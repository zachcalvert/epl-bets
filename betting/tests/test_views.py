from decimal import Decimal

import pytest
from django.urls import reverse

from betting.models import BetSlip, UserBalance
from betting.tests.factories import BetSlipFactory, OddsFactory, UserBalanceFactory
from matches.models import Match
from matches.tests.factories import MatchFactory
from users.tests.factories import UserFactory
from website.transparency import get_events, match_scope, page_scope, record_event

pytestmark = pytest.mark.django_db


def test_odds_board_view_lists_upcoming_matches_with_best_odds(client):
    match = MatchFactory(status=Match.Status.SCHEDULED)
    MatchFactory(status=Match.Status.FINISHED)
    OddsFactory(match=match, bookmaker="A", home_win="2.40", draw="3.40", away_win="3.30")
    OddsFactory(match=match, bookmaker="B", home_win="2.10", draw="3.10", away_win="3.80")

    response = client.get(reverse("betting:odds"))

    matches = list(response.context["matches"])
    assert response.status_code == 200
    assert matches == [match]
    assert matches[0].best_home_odds == Decimal("2.10")
    assert matches[0].best_draw_odds == Decimal("3.10")
    assert matches[0].best_away_odds == Decimal("3.30")


def test_odds_board_view_renders_under_the_hood_summary_from_recent_events(client):
    record_event(
        scope=page_scope("odds_board"),
        category="celery",
        source="fetch_odds",
        action="odds_synced",
        summary="Odds sync completed.",
        detail="Created 3 bookmaker rows and updated 4 existing rows.",
        status="success",
    )

    response = client.get(reverse("betting:odds"))

    assert response.status_code == 200
    assert "Under the Hood" in response.content.decode()
    assert "Odds sync completed." in response.content.decode()


def test_odds_board_partial_uses_partial_template(client):
    response = client.get(reverse("betting:odds_partial"))

    assert response.status_code == 200
    assert any(
        template.name == "betting/partials/odds_board_body.html"
        for template in response.templates
    )
    assert get_events(page_scope("odds_board"))[0]["source"] == "odds_board_partial"


def test_odds_board_under_the_hood_partial_renders_recent_events(client):
    record_event(
        scope=page_scope("odds_board"),
        category="htmx",
        source="odds_board_partial",
        action="partial_refreshed",
        summary="Odds board refreshed with the latest stored prices.",
        detail="Rendered 8 upcoming matches.",
        status="info",
    )

    response = client.get(
        reverse("betting:odds_under_the_hood"),
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert any(
        template.name == "betting/partials/odds_board_under_the_hood.html"
        for template in response.templates
    )
    assert "Recent odds-board events" in response.content.decode()
    assert "Odds board refreshed with the latest stored prices." in response.content.decode()


def test_place_bet_redirects_anonymous_user_to_login(client):
    match = MatchFactory()

    response = client.post(reverse("betting:place_bet", args=[match.pk]))

    assert response.status_code == 302
    assert reverse("website:login") in response.url


def test_place_bet_rejects_non_upcoming_match(client):
    user = UserFactory()
    match = MatchFactory(status=Match.Status.FINISHED)
    client.force_login(user)

    response = client.post(reverse("betting:place_bet", args=[match.pk]), data={})

    assert response.status_code == 200
    assert "no longer accepting bets" in response.content.decode()


def test_place_bet_rerenders_invalid_form(client):
    user = UserFactory()
    match = MatchFactory()
    client.force_login(user)

    response = client.post(
        reverse("betting:place_bet", args=[match.pk]),
        data={"selection": BetSlip.Selection.HOME_WIN, "stake": "0.10"},
    )

    assert response.status_code == 200
    assert response.context["form"].errors["stake"] == [
        "Ensure this value is greater than or equal to 0.50."
    ]


def test_place_bet_returns_error_when_no_odds_available(client):
    user = UserFactory()
    match = MatchFactory()
    client.force_login(user)

    response = client.post(
        reverse("betting:place_bet", args=[match.pk]),
        data={"selection": BetSlip.Selection.HOME_WIN, "stake": "10.00"},
    )

    assert response.status_code == 200
    assert "No odds available for this match." in response.content.decode()


def test_place_bet_returns_error_for_insufficient_balance(client):
    user = UserFactory()
    UserBalanceFactory(user=user, balance="5.00")
    match = MatchFactory()
    OddsFactory(match=match, home_win="2.25")
    client.force_login(user)

    response = client.post(
        reverse("betting:place_bet", args=[match.pk]),
        data={"selection": BetSlip.Selection.HOME_WIN, "stake": "10.00"},
    )

    assert response.status_code == 200
    assert "Insufficient balance. You have 5.00 credits." in response.content.decode()
    assert BetSlip.objects.count() == 0


def test_place_bet_creates_bet_and_deducts_balance(client):
    user = UserFactory()
    balance = UserBalanceFactory(user=user, balance="100.00")
    match = MatchFactory()
    OddsFactory(match=match, bookmaker="A", home_win="2.50")
    OddsFactory(match=match, bookmaker="B", home_win="2.10")
    client.force_login(user)

    response = client.post(
        reverse("betting:place_bet", args=[match.pk]),
        data={"selection": BetSlip.Selection.HOME_WIN, "stake": "10.00"},
    )

    bet = BetSlip.objects.get()
    balance.refresh_from_db()

    assert response.status_code == 200
    assert bet.odds_at_placement == Decimal("2.10")
    assert balance.balance == Decimal("90.00")
    assert "21.00" in response.content.decode()
    assert get_events(match_scope(match.pk))[0]["action"] == "bet_placed"


def test_place_bet_auto_creates_balance_when_missing(client):
    user = UserFactory()
    match = MatchFactory()
    OddsFactory(match=match, draw="3.40")
    client.force_login(user)

    client.post(
        reverse("betting:place_bet", args=[match.pk]),
        data={"selection": BetSlip.Selection.DRAW, "stake": "25.00"},
    )

    assert UserBalance.objects.get(user=user).balance == Decimal("975.00")


def test_my_bets_view_calculates_totals_and_default_balance(client):
    user = UserFactory()
    won_bet = BetSlipFactory(user=user, stake="10.00", payout="21.00", status=BetSlip.Status.WON)
    lost_bet = BetSlipFactory(user=user, stake="5.00", payout="0.00", status=BetSlip.Status.LOST)
    client.force_login(user)

    response = client.get(reverse("betting:my_bets"))

    bets = list(response.context["bets"])
    assert response.status_code == 200
    assert bets == [lost_bet, won_bet]
    assert response.context["total_staked"] == Decimal("15.00")
    assert response.context["total_payout"] == Decimal("21.00")
    assert response.context["net_pnl"] == Decimal("6.00")
    assert response.context["current_balance"] == Decimal("1000.00")


def test_my_bets_view_includes_rank_summary_when_user_is_outside_top_10(client):
    for index in range(10):
        UserBalanceFactory(
            user__email=f"leader{index}@example.com",
            balance=Decimal("2000.00") - Decimal(index),
        )
    user = UserFactory(email="climber@example.com")
    UserBalanceFactory(user=user, balance="1500.00")
    client.force_login(user)

    response = client.get(reverse("betting:my_bets"))

    assert response.status_code == 200
    assert response.context["user_rank"].rank == 11
    assert "Your leaderboard rank" in response.content.decode()
    assert "You are currently #11" in response.content.decode()
    assert "cl*****@example.com" in response.content.decode()


def test_my_bets_view_shows_rank_summary_when_user_is_in_top_10(client):
    user = UserFactory(email="winner@example.com")
    UserBalanceFactory(user=user, balance="2500.00")
    client.force_login(user)

    response = client.get(reverse("betting:my_bets"))

    assert response.status_code == 200
    assert response.context["user_rank"].rank == 1
    assert "Your leaderboard rank" in response.content.decode()
    assert "You are currently #1" in response.content.decode()


def test_quick_bet_form_view_returns_initial_selection(client):
    user = UserFactory()
    match = MatchFactory()
    client.force_login(user)

    response = client.get(
        reverse("betting:quick_bet_form", args=[match.pk]),
        data={"selection": BetSlip.Selection.AWAY_WIN},
    )

    assert response.status_code == 200
    assert response.context["selection"] == BetSlip.Selection.AWAY_WIN
    assert response.context["form"].initial["selection"] == BetSlip.Selection.AWAY_WIN
