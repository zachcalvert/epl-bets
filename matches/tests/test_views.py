from datetime import datetime, time, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from betting.tests.factories import OddsFactory, UserBalanceFactory
from matches.tests.factories import MatchFactory, StandingFactory
from users.tests.factories import UserFactory
from website.transparency import get_events, match_scope, page_scope
from website.transparency import record_event

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
    assert leaderboard[0].display_email == "us****@example.com"


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


def test_fixtures_view_returns_partial_for_htmx_and_invalid_matchday_falls_back(client):
    upcoming = MatchFactory(kickoff=timezone.now() + timedelta(days=1), matchday=9)
    OddsFactory(match=upcoming, home_win="1.95", draw="3.20", away_win="4.30")

    response = client.get(
        reverse("matches:fixtures"),
        data={"matchday": "not-a-number"},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert any(
        template.name == "matches/partials/fixture_list.html"
        for template in response.templates
    )
    assert response.context["matchday"] == 9
    assert response.context["matches"][0].best_home_odds == Decimal("1.95")


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
