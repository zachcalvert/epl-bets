import logging

from channels.generic.websocket import WebsocketConsumer
from django.template.loader import render_to_string

from rewards.models import RewardDistribution

logger = logging.getLogger(__name__)


class NotificationConsumer(WebsocketConsumer):
    """
    Per-user WebSocket consumer for real-time notifications.

    Authenticated users connect from base.html and join a personal group
    ``user_notifications_<id>``.  When a reward is distributed, the model
    layer broadcasts to this group and the consumer pushes an OOB toast.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.group_name = None

    def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            self.close()
            return

        self.group_name = f"user_notifications_{user.pk}"
        self.accept()
        self._join_group(self.group_name)

    def disconnect(self, close_code):
        if self.group_name:
            from asgiref.sync import async_to_sync
            from channels.layers import get_channel_layer

            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_discard)(
                self.group_name, self.channel_name
            )
            self.group_name = None

    def _join_group(self, group_name):
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_add)(group_name, self.channel_name)

    # ── Channel layer event handlers ──

    def reward_notification(self, event):
        """Push a reward toast to the connected user via OOB swap."""
        distribution_id = event["distribution_id"]
        try:
            distribution = (
                RewardDistribution.objects.filter(pk=distribution_id)
                .select_related("reward")
                .first()
            )
            if not distribution:
                return

            html = render_to_string(
                "rewards/partials/reward_toast_oob.html",
                {"distribution": distribution},
            )
            self.send(text_data=html)
        except Exception:
            logger.exception(
                "Error rendering reward_notification for distribution %s",
                distribution_id,
            )
