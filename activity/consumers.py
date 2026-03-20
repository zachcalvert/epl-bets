import logging

from asgiref.sync import async_to_sync
from channels.generic.websocket import WebsocketConsumer
from channels.layers import get_channel_layer
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)

SITE_ACTIVITY_GROUP = "site_activity"


class ActivityConsumer(WebsocketConsumer):
    """
    Site-wide WebSocket consumer for live activity toasts.

    All visitors (including anonymous) join a single ``site_activity`` group.
    A periodic Celery task drips events into this group at a controlled rate.
    """

    def connect(self):
        self.accept()
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_add)(
            SITE_ACTIVITY_GROUP, self.channel_name
        )

    def disconnect(self, close_code):
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_discard)(
            SITE_ACTIVITY_GROUP, self.channel_name
        )

    def activity_event(self, event):
        """Render and push an activity toast via OOB swap."""
        user = self.scope.get("user")
        if (
            user
            and user.is_authenticated
            and not user.show_activity_toasts
        ):
            return

        try:
            html = render_to_string(
                "activity/partials/activity_toast_oob.html",
                {
                    "message": event["message"],
                    "url": event["url"],
                    "icon": event["icon"],
                    "event_type": event["event_type"],
                },
            )
            self.send(text_data=html)
        except Exception:
            logger.exception("Error rendering activity toast")
