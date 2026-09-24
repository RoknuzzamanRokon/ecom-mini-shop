"""
Support ticket API.

Customer endpoints (/api/support/…) only ever see the caller's own tickets and
never internal notes. Another customer's ticket or attachment is a 404, the
same as one that doesn't exist. Staff endpoints (/api/support/staff/…) see
every ticket and every message, and are gated per action by the
support.staff.* codes.

Rules live in SupportTicketService; views only translate: SupportTicketError →
400 {"detail"}, SupportTicket.DoesNotExist → 404, and Django's
PermissionDenied (raised by the service) → 403 through DRF.
"""
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Case, Count, F, IntegerField, Prefetch, Q, Value, When
from django.http import FileResponse
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.generics import get_object_or_404
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.utils import get_client_ip

from .exceptions import SupportTicketError
from .models import SupportTicket, TicketAttachment, TicketMessage
from .permissions import (
    CanCreateSupportTickets,
    CanManageSupportTickets,
    CanReplySupportTickets,
    CanViewOwnSupportTickets,
    CanViewSupportTickets,
)
from .serializers import (
    CustomerTicketDetailSerializer,
    CustomerTicketListSerializer,
    StaffAssignSerializer,
    StaffMessageInputSerializer,
    StaffTicketDetailSerializer,
    StaffTicketListSerializer,
    StaffTicketUpdateSerializer,
    TicketCreateSerializer,
    TicketReplySerializer,
    staff_display_name,
)
from .services import SupportTicketService

User = get_user_model()


def _bad_request(exc):
    return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


def _ticket_not_found():
    return NotFound("Ticket not found.")


def attachment_response(attachment):
    """
    Streams a private attachment. The content type is the one detected from the
    file's bytes at upload, and nosniff stops the browser from guessing another.
    """
    try:
        handle = attachment.file.open("rb")
    except FileNotFoundError:
        raise NotFound("This file is no longer available.")
    response = FileResponse(
        handle,
        content_type=attachment.content_type,
        as_attachment=False,
        filename=attachment.original_name,
    )
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    return response


def customer_tickets(user):
    """The caller's own tickets, with public messages (never internal ones) prefetched."""
    public_messages = (
        TicketMessage.objects.filter(is_internal=False)
        .select_related("author")
        .prefetch_related("attachments")
        .order_by("created_at", "id")
    )
    return (
        SupportTicket.objects.filter(customer=user)
        .select_related("order")
        .prefetch_related(Prefetch("messages", queryset=public_messages, to_attr="public_messages"))
    )


class CustomerTicketPagination(PageNumberPagination):
    page_size = 10


class CustomerTicketListCreateView(APIView):
    """
    GET  /api/support/tickets/?status=open|closed|all&page=   (support.view)
    POST /api/support/tickets/  multipart                      (support.create)
    """

    STATUS_FILTERS = {
        "open": ~Q(status=SupportTicket.STATUS_CLOSED),
        "closed": Q(status=SupportTicket.STATUS_CLOSED),
        "all": Q(),
    }

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), CanCreateSupportTickets()]
        return [IsAuthenticated(), CanViewOwnSupportTickets()]

    def get(self, request):
        status_filter = request.query_params.get("status") or "all"
        if status_filter not in self.STATUS_FILTERS:
            return Response(
                {"detail": "status must be open, closed or all."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        queryset = (
            SupportTicket.objects.filter(customer=request.user)
            .filter(self.STATUS_FILTERS[status_filter])
            .select_related("order")
            .order_by("-last_activity_at", "-id")
        )
        paginator = CustomerTicketPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(CustomerTicketListSerializer(page, many=True).data)

    def post(self, request):
        serializer = TicketCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            ticket = SupportTicketService.create_ticket(
                request.user,
                category=data["category"],
                subject=data["subject"],
                description=data["description"],
                order_number=data.get("order_number"),
                files=data.get("attachments", []),
                ip_address=get_client_ip(request),
            )
        except SupportTicketError as exc:
            return _bad_request(exc)
        ticket = customer_tickets(request.user).get(pk=ticket.pk)
        return Response(CustomerTicketDetailSerializer(ticket).data, status=status.HTTP_201_CREATED)


class CustomerUnreadCountView(APIView):
    """GET /api/support/tickets/unread-count/ → {"unread": n}: tickets with a staff reply the customer hasn't opened."""

    permission_classes = [IsAuthenticated, CanViewOwnSupportTickets]

    def get(self, request):
        unread = (
            SupportTicket.objects.filter(customer=request.user, last_staff_reply_at__isnull=False)
            .filter(
                Q(customer_last_read_at__isnull=True)
                | Q(last_staff_reply_at__gt=F("customer_last_read_at"))
            )
            .count()
        )
        return Response({"unread": unread})


class CustomerTicketDetailView(APIView):
    """GET /api/support/tickets/<ticket_number>/ — also marks the staff replies as read."""

    permission_classes = [IsAuthenticated, CanViewOwnSupportTickets]

    def get(self, request, ticket_number):
        ticket = get_object_or_404(customer_tickets(request.user), ticket_number=ticket_number)
        if ticket.has_unread_for_customer:
            # Only when something is unread, so the page's periodic refetch doesn't write.
            SupportTicketService.mark_read_by_customer(ticket)
        return Response(CustomerTicketDetailSerializer(ticket).data)


class CustomerTicketMessageCreateView(APIView):
    """POST /api/support/tickets/<ticket_number>/messages/  multipart: body, attachments → the ticket."""

    permission_classes = [IsAuthenticated, CanCreateSupportTickets]

    def post(self, request, ticket_number):
        serializer = TicketReplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            SupportTicketService.add_customer_reply(
                request.user,
                ticket_number,
                data.get("body", ""),
                files=data.get("attachments", []),
                ip_address=get_client_ip(request),
            )
        except SupportTicket.DoesNotExist:
            raise _ticket_not_found()
        except SupportTicketError as exc:
            return _bad_request(exc)
        ticket = customer_tickets(request.user).get(ticket_number=ticket_number)
        return Response(CustomerTicketDetailSerializer(ticket).data, status=status.HTTP_201_CREATED)


class CustomerTicketCloseView(APIView):
    """POST /api/support/tickets/<ticket_number>/close/ → the closed ticket."""

    permission_classes = [IsAuthenticated, CanCreateSupportTickets]

    def post(self, request, ticket_number):
        try:
            SupportTicketService.close_by_customer(
                request.user, ticket_number, ip_address=get_client_ip(request)
            )
        except SupportTicket.DoesNotExist:
            raise _ticket_not_found()
        except SupportTicketError as exc:
            return _bad_request(exc)
        ticket = customer_tickets(request.user).get(ticket_number=ticket_number)
        return Response(CustomerTicketDetailSerializer(ticket).data)


class CustomerAttachmentDownloadView(APIView):
    """GET /api/support/attachments/<id>/ — the caller's own ticket, public messages only."""

    permission_classes = [IsAuthenticated, CanViewOwnSupportTickets]

    def get(self, request, pk):
        attachment = get_object_or_404(
            TicketAttachment,
            pk=pk,
            message__ticket__customer=request.user,
            message__is_internal=False,
        )
        return attachment_response(attachment)


# ---------------------------------------------------------------------- staff


def staff_tickets():
    """Every ticket, with what the staff list and detail serializers read."""
    return SupportTicket.objects.select_related("customer__customer_profile", "assigned_to", "order")


def staff_ticket_detail(ticket_number):
    messages = (
        TicketMessage.objects.select_related("author__customer_profile")
        .prefetch_related("attachments")
        .order_by("created_at", "id")
    )
    ticket = (
        staff_tickets()
        .prefetch_related(Prefetch("messages", queryset=messages, to_attr="all_messages"))
        .filter(ticket_number=ticket_number)
        .first()
    )
    if ticket is None:
        raise _ticket_not_found()
    return ticket


class StaffTicketPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class StaffTicketListView(APIView):
    """
    GET /api/support/staff/tickets/   (support.staff.view)

    Filters: status (a status code, `active` = everything but CLOSED, or `all`),
    priority, category, assigned (`me`, `unassigned` or a user id),
    needs_reply=true, search (ticket number, subject, customer name / username /
    email, order number). ordering: -last_activity_at (default),
    last_activity_at, -created_at, created_at, -priority, priority.
    """

    permission_classes = [IsAuthenticated, CanViewSupportTickets]

    PRIORITY_RANK = Case(
        When(priority=SupportTicket.PRIORITY_LOW, then=Value(0)),
        When(priority=SupportTicket.PRIORITY_NORMAL, then=Value(1)),
        When(priority=SupportTicket.PRIORITY_HIGH, then=Value(2)),
        When(priority=SupportTicket.PRIORITY_URGENT, then=Value(3)),
        output_field=IntegerField(),
    )
    ORDERINGS = {
        "-last_activity_at": ["-last_activity_at", "-id"],
        "last_activity_at": ["last_activity_at", "id"],
        "-created_at": ["-created_at", "-id"],
        "created_at": ["created_at", "id"],
        "-priority": ["-priority_rank", "-last_activity_at", "-id"],
        "priority": ["priority_rank", "-last_activity_at", "-id"],
    }

    def get(self, request):
        params = request.query_params
        queryset = staff_tickets()

        status_filter = params.get("status", "").strip()
        if status_filter == "active":
            queryset = queryset.exclude(status=SupportTicket.STATUS_CLOSED)
        elif status_filter in dict(SupportTicket.STATUS_CHOICES):
            queryset = queryset.filter(status=status_filter)
        elif status_filter not in ("", "all"):
            return _bad_request("Unknown status filter.")

        for field, choices in (
            ("priority", SupportTicket.PRIORITY_CHOICES),
            ("category", SupportTicket.CATEGORY_CHOICES),
        ):
            value = params.get(field, "").strip()
            if not value:
                continue
            if value not in dict(choices):
                return _bad_request(f"Unknown {field} filter.")
            queryset = queryset.filter(**{field: value})

        assigned = params.get("assigned", "").strip()
        if assigned == "me":
            queryset = queryset.filter(assigned_to=request.user)
        elif assigned == "unassigned":
            queryset = queryset.filter(assigned_to__isnull=True)
        elif assigned.isdigit():
            queryset = queryset.filter(assigned_to_id=int(assigned))
        elif assigned:
            return _bad_request("assigned must be me, unassigned or a user id.")

        if params.get("needs_reply", "").strip().lower() in ("true", "1"):
            queryset = queryset.needs_reply()

        search = params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(ticket_number__icontains=search)
                | Q(subject__icontains=search)
                | Q(customer__username__icontains=search)
                | Q(customer__email__icontains=search)
                | Q(customer__first_name__icontains=search)
                | Q(customer__last_name__icontains=search)
                | Q(order__order_number__icontains=search)
            )

        ordering = params.get("ordering", "").strip() or "-last_activity_at"
        if ordering not in self.ORDERINGS:
            return _bad_request("Unknown ordering.")
        if "priority" in ordering:
            queryset = queryset.annotate(priority_rank=self.PRIORITY_RANK)
        queryset = queryset.order_by(*self.ORDERINGS[ordering])

        paginator = StaffTicketPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(StaffTicketListSerializer(page, many=True).data)


class StaffTicketDetailView(APIView):
    """
    GET   /api/support/staff/tickets/<ticket_number>/   (support.staff.view)
    PATCH /api/support/staff/tickets/<ticket_number>/   (support.staff.manage)
          {status?, priority?, category?, reason?}; all-or-nothing.
    """

    def get_permissions(self):
        if self.request.method == "PATCH":
            return [IsAuthenticated(), CanViewSupportTickets(), CanManageSupportTickets()]
        return [IsAuthenticated(), CanViewSupportTickets()]

    def get(self, request, ticket_number):
        return Response(StaffTicketDetailSerializer(staff_ticket_detail(ticket_number)).data)

    def patch(self, request, ticket_number):
        serializer = StaffTicketUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if not ({"status", "priority", "category"} & set(data)):
            return _bad_request("Nothing to change.")
        reason = data.get("reason", "")
        ip_address = get_client_ip(request)
        try:
            # One request, one outcome: a refused status change also undoes
            # the priority/category change made with it.
            with transaction.atomic():
                if "priority" in data or "category" in data:
                    SupportTicketService.update_details(
                        request.user, ticket_number,
                        priority=data.get("priority"),
                        category=data.get("category"),
                        reason=reason,
                        ip_address=ip_address,
                    )
                if "status" in data:
                    SupportTicketService.change_status(
                        request.user, ticket_number, data["status"],
                        reason=reason, ip_address=ip_address,
                    )
        except SupportTicket.DoesNotExist:
            raise _ticket_not_found()
        except SupportTicketError as exc:
            return _bad_request(exc)
        return Response(StaffTicketDetailSerializer(staff_ticket_detail(ticket_number)).data)


class StaffTicketMessageCreateView(APIView):
    """
    POST /api/support/staff/tickets/<ticket_number>/messages/   (support.staff.reply)
         multipart: body, is_internal, set_status (needs support.staff.manage), attachments
    """

    permission_classes = [IsAuthenticated, CanViewSupportTickets, CanReplySupportTickets]

    def post(self, request, ticket_number):
        serializer = StaffMessageInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            SupportTicketService.add_staff_message(
                request.user,
                ticket_number,
                data.get("body", ""),
                files=data.get("attachments", []),
                is_internal=data.get("is_internal", False),
                set_status=data.get("set_status") or None,
                ip_address=get_client_ip(request),
            )
        except SupportTicket.DoesNotExist:
            raise _ticket_not_found()
        except SupportTicketError as exc:
            return _bad_request(exc)
        return Response(
            StaffTicketDetailSerializer(staff_ticket_detail(ticket_number)).data,
            status=status.HTTP_201_CREATED,
        )


class StaffTicketAssignView(APIView):
    """POST /api/support/staff/tickets/<ticket_number>/assign/  {"assignee_id": 12 or null}   (support.staff.manage)"""

    permission_classes = [IsAuthenticated, CanViewSupportTickets, CanManageSupportTickets]

    def post(self, request, ticket_number):
        serializer = StaffAssignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        assignee_id = serializer.validated_data["assignee_id"]
        assignee = None
        if assignee_id is not None:
            assignee = User.objects.filter(pk=assignee_id).first()
            if assignee is None:
                return _bad_request("That user can't be assigned support tickets.")
        try:
            SupportTicketService.assign(
                request.user, ticket_number, assignee, ip_address=get_client_ip(request)
            )
        except SupportTicket.DoesNotExist:
            raise _ticket_not_found()
        except SupportTicketError as exc:
            return _bad_request(exc)
        return Response(StaffTicketDetailSerializer(staff_ticket_detail(ticket_number)).data)


class StaffAssigneeListView(APIView):
    """GET /api/support/staff/assignees/ → [{id, name, email}]: who a ticket can be assigned to."""

    permission_classes = [IsAuthenticated, CanViewSupportTickets]

    def get(self, request):
        return Response([
            {"id": user.pk, "name": staff_display_name(user), "email": user.email}
            for user in SupportTicketService.get_assignable_staff()
        ])


class StaffTicketSummaryView(APIView):
    """
    GET /api/support/staff/summary/   (support.staff.view)
    {by_status: {<status>: n, ...}, active, needs_reply, unassigned, assigned_to_me}.
    The last four count only tickets that aren't closed.
    """

    permission_classes = [IsAuthenticated, CanViewSupportTickets]

    def get(self, request):
        # order_by() clears Meta.ordering, which would otherwise split the GROUP BY.
        grouped = dict(
            SupportTicket.objects.order_by().values_list("status").annotate(n=Count("id"))
        )
        by_status = {code: grouped.get(code, 0) for code, _ in SupportTicket.STATUS_CHOICES}
        counts = SupportTicket.objects.exclude(status=SupportTicket.STATUS_CLOSED).aggregate(
            active=Count("id"),
            needs_reply=Count("id", filter=SupportTicket.needs_reply_condition()),
            unassigned=Count("id", filter=Q(assigned_to__isnull=True)),
            assigned_to_me=Count("id", filter=Q(assigned_to=request.user)),
        )
        return Response({"by_status": by_status, **counts})


class StaffAttachmentDownloadView(APIView):
    """GET /api/support/staff/attachments/<id>/ — any attachment, internal ones included."""

    permission_classes = [IsAuthenticated, CanViewSupportTickets]

    def get(self, request, pk):
        return attachment_response(get_object_or_404(TicketAttachment, pk=pk))
