from django.urls import path

from .views import InboxView, MarkReadView, PreferencesView, ReadAllView, UnreadCountView

app_name = "notifications"

urlpatterns = [
    path("", InboxView.as_view(), name="inbox"),
    path("unread-count/", UnreadCountView.as_view(), name="unread-count"),
    path("read-all/", ReadAllView.as_view(), name="read-all"),
    path("preferences/", PreferencesView.as_view(), name="preferences"),
    path("<int:pk>/read/", MarkReadView.as_view(), name="mark-read"),
]
