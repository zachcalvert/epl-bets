from decimal import Decimal

import pytest

from betting.models import BetSlip, Parlay, ParlayLeg, UserBalance
from betting.tasks import settle_match_bets, settle_parlay_legs, _evaluate_parlay
from betting.tests.factories import (
    ParlayFactory,
    ParlayLegFactory,
    UserBalanceFactory,
)
from matches.models import Match
from matches.tests.factories import MatchFactory

pytestmark = pytest.mark.django_db


def _make_parlay(user, balance="100.00", stake="10.00", combined_odds="6.00"):
    UserBalanceFactory(user=user, balance=balance)
    return ParlayFactory(user=user, stake=stake, combined_odds=combined_odds)


# ── settle_parlay_legs ─────────────────────────────────────────────────────────

class TestSettleParlayLegs:
    def test_leg_won_when_selection_matches(self):
        match = MatchFactory(status=Match.Status.FINISHED, home_score=2, away_score=0)
        parlay = ParlayFactory()
        leg = ParlayLegFactory(parlay=parlay, match=match, selection=BetSlip.Selection.HOME_WIN)

        settle_parlay_legs(match, BetSlip.Selection.HOME_WIN)

        leg.refresh_from_db()
        assert leg.status == ParlayLeg.Status.WON

    def test_leg_lost_when_selection_doesnt_match(self):
        match = MatchFactory(status=Match.Status.FINISHED, home_score=2, away_score=0)
        parlay = ParlayFactory()
        leg = ParlayLegFactory(parlay=parlay, match=match, selection=BetSlip.Selection.DRAW)

        settle_parlay_legs(match, BetSlip.Selection.HOME_WIN)

        leg.refresh_from_db()
        assert leg.status == ParlayLeg.Status.LOST

    def test_leg_voided_when_winning_selection_is_none(self):
        match = MatchFactory(status=Match.Status.CANCELLED)
        parlay = ParlayFactory()
        leg = ParlayLegFactory(parlay=parlay, match=match, selection=BetSlip.Selection.HOME_WIN)

        settle_parlay_legs(match, winning_selection=None)

        leg.refresh_from_db()
        assert leg.status == ParlayLeg.Status.VOID

    def test_only_pending_legs_are_settled(self):
        match = MatchFactory(status=Match.Status.FINISHED, home_score=1, away_score=0)
        parlay = ParlayFactory()
        pending_leg = ParlayLegFactory(parlay=parlay, match=match, selection=BetSlip.Selection.HOME_WIN)
        already_won_leg = ParlayLegFactory(
            parlay=parlay,
            match=MatchFactory(),
            selection=BetSlip.Selection.HOME_WIN,
            status=ParlayLeg.Status.WON,
        )

        settle_parlay_legs(match, BetSlip.Selection.HOME_WIN)

        pending_leg.refresh_from_db()
        already_won_leg.refresh_from_db()
        assert pending_leg.status == ParlayLeg.Status.WON
        assert already_won_leg.status == ParlayLeg.Status.WON  # unchanged


# ── _evaluate_parlay ───────────────────────────────────────────────────────────

class TestEvaluateParlay:
    def test_all_legs_won_pays_out(self):
        user = UserBalanceFactory(balance="100.00").user
        parlay = ParlayFactory(user=user, stake="10.00", combined_odds="3.00")
        m1 = MatchFactory()
        m2 = MatchFactory()
        ParlayLegFactory(parlay=parlay, match=m1, status=ParlayLeg.Status.WON, odds_at_placement="1.50")
        ParlayLegFactory(parlay=parlay, match=m2, status=ParlayLeg.Status.WON, odds_at_placement="2.00")

        _evaluate_parlay(parlay.pk)

        parlay.refresh_from_db()
        user.balance.refresh_from_db()
        assert parlay.status == Parlay.Status.WON
        assert parlay.payout == Decimal("30.00")  # 10 * 3.00
        assert user.balance.balance == Decimal("130.00")

    def test_any_leg_lost_kills_parlay(self):
        user = UserBalanceFactory(balance="100.00").user
        parlay = ParlayFactory(user=user, stake="10.00", combined_odds="6.00")
        ParlayLegFactory(parlay=parlay, match=MatchFactory(), status=ParlayLeg.Status.WON)
        ParlayLegFactory(parlay=parlay, match=MatchFactory(), status=ParlayLeg.Status.LOST)

        _evaluate_parlay(parlay.pk)

        parlay.refresh_from_db()
        user.balance.refresh_from_db()
        assert parlay.status == Parlay.Status.LOST
        assert parlay.payout == Decimal("0")
        assert user.balance.balance == Decimal("100.00")  # no payout

    def test_still_pending_legs_keeps_parlay_pending(self):
        user = UserBalanceFactory(balance="100.00").user
        parlay = ParlayFactory(user=user, stake="10.00", combined_odds="6.00")
        ParlayLegFactory(parlay=parlay, match=MatchFactory(), status=ParlayLeg.Status.WON)
        ParlayLegFactory(parlay=parlay, match=MatchFactory(), status=ParlayLeg.Status.PENDING)

        _evaluate_parlay(parlay.pk)

        parlay.refresh_from_db()
        assert parlay.status == Parlay.Status.PENDING
        user.balance.refresh_from_db()
        assert user.balance.balance == Decimal("100.00")

    def test_all_legs_voided_refunds_stake(self):
        user = UserBalanceFactory(balance="100.00").user
        parlay = ParlayFactory(user=user, stake="10.00", combined_odds="6.00")
        ParlayLegFactory(parlay=parlay, match=MatchFactory(), status=ParlayLeg.Status.VOID)
        ParlayLegFactory(parlay=parlay, match=MatchFactory(), status=ParlayLeg.Status.VOID)

        _evaluate_parlay(parlay.pk)

        parlay.refresh_from_db()
        user.balance.refresh_from_db()
        assert parlay.status == Parlay.Status.VOID
        assert parlay.payout == Decimal("10.00")
        assert user.balance.balance == Decimal("110.00")  # refunded

    def test_won_and_void_mix_recalculates_odds(self):
        """A voided leg is removed and the remaining legs' combined odds are used."""
        user = UserBalanceFactory(balance="100.00").user
        parlay = ParlayFactory(user=user, stake="10.00", combined_odds="6.00")
        ParlayLegFactory(
            parlay=parlay, match=MatchFactory(), status=ParlayLeg.Status.WON, odds_at_placement="2.00"
        )
        ParlayLegFactory(
            parlay=parlay, match=MatchFactory(), status=ParlayLeg.Status.WON, odds_at_placement="3.00"
        )
        ParlayLegFactory(
            parlay=parlay, match=MatchFactory(), status=ParlayLeg.Status.VOID, odds_at_placement="5.00"
        )

        _evaluate_parlay(parlay.pk)

        parlay.refresh_from_db()
        user.balance.refresh_from_db()
        assert parlay.status == Parlay.Status.WON
        # Recalculated: 2.00 * 3.00 = 6.00 (void leg excluded)
        assert parlay.combined_odds == Decimal("6.00")
        assert parlay.payout == Decimal("60.00")
        assert user.balance.balance == Decimal("160.00")

    def test_payout_capped_at_max_payout(self):
        user = UserBalanceFactory(balance="1000.00").user
        parlay = ParlayFactory(user=user, stake="1000.00", combined_odds="999.00", max_payout="50000.00")
        ParlayLegFactory(
            parlay=parlay, match=MatchFactory(), status=ParlayLeg.Status.WON, odds_at_placement="999.00"
        )

        _evaluate_parlay(parlay.pk)

        parlay.refresh_from_db()
        user.balance.refresh_from_db()
        assert parlay.status == Parlay.Status.WON
        assert parlay.payout == Decimal("50000.00")  # capped
        assert user.balance.balance == Decimal("51000.00")

    def test_already_settled_parlay_is_skipped(self):
        user = UserBalanceFactory(balance="100.00").user
        parlay = ParlayFactory(user=user, stake="10.00", status=Parlay.Status.WON, payout="60.00")
        ParlayLegFactory(parlay=parlay, match=MatchFactory(), status=ParlayLeg.Status.WON)

        _evaluate_parlay(parlay.pk)

        parlay.refresh_from_db()
        user.balance.refresh_from_db()
        assert parlay.status == Parlay.Status.WON
        assert parlay.payout == Decimal("60.00")  # unchanged
        assert user.balance.balance == Decimal("100.00")  # not credited again

    def test_nonexistent_parlay_does_not_raise(self):
        _evaluate_parlay(9999999)  # should not raise


# ── Integration: settle_match_bets triggers parlay settlement ─────────────────

class TestSettleMatchBetsTriggersParlayLegs:
    def test_settled_match_also_settles_parlay_legs(self):
        user = UserBalanceFactory(balance="100.00").user
        match = MatchFactory(status=Match.Status.FINISHED, home_score=1, away_score=0)
        match2 = MatchFactory(status=Match.Status.SCHEDULED)

        parlay = ParlayFactory(user=user, stake="10.00", combined_odds="4.00")
        leg1 = ParlayLegFactory(
            parlay=parlay, match=match, selection=BetSlip.Selection.HOME_WIN, odds_at_placement="2.00"
        )
        leg2 = ParlayLegFactory(
            parlay=parlay, match=match2, selection=BetSlip.Selection.DRAW, odds_at_placement="2.00",
            status=ParlayLeg.Status.PENDING,
        )

        settle_match_bets.run(match.pk)

        leg1.refresh_from_db()
        leg2.refresh_from_db()
        parlay.refresh_from_db()

        assert leg1.status == ParlayLeg.Status.WON
        assert leg2.status == ParlayLeg.Status.PENDING  # other match not yet settled
        assert parlay.status == Parlay.Status.PENDING  # still one leg pending

    def test_cancelled_match_voids_parlay_leg(self):
        user = UserBalanceFactory(balance="100.00").user
        match = MatchFactory(status=Match.Status.CANCELLED)

        parlay = ParlayFactory(user=user, stake="10.00", combined_odds="2.00")
        leg = ParlayLegFactory(
            parlay=parlay, match=match, selection=BetSlip.Selection.HOME_WIN, odds_at_placement="2.00"
        )
        # Second leg already won
        ParlayLegFactory(
            parlay=parlay, match=MatchFactory(), selection=BetSlip.Selection.HOME_WIN,
            status=ParlayLeg.Status.WON, odds_at_placement="1.00"
        )

        settle_match_bets.run(match.pk)

        leg.refresh_from_db()
        parlay.refresh_from_db()

        assert leg.status == ParlayLeg.Status.VOID
        # Parlay should now be WON (1 won, 1 void — recalculate to 1.00, payout = 10 * 1 = 10)
        assert parlay.status == Parlay.Status.WON
