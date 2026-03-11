from unittest.mock import Mock

import pytest

from matches.consumers import LiveUpdatesConsumer
from matches.tests.factories import MatchFactory


pytestmark = pytest.mark.django_db


def build_consumer(scope_value):
    consumer = LiveUpdatesConsumer()
    consumer.scope = {"url_route": {"kwargs": {"scope": scope_value}}}
    consumer.channel_name = "test-channel"
    return consumer


def test_connect_joins_dashboard_group(monkeypatch):
    consumer = build_consumer("dashboard")
    accept = Mock()
    join_group = Mock()
    monkeypatch.setattr(consumer, "accept", accept)
    monkeypatch.setattr(consumer, "_join_group", join_group)

    consumer.connect()

    accept.assert_called_once_with()
    join_group.assert_called_once_with("live_scores")


def test_connect_joins_match_group_for_numeric_scope(monkeypatch):
    consumer = build_consumer("42")
    monkeypatch.setattr(consumer, "accept", Mock())
    join_group = Mock()
    monkeypatch.setattr(consumer, "_join_group", join_group)

    consumer.connect()

    join_group.assert_called_once_with("match_42")


def test_connect_ignores_unknown_scope(monkeypatch):
    consumer = build_consumer("invalid-scope")
    monkeypatch.setattr(consumer, "accept", Mock())
    join_group = Mock()
    monkeypatch.setattr(consumer, "_join_group", join_group)

    consumer.connect()

    join_group.assert_not_called()


def test_disconnect_discards_all_joined_groups(monkeypatch):
    consumer = build_consumer("dashboard")
    consumer.groups_joined = ["live_scores", "match_1"]
    layer = SimpleLayer()
    monkeypatch.setattr("channels.layers.get_channel_layer", lambda: layer)

    consumer.disconnect(1000)

    assert layer.discarded == [
        ("live_scores", "test-channel"),
        ("match_1", "test-channel"),
    ]
    assert consumer.groups_joined == []


def test_score_update_renders_and_sends_html(monkeypatch):
    match = MatchFactory()
    consumer = build_consumer("dashboard")
    consumer.send = Mock()
    monkeypatch.setattr(
        "matches.consumers.render_to_string",
        lambda template, context: f"{template}:{context['match'].pk}:{context['match'].best_home_odds}",
    )

    consumer.score_update({"match_id": match.pk})

    consumer.send.assert_called_once()
    assert "matches/partials/match_card_oob.html" in consumer.send.call_args.kwargs["text_data"]


def test_match_score_update_renders_and_sends_html(monkeypatch):
    match = MatchFactory()
    consumer = build_consumer(str(match.pk))
    consumer.send = Mock()
    monkeypatch.setattr(
        "matches.consumers.render_to_string",
        lambda template, context: f"{template}:{context['match'].pk}",
    )

    consumer.match_score_update({"match_id": match.pk})

    consumer.send.assert_called_once_with(
        text_data=f"matches/partials/score_display_oob.html:{match.pk}"
    )


class SimpleLayer:
    def __init__(self):
        self.discarded = []

    async def group_discard(self, group, channel):
        self.discarded.append((group, channel))
