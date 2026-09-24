from django.urls import path

from .views import (
    CustomerAttachmentDownloadView,
    CustomerTicketCloseView,
    CustomerTicketDetailView,
    CustomerTicketListCreateView,
    CustomerTicketMessageCreateView,
    CustomerUnreadCountView,
    StaffAssigneeListView,
    StaffAttachmentDownloadView,
    StaffTicketAssignView,
    StaffTicketDetailView,
    StaffTicketListView,
    StaffTicketMessageCreateView,
    StaffTicketSummaryView,
)

app_name = "support"

urlpatterns = [
    # Customer: the caller's own tickets only.
    path("tickets/", CustomerTicketListCreateView.as_view(), name="ticket-list-create"),
    # Before <ticket_number>/ so it isn't read as a ticket number.
    path("tickets/unread-count/", CustomerUnreadCountView.as_view(), name="ticket-unread-count"),
    path("tickets/<str:ticket_number>/", CustomerTicketDetailView.as_view(), name="ticket-detail"),
    path(
        "tickets/<str:ticket_number>/messages/",
        CustomerTicketMessageCreateView.as_view(),
        name="ticket-messages",
    ),
    path("tickets/<str:ticket_number>/close/", CustomerTicketCloseView.as_view(), name="ticket-close"),
    path("attachments/<int:pk>/", CustomerAttachmentDownloadView.as_view(), name="attachment-download"),

    # Staff: every ticket, gated by the support.staff.* codes.
    path("staff/tickets/", StaffTicketListView.as_view(), name="staff-ticket-list"),
    path("staff/tickets/<str:ticket_number>/", StaffTicketDetailView.as_view(), name="staff-ticket-detail"),
    path(
        "staff/tickets/<str:ticket_number>/messages/",
        StaffTicketMessageCreateView.as_view(),
        name="staff-ticket-messages",
    ),
    path(
        "staff/tickets/<str:ticket_number>/assign/",
        StaffTicketAssignView.as_view(),
        name="staff-ticket-assign",
    ),
    path("staff/assignees/", StaffAssigneeListView.as_view(), name="staff-assignees"),
    path("staff/summary/", StaffTicketSummaryView.as_view(), name="staff-summary"),
    path(
        "staff/attachments/<int:pk>/",
        StaffAttachmentDownloadView.as_view(),
        name="staff-attachment-download",
    ),
]
