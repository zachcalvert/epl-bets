import pytest
from django.utils import timezone

from activity.models import ActivityEvent

pytestmark = pytest.mark.django_db


class TestActivityEventModel:
    def test_creation_defaults(self):
        event = ActivityEvent.objects.create(
            event_type=ActivityEvent.EventType.BOT_BET,
            message="Test bot bet",
            url="/matches/1/",
            icon="coin",
        )
        assert event.broadcast_at is None
        assert event.icon == "coin"
        assert event.created_at is not None

    def test_default_icon(self):
        event = ActivityEvent.objects.create(
            event_type=ActivityEvent.EventType.ODDS_UPDATE,
            message="Odds refreshed",
        )
        assert event.icon == "lightning"
        assert event.url == ""

    def test_str_queued(self):
        event = ActivityEvent.objects.create(
            event_type=ActivityEvent.EventType.BOT_COMMENT,
            message="Parlay Pete commented",
        )
        assert str(event) == "[queued] Parlay Pete commented"

    def test_str_sent(self):
        event = ActivityEvent.objects.create(
            event_type=ActivityEvent.EventType.SCORE_CHANGE,
            message="GOAL! Arsenal 1-0 Chelsea",
            broadcast_at=timezone.now(),
        )
        assert str(event) == "[sent] GOAL! Arsenal 1-0 Chelsea"

    def test_ordering_oldest_first(self):
        e1 = ActivityEvent.objects.create(
            event_type=ActivityEvent.EventType.BOT_BET,
            message="First",
        )
        e2 = ActivityEvent.objects.create(
            event_type=ActivityEvent.EventType.BOT_BET,
            message="Second",
        )
        events = list(ActivityEvent.objects.all())
        assert events[0].pk == e1.pk
        assert events[1].pk == e2.pk

    def test_all_event_types_valid(self):
        for event_type, _ in ActivityEvent.EventType.choices:
            event = ActivityEvent.objects.create(
                event_type=event_type,
                message=f"Test {event_type}",
            )
            assert event.pk is not None
