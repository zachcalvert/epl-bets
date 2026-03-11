from decimal import Decimal

import pytest
from django.urls import reverse

from betting.models import BetSlip, UserBalance
from betting.tests.factories import BetSlipFactory, OddsFactory, UserBalanceFactory
from matches.models import Match
from matches.tests.factories import MatchFactory
from users.tests.factories import UserFactory


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


def test_odds_board_partial_uses_partial_template(client):
    response = client.get(reverse("betting:odds_partial"))

    assert response.status_code == 200
    assert any(
        template.name == "betting/partials/odds_board_body.html"
        for template in response.templates
    )


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
