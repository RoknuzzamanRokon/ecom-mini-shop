from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = [
            "id", "event_type", "category", "title", "body", "action_url",
            "priority", "occurred_at", "read_at",
        ]
        read_only_fields = fields
