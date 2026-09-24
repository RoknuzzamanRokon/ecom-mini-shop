from django.urls import path

from .views import (
    CustomerAttachmentDownloadView,
    CustomerTicketCloseView,
    CustomerTicketDetailView,
    CustomerTicketListCreateView,
    CustomerTicketMessageCreateView,
    CustomerUnreadCountView,
)

app_name = "support"

urlpatterns = [
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
]
