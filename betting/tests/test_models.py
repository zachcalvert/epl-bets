import pytest

from betting.models import BetSlip
from betting.tests.factories import BetSlipFactory, OddsFactory, UserBalanceFactory
from matches.tests.factories import MatchFactory, TeamFactory

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

    assert str(balance) == f"{balance.user}: 875.50 credits"
