import pytest

from activity.models import ActivityEvent
from activity.services import queue_activity_event

pytestmark = pytest.mark.django_db


class TestQueueActivityEvent:
    def test_creates_event_with_all_fields(self):
        event = queue_activity_event(
            "bot_bet",
            "Underdog placed a bet",
            url="/matches/42/",
            icon="coin",
        )
        assert event.pk is not None
        assert event.event_type == "bot_bet"
        assert event.message == "Underdog placed a bet"
        assert event.url == "/matches/42/"
        assert event.icon == "coin"
        assert event.broadcast_at is None

    def test_defaults_url_and_icon(self):
        event = queue_activity_event("odds_update", "Fresh odds")
        assert event.url == ""
        assert event.icon == "lightning"

    def test_returns_saved_instance(self):
        event = queue_activity_event("bot_comment", "Bot commented")
        assert ActivityEvent.objects.filter(pk=event.pk).exists()

    def test_multiple_events_all_queued(self):
        queue_activity_event("bot_bet", "Bet 1")
        queue_activity_event("bot_bet", "Bet 2")
        queue_activity_event("score_change", "Goal!")
        assert ActivityEvent.objects.filter(broadcast_at__isnull=True).count() == 3
