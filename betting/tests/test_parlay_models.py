from decimal import Decimal

import pytest

from betting.models import (
    PARLAY_MAX_LEGS,
    PARLAY_MAX_PAYOUT,
    PARLAY_MIN_LEGS,
    BetSlip,
    Parlay,
    ParlayLeg,
)
from betting.tests.factories import ParlayFactory, ParlayLegFactory, UserBalanceFactory
from matches.tests.factories import MatchFactory

pytestmark = pytest.mark.django_db


class TestParlayModel:
    def test_parlay_created_with_defaults(self):
        parlay = ParlayFactory()
        assert parlay.status == Parlay.Status.PENDING
        assert parlay.payout is None
        assert parlay.max_payout == PARLAY_MAX_PAYOUT
        assert parlay.id_hash  # inherited from BaseModel

    def test_parlay_str(self):
        parlay = ParlayFactory(combined_odds="8.50")
        assert parlay.id_hash in str(parlay)
        assert "8.50" in str(parlay)

    def test_constants(self):
        assert PARLAY_MIN_LEGS == 2
        assert PARLAY_MAX_LEGS == 10
        assert PARLAY_MAX_PAYOUT == Decimal("50000.00")

    def test_parlay_ordered_by_created_at_desc(self):
        user = UserBalanceFactory().user
        ParlayFactory(user=user)
        p2 = ParlayFactory(user=user)
        parlays = list(Parlay.objects.filter(user=user))
        assert parlays[0].pk == p2.pk  # newest first


class TestParlayLegModel:
    def test_leg_created_with_defaults(self):
        leg = ParlayLegFactory()
        assert leg.status == ParlayLeg.Status.PENDING
        assert leg.selection == BetSlip.Selection.HOME_WIN

    def test_unique_together_match_per_parlay(self):
        from django.db import IntegrityError

        parlay = ParlayFactory()
        match = MatchFactory()
        ParlayLegFactory(parlay=parlay, match=match, selection=BetSlip.Selection.HOME_WIN)

        with pytest.raises(IntegrityError):
            ParlayLegFactory(parlay=parlay, match=match, selection=BetSlip.Selection.DRAW)

    def test_different_parlays_can_have_same_match(self):
        match = MatchFactory()
        leg1 = ParlayLegFactory(match=match)
        leg2 = ParlayLegFactory(match=match)
        assert leg1.pk != leg2.pk

    def test_leg_str(self):
        leg = ParlayLegFactory(selection=BetSlip.Selection.HOME_WIN, odds_at_placement="2.50")
        assert "2.50" in str(leg)

    def test_legs_ordered_by_created_at(self):
        parlay = ParlayFactory()
        leg1 = ParlayLegFactory(parlay=parlay, match=MatchFactory())
        ParlayLegFactory(parlay=parlay, match=MatchFactory())
        legs = list(parlay.legs.all())
        assert legs[0].pk == leg1.pk  # oldest first
