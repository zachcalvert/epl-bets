from decimal import Decimal

import pytest

from betting.models import Bailout, Bankruptcy, BetSlip
from betting.tests.factories import BetSlipFactory, OddsFactory, UserBalanceFactory
from matches.tests.factories import MatchFactory, TeamFactory
from users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def test_odds_str_includes_bookmaker_match_and_prices():
    match = MatchFactory(
        home_team=TeamFactory(short_name="Arsenal"),
        away_team=TeamFactory(short_name="Chelsea"),
    )
    odds = OddsFactory(match=match, bookmaker="Bet365", home_win="2.15", draw="3.10", away_win="4.20")

    assert str(odds) == "Bet365: Arsenal vs Chelsea (2.15/3.10/4.20)"


def test_betslip_str_uses_selection_display():
    bet = BetSlipFactory(selection=BetSlip.Selection.DRAW, odds_at_placement="3.20")

    assert "Draw on" in str(bet)
    assert "@ 3.20" in str(bet)


def test_user_balance_str_formats_credits():
    balance = UserBalanceFactory(balance="875.50")

    assert str(balance) == f"{balance.user}: 875.50"


def test_bankruptcy_str_includes_user_pk_and_balance():
    user = UserFactory()
    bankruptcy = Bankruptcy.objects.create(user=user, balance_at_bankruptcy=Decimal("0.25"))

    assert f"bankruptcy #{bankruptcy.pk}" in str(bankruptcy)
    assert "0.25 cr" in str(bankruptcy)


def test_bailout_str_includes_user_and_amount():
    user = UserFactory()
    bankruptcy = Bankruptcy.objects.create(user=user, balance_at_bankruptcy=Decimal("0.00"))
    bailout = Bailout.objects.create(user=user, bankruptcy=bankruptcy, amount=Decimal("2500.00"))

    assert "bailout of 2500.00 cr" in str(bailout)
