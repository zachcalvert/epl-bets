from unittest.mock import Mock

import pytest

from matches.models import Match
from matches.tasks import (
    _broadcast_score_changes,
    fetch_fixtures,
    fetch_live_scores,
    fetch_standings,
    fetch_teams,
)
from matches.tests.factories import MatchFactory

pytestmark = pytest.mark.django_db


def test_fetch_teams_calls_sync_with_current_season(monkeypatch, settings):
    called = {}

    def fake_sync(season):
        called["season"] = season
        return (1, 0)

    monkeypatch.setattr("matches.tasks.sync_teams", fake_sync)

    fetch_teams.run()

    assert called["season"] == settings.CURRENT_SEASON


def test_fetch_fixtures_retries_with_exponential_backoff(monkeypatch):
    retry = Mock(side_effect=RuntimeError("retry"))
    monkeypatch.setattr("matches.tasks.sync_matches", Mock(side_effect=ValueError("boom")))
    fetch_fixtures.push_request(retries=2)
    monkeypatch.setattr(fetch_fixtures, "retry", retry)

    try:
        with pytest.raises(RuntimeError, match="retry"):
            fetch_fixtures.run()
    finally:
        fetch_fixtures.pop_request()

    retry.assert_called_once()
    assert retry.call_args.kwargs["countdown"] == 240


def test_fetch_standings_retries_with_exponential_backoff(monkeypatch):
    retry = Mock(side_effect=RuntimeError("retry"))
    monkeypatch.setattr("matches.tasks.sync_standings", Mock(side_effect=ValueError("boom")))
    fetch_standings.push_request(retries=1)
    monkeypatch.setattr(fetch_standings, "retry", retry)

    try:
        with pytest.raises(RuntimeError, match="retry"):
            fetch_standings.run()
    finally:
        fetch_standings.pop_request()

    assert retry.call_args.kwargs["countdown"] == 120


def test_fetch_live_scores_calls_broadcast_when_sync_changes_exist(monkeypatch, settings):
    live_match = MatchFactory(status=Match.Status.IN_PLAY, season=settings.CURRENT_SEASON, home_score=0, away_score=0)
    broadcast = Mock()
    monkeypatch.setattr("matches.tasks.sync_matches", lambda season, status=None: (0, 1))
    monkeypatch.setattr("matches.tasks._broadcast_score_changes", broadcast)

    fetch_live_scores.run()

    broadcast.assert_called_once_with(
        {live_match.pk: (0, 0, Match.Status.IN_PLAY)}
    )


def test_fetch_live_scores_skips_broadcast_when_nothing_changes(monkeypatch):
    broadcast = Mock()
    monkeypatch.setattr("matches.tasks.sync_matches", lambda season, status=None: (0, 0))
    monkeypatch.setattr("matches.tasks._broadcast_score_changes", broadcast)

    fetch_live_scores.run()

    broadcast.assert_not_called()


def test_fetch_live_scores_retries_with_exponential_backoff(monkeypatch):
    retry = Mock(side_effect=RuntimeError("retry"))
    monkeypatch.setattr("matches.tasks.sync_matches", Mock(side_effect=ValueError("boom")))
    fetch_live_scores.push_request(retries=2)
    monkeypatch.setattr(fetch_live_scores, "retry", retry)

    try:
        with pytest.raises(RuntimeError, match="retry"):
            fetch_live_scores.run()
    finally:
        fetch_live_scores.pop_request()

    assert retry.call_args.kwargs["countdown"] == 120


def test_broadcast_score_changes_sends_updates_and_triggers_settlement(monkeypatch, settings):
    match = MatchFactory(
        status=Match.Status.FINISHED,
        season=settings.CURRENT_SEASON,
        home_score=2,
        away_score=1,
    )
    sent = []
    delay = Mock()
    channel_layer = SimpleChannelLayer(sent)
    monkeypatch.setattr("channels.layers.get_channel_layer", lambda: channel_layer)
    monkeypatch.setattr("betting.tasks.settle_match_bets.delay", delay)

    _broadcast_score_changes({match.pk: (1, 1, Match.Status.IN_PLAY)})

    assert sent == [
        ("live_scores", {"type": "score_update", "match_id": match.pk}),
        (f"match_{match.pk}", {"type": "match_score_update", "match_id": match.pk}),
    ]
    delay.assert_called_once_with(match.pk)


def test_broadcast_score_changes_returns_when_channel_layer_missing(monkeypatch):
    monkeypatch.setattr("channels.layers.get_channel_layer", lambda: None)

    _broadcast_score_changes({})


def test_broadcast_score_changes_ignores_unchanged_match(monkeypatch, settings):
    match = MatchFactory(
        status=Match.Status.IN_PLAY,
        season=settings.CURRENT_SEASON,
        home_score=1,
        away_score=1,
    )
    sent = []
    channel_layer = SimpleChannelLayer(sent)
    monkeypatch.setattr("channels.layers.get_channel_layer", lambda: channel_layer)

    _broadcast_score_changes({match.pk: (1, 1, Match.Status.IN_PLAY)})

    assert sent == []


class SimpleChannelLayer:
    def __init__(self, sent):
        self.sent = sent

    async def group_send(self, group, message):
        self.sent.append((group, message))
