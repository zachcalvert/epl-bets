from unittest.mock import Mock

import pytest
from django.utils import timezone

from matches.models import Match
from matches.tasks import (
    _broadcast_score_changes,
    _refresh_stale_matches,
    fetch_fixtures,
    fetch_live_scores,
    fetch_standings,
    fetch_teams,
    prefetch_upcoming_hype_data,
)
from matches.tests.factories import MatchFactory, MatchStatsFactory
from website.transparency import GLOBAL_SCOPE, get_events, match_scope, page_scope

pytestmark = pytest.mark.django_db


def test_fetch_teams_calls_sync_with_current_season(monkeypatch, settings):
    called = {}

    def fake_sync(season):
        called["season"] = season
        return (1, 0)

    monkeypatch.setattr("matches.tasks.sync_teams", fake_sync)

    fetch_teams.run()

    assert called["season"] == settings.CURRENT_SEASON


def test_fetch_teams_retries_with_exponential_backoff(monkeypatch):
    retry = Mock(side_effect=RuntimeError("retry"))
    monkeypatch.setattr("matches.tasks.sync_teams", Mock(side_effect=ValueError("boom")))
    fetch_teams.push_request(retries=1)
    monkeypatch.setattr(fetch_teams, "retry", retry)

    try:
        with pytest.raises(RuntimeError, match="retry"):
            fetch_teams.run()
    finally:
        fetch_teams.pop_request()

    assert retry.call_args.kwargs["countdown"] == 120


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


def test_fetch_standings_calls_sync_with_current_season(monkeypatch, settings):
    called = {}

    def fake_sync(season):
        called["season"] = season
        return (1, 1)

    monkeypatch.setattr("matches.tasks.sync_standings", fake_sync)

    fetch_standings.run()

    assert called["season"] == settings.CURRENT_SEASON


def test_fetch_live_scores_calls_broadcast_when_sync_changes_exist(monkeypatch, settings):
    live_match = MatchFactory(status=Match.Status.IN_PLAY, season=settings.CURRENT_SEASON, home_score=0, away_score=0)
    broadcast = Mock()
    monkeypatch.setattr("matches.tasks.sync_matches", lambda season, status=None: (0, 1))
    monkeypatch.setattr("matches.tasks._broadcast_score_changes", broadcast)

    fetch_live_scores.run()

    broadcast.assert_called_once_with(
        {live_match.pk: (0, 0, Match.Status.IN_PLAY)}
    )
    assert get_events(page_scope("dashboard"))[0]["action"] == "scores_synced"


def test_fetch_live_scores_snapshots_live_paused_and_finished_matches_only(monkeypatch, settings):
    live_match = MatchFactory(
        status=Match.Status.IN_PLAY,
        season=settings.CURRENT_SEASON,
        home_score=1,
        away_score=0,
    )
    paused_match = MatchFactory(
        status=Match.Status.PAUSED,
        season=settings.CURRENT_SEASON,
        home_score=2,
        away_score=2,
    )
    finished_match = MatchFactory(
        status=Match.Status.FINISHED,
        season=settings.CURRENT_SEASON,
        home_score=3,
        away_score=1,
    )
    MatchFactory(
        status=Match.Status.SCHEDULED,
        season=settings.CURRENT_SEASON,
        home_score=None,
        away_score=None,
    )
    MatchFactory(
        status=Match.Status.IN_PLAY,
        season="2024",
        home_score=0,
        away_score=0,
    )
    broadcast = Mock()
    monkeypatch.setattr("matches.tasks.sync_matches", lambda season, status=None: (0, 1))
    monkeypatch.setattr("matches.tasks._broadcast_score_changes", broadcast)

    fetch_live_scores.run()

    assert broadcast.call_count == 1
    assert broadcast.call_args.args[0] == {
        live_match.pk: (1, 0, Match.Status.IN_PLAY),
        paused_match.pk: (2, 2, Match.Status.PAUSED),
        finished_match.pk: (3, 1, Match.Status.FINISHED),
    }


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
    monkeypatch.setattr("matches.tasks.get_channel_layer", lambda: channel_layer)
    monkeypatch.setattr("matches.tasks.settle_match_bets.delay", delay)

    _broadcast_score_changes({match.pk: (1, 1, Match.Status.IN_PLAY)})

    assert sent == [
        ("live_scores", {"type": "score_update", "match_id": match.pk}),
        (f"match_{match.pk}", {"type": "match_score_update", "match_id": match.pk}),
    ]
    delay.assert_called_once_with(match.pk)
    assert get_events(match_scope(match.pk))[0]["action"] == "score_broadcast"
    assert get_events(page_scope("dashboard"))[0]["action"] == "score_broadcast"
    assert get_events(GLOBAL_SCOPE)[0]["action"] == "score_broadcast"


def test_broadcast_score_changes_sends_updates_for_newly_live_match(monkeypatch, settings):
    match = MatchFactory(
        status=Match.Status.IN_PLAY,
        season=settings.CURRENT_SEASON,
        home_score=1,
        away_score=0,
    )
    sent = []
    channel_layer = SimpleChannelLayer(sent)
    monkeypatch.setattr("matches.tasks.get_channel_layer", lambda: channel_layer)

    _broadcast_score_changes({})

    assert sent == [
        ("live_scores", {"type": "score_update", "match_id": match.pk}),
        (f"match_{match.pk}", {"type": "match_score_update", "match_id": match.pk}),
    ]


def test_broadcast_score_changes_returns_when_channel_layer_missing(monkeypatch):
    monkeypatch.setattr("matches.tasks.get_channel_layer", lambda: None)

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
    monkeypatch.setattr("matches.tasks.get_channel_layer", lambda: channel_layer)

    _broadcast_score_changes({match.pk: (1, 1, Match.Status.IN_PLAY)})

    assert sent == []


@pytest.mark.parametrize("status", [Match.Status.CANCELLED, Match.Status.POSTPONED])
def test_broadcast_score_changes_triggers_settlement_for_terminal_statuses(
    monkeypatch, settings, status
):
    match = MatchFactory(
        status=status,
        season=settings.CURRENT_SEASON,
        home_score=1,
        away_score=1,
    )
    sent = []
    delay = Mock()
    channel_layer = SimpleChannelLayer(sent)
    monkeypatch.setattr("matches.tasks.get_channel_layer", lambda: channel_layer)
    monkeypatch.setattr("matches.tasks.settle_match_bets.delay", delay)

    _broadcast_score_changes({match.pk: (1, 1, Match.Status.IN_PLAY)})

    delay.assert_called_once_with(match.pk)


def test_fetch_live_scores_refreshes_stale_matches(monkeypatch, settings):
    """Matches that finished between syncs (still IN_PLAY in our DB but absent
    from the LIVE API response) should be individually fetched and updated."""
    stale_match = MatchFactory(
        status=Match.Status.IN_PLAY,
        season=settings.CURRENT_SEASON,
        home_score=1,
        away_score=0,
    )

    # sync_matches returns (0, 0) — the LIVE API didn't include the stale match,
    # so our DB still has it as IN_PLAY after sync.
    monkeypatch.setattr("matches.tasks.sync_matches", lambda season, status=None: (0, 0))

    # _refresh_stale_matches will call get_match for the stale one
    monkeypatch.setattr(
        "matches.tasks._refresh_stale_matches",
        lambda stale: Match.objects.filter(
            pk__in=[pk for pk, _ in stale],
        ).update(status=Match.Status.FINISHED, home_score=2, away_score=1)
    )
    monkeypatch.setattr("matches.tasks._broadcast_score_changes", Mock())

    fetch_live_scores.run()

    stale_match.refresh_from_db()
    assert stale_match.status == Match.Status.FINISHED
    assert stale_match.home_score == 2
    assert stale_match.away_score == 1


def test_refresh_stale_matches_updates_match_from_api(monkeypatch, settings):
    """_refresh_stale_matches fetches each match individually and updates the DB."""
    match = MatchFactory(
        status=Match.Status.IN_PLAY,
        season=settings.CURRENT_SEASON,
        home_score=1,
        away_score=1,
    )

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get_match(self, ext_id):
            return {"status": "FINISHED", "home_score": 2, "away_score": 1}

    monkeypatch.setattr("matches.tasks.FootballDataClient", FakeClient)

    updated = _refresh_stale_matches([(match.pk, match.external_id)])

    assert updated == 1
    match.refresh_from_db()
    assert match.status == Match.Status.FINISHED
    assert match.home_score == 2
    assert match.away_score == 1


def test_refresh_stale_matches_continues_on_individual_failure(monkeypatch, settings):
    """If one match fails to refresh, others should still be processed."""
    match_ok = MatchFactory(
        status=Match.Status.IN_PLAY,
        season=settings.CURRENT_SEASON,
        home_score=0,
        away_score=0,
    )
    match_fail = MatchFactory(
        status=Match.Status.IN_PLAY,
        season=settings.CURRENT_SEASON,
        home_score=0,
        away_score=0,
    )

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get_match(self, ext_id):
            if ext_id == match_fail.external_id:
                raise ConnectionError("API timeout")
            return {"status": "FINISHED", "home_score": 3, "away_score": 0}

    monkeypatch.setattr("matches.tasks.FootballDataClient", FakeClient)

    updated = _refresh_stale_matches([
        (match_fail.pk, match_fail.external_id),
        (match_ok.pk, match_ok.external_id),
    ])

    assert updated == 1
    match_ok.refresh_from_db()
    assert match_ok.status == Match.Status.FINISHED
    match_fail.refresh_from_db()
    assert match_fail.status == Match.Status.IN_PLAY


# ---------------------------------------------------------------------------
# prefetch_upcoming_hype_data
# ---------------------------------------------------------------------------


def test_prefetch_upcoming_hype_data_fetches_scheduled_matches_within_48h(monkeypatch, settings):
    from datetime import timedelta
    upcoming = MatchFactory(
        status=Match.Status.SCHEDULED,
        kickoff=timezone.now() + timedelta(hours=24),
        season=settings.CURRENT_SEASON,
    )
    # Beyond 48h — should be skipped
    MatchFactory(
        status=Match.Status.SCHEDULED,
        kickoff=timezone.now() + timedelta(hours=72),
        season=settings.CURRENT_SEASON,
    )
    # Finished match — should be skipped
    MatchFactory(
        status=Match.Status.FINISHED,
        kickoff=timezone.now() + timedelta(hours=12),
        season=settings.CURRENT_SEASON,
    )
    fetched = []
    monkeypatch.setattr("matches.tasks.fetch_match_hype_data", lambda m: fetched.append(m))
    monkeypatch.setattr("matches.tasks.time.sleep", lambda s: None)

    prefetch_upcoming_hype_data()

    assert fetched == [upcoming]


def test_prefetch_upcoming_hype_data_skips_matches_with_fresh_stats(monkeypatch, settings):
    from datetime import timedelta
    match = MatchFactory(
        status=Match.Status.SCHEDULED,
        kickoff=timezone.now() + timedelta(hours=6),
        season=settings.CURRENT_SEASON,
    )
    MatchStatsFactory(match=match, fetched_at=timezone.now())  # fresh
    fetched = []
    monkeypatch.setattr("matches.tasks.fetch_match_hype_data", lambda m: fetched.append(m))
    monkeypatch.setattr("matches.tasks.time.sleep", lambda s: None)

    prefetch_upcoming_hype_data()

    assert fetched == []


def test_prefetch_upcoming_hype_data_fetches_match_with_stale_stats(monkeypatch, settings):
    from datetime import timedelta
    match = MatchFactory(
        status=Match.Status.SCHEDULED,
        kickoff=timezone.now() + timedelta(hours=6),
        season=settings.CURRENT_SEASON,
    )
    MatchStatsFactory(match=match, fetched_at=timezone.now() - timedelta(hours=25))  # stale
    fetched = []
    monkeypatch.setattr("matches.tasks.fetch_match_hype_data", lambda m: fetched.append(m))
    monkeypatch.setattr("matches.tasks.time.sleep", lambda s: None)

    prefetch_upcoming_hype_data()

    assert fetched == [match]


def test_prefetch_upcoming_hype_data_sleeps_between_matches(monkeypatch, settings):
    from datetime import timedelta
    MatchFactory(
        status=Match.Status.SCHEDULED,
        kickoff=timezone.now() + timedelta(hours=6),
        season=settings.CURRENT_SEASON,
    )
    MatchFactory(
        status=Match.Status.SCHEDULED,
        kickoff=timezone.now() + timedelta(hours=12),
        season=settings.CURRENT_SEASON,
    )
    sleep_calls = []
    monkeypatch.setattr("matches.tasks.fetch_match_hype_data", lambda m: None)
    monkeypatch.setattr("matches.tasks.time.sleep", lambda s: sleep_calls.append(s))

    prefetch_upcoming_hype_data()

    assert len(sleep_calls) == 2
    assert all(s == 6 for s in sleep_calls)


class SimpleChannelLayer:
    def __init__(self, sent):
        self.sent = sent

    async def group_send(self, group, message):
        self.sent.append((group, message))
