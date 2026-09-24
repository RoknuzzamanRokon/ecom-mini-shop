"""
Support ticket API.

Customer endpoints (/api/support/…) only ever see the caller's own tickets and
never internal notes. Another customer's ticket or attachment is a 404, the
same as one that doesn't exist. Rules live in SupportTicketService; views only
translate: SupportTicketError → 400 {"detail"}, SupportTicket.DoesNotExist →
404, and Django's PermissionDenied (raised by the service) → 403 through DRF.
"""
from django.db.models import F, Prefetch, Q
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
from .permissions import CanCreateSupportTickets, CanViewOwnSupportTickets
from .serializers import (
    CustomerTicketDetailSerializer,
    CustomerTicketListSerializer,
    TicketCreateSerializer,
    TicketReplySerializer,
)
from .services import SupportTicketService


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
