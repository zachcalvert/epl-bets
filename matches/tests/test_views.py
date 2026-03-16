from datetime import datetime, time, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from betting.models import BetSlip
from betting.tests.factories import BetSlipFactory, OddsFactory, UserBalanceFactory
from matches.models import Match
from matches.tests.factories import MatchFactory, MatchStatsFactory, StandingFactory
from users.tests.factories import UserFactory
from website.transparency import get_events, match_scope, page_scope, record_event

pytestmark = pytest.mark.django_db


def test_dashboard_view_prefers_todays_matches_and_sets_best_odds(client):
    today = timezone.localdate()
    first_kickoff = timezone.make_aware(datetime.combine(today, time(12, 0)))
    second_kickoff = timezone.make_aware(datetime.combine(today, time(15, 0)))
    today_match = MatchFactory(kickoff=first_kickoff, matchday=5)
    later_match = MatchFactory(kickoff=second_kickoff, matchday=5)
    OddsFactory(match=today_match, bookmaker="A", home_win="2.50", draw="3.20", away_win="3.10")
    OddsFactory(match=today_match, bookmaker="B", home_win="2.10", draw="3.00", away_win="3.80")

    response = client.get(reverse("matches:dashboard"))

    matches = list(response.context["matches"])
    assert response.status_code == 200
    assert matches == [today_match, later_match]
    assert response.context["current_matchday"] == 5
    assert matches[0].best_home_odds == Decimal("2.10")
    assert matches[0].best_draw_odds == Decimal("3.00")
    assert matches[0].best_away_odds == Decimal("3.10")
    assert matches[1].best_home_odds is None


def test_dashboard_view_falls_back_to_next_matchday_when_no_matches_today(client):
    MatchFactory(kickoff=timezone.now() + timedelta(days=3), matchday=8)

    response = client.get(reverse("matches:dashboard"))

    assert response.status_code == 200
    assert response.context["current_matchday"] == 8
    assert len(response.context["matches"]) == 1


def test_dashboard_view_includes_top_10_leaderboard_entries_in_balance_order(client):
    for index in range(12):
        UserBalanceFactory(
            user__email=f"user{index}@example.com",
            balance=Decimal("1000.00") + Decimal(index),
        )

    response = client.get(reverse("matches:dashboard"))

    leaderboard = list(response.context["leaderboard"])
    assert response.status_code == 200
    assert len(leaderboard) == 10
    assert leaderboard[0].user.email == "user11@example.com"
    assert leaderboard[-1].user.email == "user2@example.com"
    assert leaderboard[0].display_identity == "us****@example.com"


def test_dashboard_view_leaderboard_prefers_display_name_when_present(client):
    UserBalanceFactory(
        user__email="user@example.com",
        user__display_name="Top Punter",
        balance="1250.00",
    )

    response = client.get(reverse("matches:dashboard"))

    assert response.status_code == 200
    assert response.context["leaderboard"][0].display_identity == "Top Punter"


def test_dashboard_view_leaderboard_breaks_ties_by_user_id(client):
    first = UserBalanceFactory(user__email="alpha@example.com", balance="1250.00")
    second = UserBalanceFactory(user__email="beta@example.com", balance="1250.00")

    response = client.get(reverse("matches:dashboard"))

    leaderboard = list(response.context["leaderboard"])
    assert leaderboard[:2] == [first, second]


def test_dashboard_view_includes_signed_in_user_rank_when_outside_top_10(client):
    for index in range(10):
        UserBalanceFactory(
            user__email=f"leader{index}@example.com",
            balance=Decimal("2000.00") - Decimal(index),
        )
    user = UserFactory(email="supporter@example.com")
    UserBalanceFactory(user=user, balance="1500.00")
    client.force_login(user)

    response = client.get(reverse("matches:dashboard"))

    assert response.context["user_rank"].rank == 11
    assert "You are currently #11" in response.content.decode()


def test_dashboard_view_omits_signed_in_user_rank_when_user_is_in_top_10(client):
    user = UserFactory(email="champion@example.com")
    UserBalanceFactory(user=user, balance="2500.00")
    client.force_login(user)

    response = client.get(reverse("matches:dashboard"))

    assert response.context["user_rank"] is None
    assert "Your rank" not in response.content.decode()


def test_dashboard_view_renders_under_the_hood_summary_from_recent_events(client):
    record_event(
        scope=page_scope("dashboard"),
        category="websocket",
        source="score_broadcast",
        action="score_broadcast",
        summary="Live score broadcast sent for match 42.",
        detail="Score changed from 0-0 to 1-0.",
        status="info",
    )

    response = client.get(reverse("matches:dashboard"))

    assert response.status_code == 200
    assert "Under the Hood" in response.content.decode()
    assert "Live score broadcast sent for match 42." in response.content.decode()


def test_dashboard_under_the_hood_partial_renders_recent_events(client):
    record_event(
        scope=page_scope("dashboard"),
        category="celery",
        source="fetch_live_scores",
        action="scores_synced",
        summary="Live score sync completed.",
        detail="Updated 2 matches and created 0 live records.",
        status="success",
    )

    response = client.get(
        reverse("matches:dashboard_under_the_hood"),
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert any(
        template.name == "matches/partials/dashboard_under_the_hood.html"
        for template in response.templates
    )
    assert "Recent dashboard events" in response.content.decode()
    assert "Live score sync completed." in response.content.decode()
    assert "See Architecture" in response.content.decode()


def test_dashboard_renders_matchday_tabs_with_active_id(client):
    MatchFactory(kickoff=timezone.now() + timedelta(days=1), matchday=15)

    response = client.get(reverse("matches:dashboard"), data={"matchday": "15"})

    assert response.status_code == 200
    content = response.content.decode()
    assert 'id="active-matchday"' in content
    assert 'id="matchday-tabs"' in content
    assert 'scrollIntoView' in content


def test_dashboard_returns_partial_for_htmx_and_invalid_matchday_falls_back(client):
    upcoming = MatchFactory(kickoff=timezone.now() + timedelta(days=1), matchday=9)
    OddsFactory(match=upcoming, home_win="1.95", draw="3.20", away_win="4.30")

    response = client.get(
        reverse("matches:dashboard"),
        data={"matchday": "not-a-number"},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert any(
        template.name == "matches/partials/fixture_list_htmx.html"
        for template in response.templates
    )
    assert response.context["matchday"] == 9
    assert response.context["matches"][0].best_home_odds == Decimal("1.95")


def test_dashboard_htmx_response_includes_oob_matchday_tabs(client):
    MatchFactory(kickoff=timezone.now() + timedelta(days=1), matchday=20)

    response = client.get(
        reverse("matches:dashboard"),
        data={"matchday": "20"},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert response.context["current_matchday"] == 20
    content = response.content.decode()
    assert 'hx-swap-oob="outerHTML"' in content
    assert 'id="matchday-tabs"' in content
    assert 'id="active-matchday"' in content
    # The active tab button should link to matchday 20
    assert '?matchday=20' in content[content.index('id="active-matchday"') - 200 : content.index('id="active-matchday"')]


def test_league_table_view_orders_current_season_standings(client):
    first = StandingFactory(position=2)
    second = StandingFactory(position=1)

    response = client.get(reverse("matches:table"))

    standings = list(response.context["standings"])
    assert response.status_code == 200
    assert standings == [second, first]
    assert response.context["season"] == "2025"


def test_match_detail_view_includes_best_odds_and_form_for_authenticated_user(client):
    match = MatchFactory()
    OddsFactory(match=match, bookmaker="A", home_win="2.60", draw="3.40", away_win="2.90")
    OddsFactory(match=match, bookmaker="B", home_win="2.20", draw="3.10", away_win="3.20")
    user = UserFactory()
    client.force_login(user)

    response = client.get(reverse("matches:match_detail", args=[match.pk]))

    assert response.status_code == 200
    assert response.context["best_home"] == Decimal("2.20")
    assert response.context["best_draw"] == Decimal("3.10")
    assert response.context["best_away"] == Decimal("2.90")
    assert "form" in response.context


def test_match_detail_view_renders_under_the_hood_summary_from_match_events(client):
    match = MatchFactory()
    record_event(
        scope=match_scope(match.pk),
        category="betting",
        source="place_bet",
        action="bet_placed",
        summary="Bet placed on Arsenal vs Chelsea.",
        detail="Selection HOME_WIN at 2.10 for 10.00 credits.",
        status="success",
    )

    response = client.get(reverse("matches:match_detail", args=[match.pk]))

    assert response.status_code == 200
    assert "Under the Hood" in response.content.decode()
    assert "Bet placed on Arsenal vs Chelsea." in response.content.decode()


def test_match_detail_view_omits_form_for_anonymous_user(client):
    match = MatchFactory()

    response = client.get(reverse("matches:match_detail", args=[match.pk]))

    assert response.status_code == 200
    assert "form" not in response.context


def test_match_odds_partial_uses_partial_template(client):
    match = MatchFactory()

    response = client.get(reverse("matches:match_odds_partial", args=[match.pk]))

    assert response.status_code == 200
    assert any(
        template.name == "matches/partials/odds_table_body.html"
        for template in response.templates
    )
    assert get_events(match_scope(match.pk))[0]["action"] == "partial_refreshed"


def test_match_under_the_hood_partial_renders_match_scoped_events(client):
    match = MatchFactory()
    record_event(
        scope=match_scope(match.pk),
        category="websocket",
        source="score_broadcast",
        action="score_broadcast",
        summary=f"Live score broadcast sent for match {match.pk}.",
        detail="Score/state changed from (0, 0, 'IN_PLAY') to (1, 0, 'IN_PLAY').",
        status="info",
    )

    response = client.get(
        reverse("matches:match_under_the_hood", args=[match.pk]),
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert any(
        template.name == "matches/partials/match_under_the_hood.html"
        for template in response.templates
    )
    assert "Recent match events" in response.content.decode()
    assert f"Live score broadcast sent for match {match.pk}." in response.content.decode()


def test_leaderboard_partial_renders_partial_template_and_content(client):
    UserBalanceFactory(user__email="leader@example.com", balance="1400.00")

    response = client.get(
        reverse("matches:leaderboard_partial"),
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert any(
        template.name == "matches/partials/leaderboard.html"
        for template in response.templates
    )
    assert "le****@example.com" in response.content.decode()
    assert "leader@example.com" not in response.content.decode()
    assert get_events(page_scope("dashboard"))[0]["source"] == "leaderboard_partial"


def test_leaderboard_partial_renders_display_name_when_available(client):
    UserBalanceFactory(
        user__email="leader@example.com",
        user__display_name="Top Punter",
        balance="1400.00",
    )

    response = client.get(
        reverse("matches:leaderboard_partial"),
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert "Top Punter" in response.content.decode()
    assert "le****@example.com" not in response.content.decode()


def test_leaderboard_partial_shows_signed_in_user_rank_when_outside_top_10(client):
    for index in range(10):
        UserBalanceFactory(
            user__email=f"leader{index}@example.com",
            balance=Decimal("2000.00") - Decimal(index),
        )
    user = UserFactory(email="latecomer@example.com")
    UserBalanceFactory(user=user, balance="1500.00")
    client.force_login(user)

    response = client.get(
        reverse("matches:leaderboard_partial"),
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert "Your rank" in response.content.decode()
    assert "You are currently #11" in response.content.decode()


def test_leaderboard_partial_shows_empty_state_when_no_balances_exist(client):
    response = client.get(reverse("matches:leaderboard_partial"))

    assert response.status_code == 200
    assert "No leaderboard data yet" in response.content.decode()


def test_leaderboard_view_renders_all_users_in_balance_order(client):
    for index in range(12):
        UserBalanceFactory(
            user__email=f"player{index}@example.com",
            balance=Decimal("1000.00") + Decimal(index),
        )

    response = client.get(reverse("matches:leaderboard"))

    leaderboard = list(response.context["leaderboard"])
    assert response.status_code == 200
    assert len(leaderboard) == 12
    assert leaderboard[0].user.email == "player11@example.com"
    assert leaderboard[-1].user.email == "player0@example.com"


def test_leaderboard_view_shows_signed_in_user_rank_when_outside_top_10(client):
    for index in range(10):
        UserBalanceFactory(
            user__email=f"top{index}@example.com",
            balance=Decimal("2000.00") - Decimal(index),
        )
    user = UserFactory(email="latecomer@example.com")
    UserBalanceFactory(user=user, balance="1500.00")
    client.force_login(user)

    response = client.get(reverse("matches:leaderboard"))

    # All 11 users are visible in the full leaderboard, so the user is in it and
    # the separate "Your rank" card is not shown (user_rank is None)
    assert response.status_code == 200
    assert len(list(response.context["leaderboard"])) == 11
    assert response.context["user_rank"] is None


def test_leaderboard_view_shows_empty_state_when_no_balances_exist(client):
    response = client.get(reverse("matches:leaderboard"))

    assert response.status_code == 200
    assert "No leaderboard data yet" in response.content.decode()


# ---------------------------------------------------------------------------
# Match Hype Card
# ---------------------------------------------------------------------------


def test_match_detail_includes_hype_context_for_scheduled_match(client, monkeypatch):
    match = MatchFactory(status=Match.Status.SCHEDULED)
    stats = MatchStatsFactory(match=match)  # fresh — no API call needed
    monkeypatch.setattr("matches.views.fetch_match_hype_data", lambda m: stats)

    response = client.get(reverse("matches:match_status_card", args=[match.pk]))

    assert response.status_code == 200
    assert response.context["match_stats"] is stats


def test_match_detail_includes_hype_context_for_timed_match(client, monkeypatch):
    match = MatchFactory(status=Match.Status.TIMED)
    stats = MatchStatsFactory(match=match)
    monkeypatch.setattr("matches.views.fetch_match_hype_data", lambda m: stats)

    response = client.get(reverse("matches:match_status_card", args=[match.pk]))

    assert response.status_code == 200
    assert "match_stats" in response.context


def test_match_detail_omits_card_for_postponed_match(client):
    match = MatchFactory(status=Match.Status.POSTPONED)

    response = client.get(reverse("matches:match_detail", args=[match.pk]))

    assert response.status_code == 200
    assert not response.context["has_status_card"]


def test_match_detail_hype_card_renders_in_html_for_scheduled_match(client, monkeypatch):
    match = MatchFactory(status=Match.Status.SCHEDULED)
    stats = MatchStatsFactory(match=match)
    monkeypatch.setattr("matches.views.fetch_match_hype_data", lambda m: stats)

    response = client.get(reverse("matches:match_status_card", args=[match.pk]))

    assert response.status_code == 200
    assert "Match Preview" in response.content.decode()
    assert any(
        template.name == "matches/partials/hype_card.html"
        for template in response.templates
    )


def test_match_detail_hype_card_absent_for_finished_match(client, monkeypatch):
    match = MatchFactory(status=Match.Status.FINISHED, home_score=1, away_score=0)
    stats = MatchStatsFactory(match=match)
    monkeypatch.setattr("matches.views.fetch_match_hype_data", lambda m: stats)

    response = client.get(reverse("matches:match_status_card", args=[match.pk]))

    assert "Match Preview" not in response.content.decode()
    assert "Match Recap" in response.content.decode()


def test_match_detail_hype_context_includes_standings(client, monkeypatch):
    match = MatchFactory(status=Match.Status.SCHEDULED)
    home_standing = StandingFactory(team=match.home_team, season="2025", position=1, points=52)
    away_standing = StandingFactory(team=match.away_team, season="2025", position=4, points=41)
    stats = MatchStatsFactory(match=match)
    monkeypatch.setattr("matches.views.fetch_match_hype_data", lambda m: stats)

    response = client.get(reverse("matches:match_status_card", args=[match.pk]))

    assert response.context["home_standing"] == home_standing
    assert response.context["away_standing"] == away_standing


def test_match_detail_hype_context_sentiment_none_when_no_bets(client, monkeypatch):
    match = MatchFactory(status=Match.Status.SCHEDULED)
    stats = MatchStatsFactory(match=match)
    monkeypatch.setattr("matches.views.fetch_match_hype_data", lambda m: stats)

    response = client.get(reverse("matches:match_status_card", args=[match.pk]))

    assert response.context["sentiment"] is None


def test_match_detail_hype_context_computes_sentiment_from_betslips(client, monkeypatch):
    match = MatchFactory(status=Match.Status.SCHEDULED)
    stats = MatchStatsFactory(match=match)
    monkeypatch.setattr("matches.views.fetch_match_hype_data", lambda m: stats)
    # 2 HOME_WIN, 1 DRAW, 1 AWAY_WIN = 50% / 25% / 25%
    BetSlipFactory(match=match, selection=BetSlip.Selection.HOME_WIN)
    BetSlipFactory(match=match, selection=BetSlip.Selection.HOME_WIN)
    BetSlipFactory(match=match, selection=BetSlip.Selection.DRAW)
    BetSlipFactory(match=match, selection=BetSlip.Selection.AWAY_WIN)

    response = client.get(reverse("matches:match_status_card", args=[match.pk]))

    sentiment = response.context["sentiment"]
    assert sentiment["total"] == 4
    assert sentiment["home_pct"] == 50
    assert sentiment["draw_pct"] == 25
    assert sentiment["away_pct"] == 25
    assert sentiment["most_popular"] == "Home Win"


def test_match_detail_sentiment_percentages_sum_to_100(client, monkeypatch):
    """away_pct is derived (100 - home - draw) so rounding never loses or gains a percent."""
    match = MatchFactory(status=Match.Status.SCHEDULED)
    stats = MatchStatsFactory(match=match)
    monkeypatch.setattr("matches.views.fetch_match_hype_data", lambda m: stats)
    # 1 of each → 33%/33%/34% (derived away avoids drift)
    BetSlipFactory(match=match, selection=BetSlip.Selection.HOME_WIN)
    BetSlipFactory(match=match, selection=BetSlip.Selection.DRAW)
    BetSlipFactory(match=match, selection=BetSlip.Selection.AWAY_WIN)

    response = client.get(reverse("matches:match_status_card", args=[match.pk]))

    sentiment = response.context["sentiment"]
    assert sentiment["home_pct"] + sentiment["draw_pct"] + sentiment["away_pct"] == 100


# ---------------------------------------------------------------------------
# Live Match Card
# ---------------------------------------------------------------------------


def test_match_detail_live_card_renders_for_in_play_match(client, monkeypatch):
    match = MatchFactory(status=Match.Status.IN_PLAY, home_score=1, away_score=0)
    stats = MatchStatsFactory(match=match)
    monkeypatch.setattr("matches.views.fetch_match_hype_data", lambda m: stats)

    response = client.get(reverse("matches:match_status_card", args=[match.pk]))

    assert response.status_code == 200
    assert "Match Centre" in response.content.decode()
    assert any(
        template.name == "matches/partials/live_card.html"
        for template in response.templates
    )


def test_match_detail_live_card_renders_for_paused_match(client, monkeypatch):
    match = MatchFactory(status=Match.Status.PAUSED, home_score=0, away_score=0)
    stats = MatchStatsFactory(match=match)
    monkeypatch.setattr("matches.views.fetch_match_hype_data", lambda m: stats)

    response = client.get(reverse("matches:match_status_card", args=[match.pk]))

    assert response.status_code == 200
    content = response.content.decode()
    assert "Match Centre" in content
    assert "HT" in content


def test_match_detail_live_card_includes_sentiment_and_standings(client, monkeypatch):
    match = MatchFactory(status=Match.Status.IN_PLAY, home_score=0, away_score=0)
    stats = MatchStatsFactory(match=match)
    home_standing = StandingFactory(team=match.home_team, season="2025", position=3, points=45)
    away_standing = StandingFactory(team=match.away_team, season="2025", position=7, points=32)
    monkeypatch.setattr("matches.views.fetch_match_hype_data", lambda m: stats)
    BetSlipFactory(match=match, selection=BetSlip.Selection.HOME_WIN)

    response = client.get(reverse("matches:match_status_card", args=[match.pk]))

    assert response.context["home_standing"] == home_standing
    assert response.context["away_standing"] == away_standing
    assert response.context["sentiment"]["total"] == 1


# ---------------------------------------------------------------------------
# Match Recap Card
# ---------------------------------------------------------------------------


def test_match_detail_recap_card_renders_for_finished_match(client, monkeypatch):
    match = MatchFactory(status=Match.Status.FINISHED, home_score=2, away_score=1)
    stats = MatchStatsFactory(match=match)
    monkeypatch.setattr("matches.views.fetch_match_hype_data", lambda m: stats)

    response = client.get(reverse("matches:match_status_card", args=[match.pk]))

    assert response.status_code == 200
    assert "Match Recap" in response.content.decode()
    assert any(
        template.name == "matches/partials/recap_card.html"
        for template in response.templates
    )


def test_match_detail_recap_card_includes_result_context(client, monkeypatch):
    match = MatchFactory(status=Match.Status.FINISHED, home_score=3, away_score=0)
    stats = MatchStatsFactory(match=match)
    monkeypatch.setattr("matches.views.fetch_match_hype_data", lambda m: stats)

    response = client.get(reverse("matches:match_status_card", args=[match.pk]))

    result_context = response.context["result_context"]
    assert "3-0" in result_context["score_line"]
    assert result_context["is_upset"] is False


def test_match_detail_recap_card_detects_upset(client, monkeypatch):
    match = MatchFactory(status=Match.Status.FINISHED, home_score=0, away_score=1)
    stats = MatchStatsFactory(match=match)
    # Away team in worse position wins → upset
    StandingFactory(team=match.home_team, season="2025", position=2, points=50)
    StandingFactory(team=match.away_team, season="2025", position=15, points=20)
    monkeypatch.setattr("matches.views.fetch_match_hype_data", lambda m: stats)

    response = client.get(reverse("matches:match_status_card", args=[match.pk]))

    result_context = response.context["result_context"]
    assert result_context["is_upset"] is True
    assert "upset" in result_context["headline"].lower()


def test_match_detail_recap_card_draw_headline(client, monkeypatch):
    match = MatchFactory(status=Match.Status.FINISHED, home_score=1, away_score=1)
    stats = MatchStatsFactory(match=match)
    monkeypatch.setattr("matches.views.fetch_match_hype_data", lambda m: stats)

    response = client.get(reverse("matches:match_status_card", args=[match.pk]))

    result_context = response.context["result_context"]
    assert "Honours even" in result_context["headline"]
    assert response.context["actual_result"] == "DRAW"


def test_match_detail_recap_card_betting_outcome(client, monkeypatch):
    match = MatchFactory(status=Match.Status.FINISHED, home_score=2, away_score=0)
    stats = MatchStatsFactory(match=match)
    monkeypatch.setattr("matches.views.fetch_match_hype_data", lambda m: stats)
    BetSlipFactory(match=match, selection=BetSlip.Selection.HOME_WIN, status=BetSlip.Status.WON, stake="10.00", payout="21.00")
    BetSlipFactory(match=match, selection=BetSlip.Selection.DRAW, status=BetSlip.Status.LOST, stake="10.00")
    BetSlipFactory(match=match, selection=BetSlip.Selection.AWAY_WIN, status=BetSlip.Status.LOST, stake="5.00")

    response = client.get(reverse("matches:match_status_card", args=[match.pk]))

    outcome = response.context["betting_outcome"]
    assert outcome["total_bets"] == 3
    assert outcome["winners"] == 1
    assert outcome["win_pct"] == 33
    assert outcome["total_won_payout"] == Decimal("21.00")


def test_match_detail_recap_card_no_betting_outcome_when_no_bets(client, monkeypatch):
    match = MatchFactory(status=Match.Status.FINISHED, home_score=1, away_score=0)
    stats = MatchStatsFactory(match=match)
    monkeypatch.setattr("matches.views.fetch_match_hype_data", lambda m: stats)

    response = client.get(reverse("matches:match_status_card", args=[match.pk]))

    assert response.context["betting_outcome"] is None


def test_match_detail_recap_card_sentiment_vs_reality(client, monkeypatch):
    match = MatchFactory(status=Match.Status.FINISHED, home_score=2, away_score=1)
    stats = MatchStatsFactory(match=match)
    monkeypatch.setattr("matches.views.fetch_match_hype_data", lambda m: stats)
    BetSlipFactory(match=match, selection=BetSlip.Selection.HOME_WIN)
    BetSlipFactory(match=match, selection=BetSlip.Selection.HOME_WIN)
    BetSlipFactory(match=match, selection=BetSlip.Selection.DRAW)

    response = client.get(reverse("matches:match_status_card", args=[match.pk]))

    assert response.context["actual_result"] == "HOME_WIN"
    assert response.context["actual_result_label"] == "Home Win"
    content = response.content.decode()
    assert "Sentiment vs Reality" in content
    assert "Community got it right" in content

