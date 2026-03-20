from datetime import timedelta

import pytest
from django.utils import timezone

from activity.models import ActivityEvent
from activity.tasks import broadcast_next_activity_event, cleanup_old_activity_events

pytestmark = pytest.mark.django_db


class BroadcastLayer:
    def __init__(self):
        self.sent = []

    async def group_send(self, group, event):
        self.sent.append((group, event))


class TestBroadcastNextActivityEvent:
    def test_broadcasts_oldest_queued_event(self, monkeypatch):
        old = ActivityEvent.objects.create(
            event_type="bot_bet", message="First", url="/a/", icon="coin",
        )
        ActivityEvent.objects.create(
            event_type="bot_comment", message="Second",
        )
        layer = BroadcastLayer()
        monkeypatch.setattr("activity.tasks.get_channel_layer", lambda: layer)

        broadcast_next_activity_event()

        assert len(layer.sent) == 1
        group, event = layer.sent[0]
        assert group == "site_activity"
        assert event["type"] == "activity_event"
        assert event["message"] == "First"
        assert event["url"] == "/a/"
        assert event["icon"] == "coin"
        assert event["event_type"] == "bot_bet"
        old.refresh_from_db()
        assert old.broadcast_at is not None

    def test_skips_already_broadcast_events(self, monkeypatch):
        ActivityEvent.objects.create(
            event_type="bot_bet",
            message="Already sent",
            broadcast_at=timezone.now(),
        )
        layer = BroadcastLayer()
        monkeypatch.setattr("activity.tasks.get_channel_layer", lambda: layer)

        broadcast_next_activity_event()

        assert layer.sent == []

    def test_noop_when_queue_is_empty(self, monkeypatch):
        layer = BroadcastLayer()
        monkeypatch.setattr("activity.tasks.get_channel_layer", lambda: layer)

        broadcast_next_activity_event()

        assert layer.sent == []

    def test_sets_broadcast_at_on_sent_event(self, monkeypatch):
        event = ActivityEvent.objects.create(
            event_type="score_change", message="GOAL!",
        )
        layer = BroadcastLayer()
        monkeypatch.setattr("activity.tasks.get_channel_layer", lambda: layer)

        before = timezone.now()
        broadcast_next_activity_event()
        after = timezone.now()

        event.refresh_from_db()
        assert before <= event.broadcast_at <= after

    def test_broadcasts_only_one_event_per_call(self, monkeypatch):
        for i in range(5):
            ActivityEvent.objects.create(event_type="bot_bet", message=f"Bet {i}")
        layer = BroadcastLayer()
        monkeypatch.setattr("activity.tasks.get_channel_layer", lambda: layer)

        broadcast_next_activity_event()

        assert len(layer.sent) == 1
        assert ActivityEvent.objects.filter(broadcast_at__isnull=True).count() == 4

    def test_does_not_rebroadcast_if_called_twice(self, monkeypatch):
        ActivityEvent.objects.create(event_type="bot_bet", message="Once")
        layer = BroadcastLayer()
        monkeypatch.setattr("activity.tasks.get_channel_layer", lambda: layer)

        broadcast_next_activity_event()
        broadcast_next_activity_event()

        assert len(layer.sent) == 1


class TestCleanupOldActivityEvents:
    def test_deletes_events_older_than_7_days(self):
        old = ActivityEvent.objects.create(event_type="bot_bet", message="Old event")
        # Force created_at back past the 7-day cutoff
        old_time = timezone.now() - timedelta(days=8)
        ActivityEvent.objects.filter(pk=old.pk).update(created_at=old_time)

        recent = ActivityEvent.objects.create(event_type="bot_bet", message="Recent event")

        cleanup_old_activity_events()

        assert not ActivityEvent.objects.filter(pk=old.pk).exists()
        assert ActivityEvent.objects.filter(pk=recent.pk).exists()

    def test_noop_when_nothing_to_clean(self):
        ActivityEvent.objects.create(event_type="bot_bet", message="Fresh")
        cleanup_old_activity_events()
        assert ActivityEvent.objects.count() == 1
