from unittest.mock import Mock

import pytest

from activity.consumers import SITE_ACTIVITY_GROUP, ActivityConsumer
from users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


class SimpleLayer:
    def __init__(self):
        self.added = []
        self.discarded = []

    async def group_add(self, group, channel):
        self.added.append((group, channel))

    async def group_discard(self, group, channel):
        self.discarded.append((group, channel))


def build_consumer(user=None):
    consumer = ActivityConsumer()
    consumer.scope = {"user": user}
    consumer.channel_name = "test-channel"
    return consumer


class TestActivityConsumerConnect:
    def test_anonymous_user_can_connect(self, monkeypatch):
        consumer = build_consumer(user=None)
        accept = Mock()
        layer = SimpleLayer()
        monkeypatch.setattr(consumer, "accept", accept)
        monkeypatch.setattr("activity.consumers.get_channel_layer", lambda: layer)

        consumer.connect()

        accept.assert_called_once()
        assert layer.added == [(SITE_ACTIVITY_GROUP, "test-channel")]

    def test_authenticated_user_can_connect(self, monkeypatch):
        user = UserFactory()
        consumer = build_consumer(user=user)
        accept = Mock()
        layer = SimpleLayer()
        monkeypatch.setattr(consumer, "accept", accept)
        monkeypatch.setattr("activity.consumers.get_channel_layer", lambda: layer)

        consumer.connect()

        accept.assert_called_once()
        assert layer.added == [(SITE_ACTIVITY_GROUP, "test-channel")]

    def test_connect_joins_site_activity_group(self, monkeypatch):
        consumer = build_consumer()
        monkeypatch.setattr(consumer, "accept", Mock())
        layer = SimpleLayer()
        monkeypatch.setattr("activity.consumers.get_channel_layer", lambda: layer)

        consumer.connect()

        assert (SITE_ACTIVITY_GROUP, "test-channel") in layer.added


class TestActivityConsumerDisconnect:
    def test_disconnect_leaves_group(self, monkeypatch):
        consumer = build_consumer()
        layer = SimpleLayer()
        monkeypatch.setattr("activity.consumers.get_channel_layer", lambda: layer)

        consumer.disconnect(1000)

        assert layer.discarded == [(SITE_ACTIVITY_GROUP, "test-channel")]


class TestActivityConsumerEvent:
    def _make_event(self, **overrides):
        return {
            "type": "activity_event",
            "message": "Underdog placed a bet on Arsenal",
            "url": "/matches/1/",
            "icon": "coin",
            "event_type": "bot_bet",
            **overrides,
        }

    def test_sends_rendered_html_to_anonymous_user(self, monkeypatch):
        consumer = build_consumer(user=None)
        consumer.send = Mock()
        monkeypatch.setattr(
            "activity.consumers.render_to_string",
            lambda template, ctx: f"TOAST:{ctx['message']}",
        )

        consumer.activity_event(self._make_event())

        consumer.send.assert_called_once()
        assert "TOAST:Underdog placed a bet on Arsenal" in consumer.send.call_args.kwargs["text_data"]

    def test_sends_rendered_html_to_opted_in_user(self, monkeypatch):
        user = UserFactory(show_activity_toasts=True)
        consumer = build_consumer(user=user)
        consumer.send = Mock()
        monkeypatch.setattr(
            "activity.consumers.render_to_string",
            lambda template, ctx: f"TOAST:{ctx['message']}",
        )

        consumer.activity_event(self._make_event())

        consumer.send.assert_called_once()

    def test_skips_opted_out_authenticated_user(self, monkeypatch):
        user = UserFactory(show_activity_toasts=False)
        consumer = build_consumer(user=user)
        consumer.send = Mock()

        consumer.activity_event(self._make_event())

        consumer.send.assert_not_called()

    def test_passes_all_context_to_template(self, monkeypatch):
        consumer = build_consumer(user=None)
        consumer.send = Mock()
        captured = {}

        def fake_render(template, ctx):
            captured.update(ctx)
            return "HTML"

        monkeypatch.setattr("activity.consumers.render_to_string", fake_render)
        event = self._make_event(message="GOAL!", url="/matches/99/", icon="soccer-ball")

        consumer.activity_event(event)

        assert captured["message"] == "GOAL!"
        assert captured["url"] == "/matches/99/"
        assert captured["icon"] == "soccer-ball"
        assert captured["event_type"] == "bot_bet"

    def test_swallows_render_errors(self, monkeypatch):
        consumer = build_consumer(user=None)
        consumer.send = Mock()
        monkeypatch.setattr(
            "activity.consumers.render_to_string",
            lambda *a: (_ for _ in ()).throw(RuntimeError("template error")),
        )

        # Should not raise
        consumer.activity_event(self._make_event())

        consumer.send.assert_not_called()
