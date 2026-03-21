from decimal import Decimal
from unittest.mock import Mock

import pytest

from betting.models import BetSlip, Odds
from betting.tasks import generate_odds, settle_match_bets
from betting.tests.factories import BetSlipFactory, UserBalanceFactory
from matches.models import Match
from matches.tests.factories import MatchFactory, StandingFactory, TeamFactory

pytestmark = pytest.mark.django_db


def test_generate_odds_creates_house_odds_for_upcoming_matches():
    home = TeamFactory(name="Arsenal FC")
    away = TeamFactory(name="Chelsea FC")
    StandingFactory(team=home, position=2, points=60, played=30)
    StandingFactory(team=away, position=5, points=50, played=30)
    MatchFactory(home_team=home, away_team=away, status=Match.Status.SCHEDULED)

    generate_odds.run()

    assert Odds.objects.filter(bookmaker="House").count() == 1
    odds = Odds.objects.get(bookmaker="House")
    assert odds.home_win > Decimal("1.00")
    assert odds.draw > Decimal("1.00")
    assert odds.away_win > Decimal("1.00")


def test_generate_odds_updates_existing_house_odds():
    home = TeamFactory(name="Liverpool FC")
    away = TeamFactory(name="Everton FC")
    StandingFactory(team=home, position=1, points=70, played=30)
    StandingFactory(team=away, position=15, points=30, played=30)
    match = MatchFactory(home_team=home, away_team=away, status=Match.Status.SCHEDULED)

    # Run twice — second should update, not create duplicate
    generate_odds.run()
    generate_odds.run()

    assert Odds.objects.filter(match=match, bookmaker="House").count() == 1


def test_generate_odds_retries_on_failure(monkeypatch):
    retry = Mock(side_effect=RuntimeError("retry"))
    monkeypatch.setattr(
        "betting.tasks.generate_all_upcoming_odds",
        Mock(side_effect=ValueError("boom")),
    )
    generate_odds.push_request(retries=1)
    monkeypatch.setattr(generate_odds, "retry", retry)

    try:
        with pytest.raises(RuntimeError, match="retry"):
            generate_odds.run()
    finally:
        generate_odds.pop_request()

    assert retry.call_args.kwargs["countdown"] == 240


def test_settle_match_bets_returns_when_match_missing():
    settle_match_bets.run(999999)


def test_settle_match_bets_returns_when_no_pending_bets():
    match = MatchFactory(status=Match.Status.FINISHED, home_score=1, away_score=0)

    settle_match_bets.run(match.pk)


def test_settle_match_bets_voids_and_refunds_cancelled_match():
    match = MatchFactory(status=Match.Status.CANCELLED)
    winning_user = UserBalanceFactory(balance="50.00").user
    bet = BetSlipFactory(user=winning_user, match=match, stake="12.00")

    settle_match_bets.run(match.pk)

    bet.refresh_from_db()
    winning_user.balance.refresh_from_db()

    assert bet.status == BetSlip.Status.VOID
    assert bet.payout == Decimal("12.00")
    assert winning_user.balance.balance == Decimal("62.00")


def test_settle_match_bets_returns_for_non_finished_match():
    match = MatchFactory(status=Match.Status.IN_PLAY, home_score=1, away_score=0)
    bet = BetSlipFactory(match=match)

    settle_match_bets.run(match.pk)
    bet.refresh_from_db()

    assert bet.status == BetSlip.Status.PENDING


def test_settle_match_bets_returns_when_finished_match_has_no_scores():
    match = MatchFactory(status=Match.Status.FINISHED, home_score=None, away_score=None)
    bet = BetSlipFactory(match=match)

    settle_match_bets.run(match.pk)
    bet.refresh_from_db()

    assert bet.status == BetSlip.Status.PENDING


def test_settle_match_bets_marks_winners_and_losers_and_updates_balances():
    match = MatchFactory(status=Match.Status.FINISHED, home_score=3, away_score=1)
    winner_balance = UserBalanceFactory(balance="100.00")
    loser_balance = UserBalanceFactory(balance="80.00")
    winner = BetSlipFactory(
        user=winner_balance.user,
        match=match,
        selection=BetSlip.Selection.HOME_WIN,
        odds_at_placement="2.50",
        stake="10.00",
    )
    loser = BetSlipFactory(
        user=loser_balance.user,
        match=match,
        selection=BetSlip.Selection.DRAW,
        odds_at_placement="3.10",
        stake="5.00",
    )

    settle_match_bets.run(match.pk)

    winner.refresh_from_db()
    loser.refresh_from_db()
    winner_balance.refresh_from_db()
    loser_balance.refresh_from_db()

    assert winner.status == BetSlip.Status.WON
    assert winner.payout == Decimal("25.00")
    assert loser.status == BetSlip.Status.LOST
    assert loser.payout == Decimal("0.00")
    assert winner_balance.balance == Decimal("125.00")
    assert loser_balance.balance == Decimal("80.00")
