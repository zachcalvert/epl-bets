from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command

from betting.models import BetSlip, Parlay, UserStats
from betting.tests.factories import BetSlipFactory, ParlayFactory
from users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def test_backfill_creates_stats_from_settled_bets():
    user = UserFactory()
    BetSlipFactory(user=user, status=BetSlip.Status.WON, stake="10.00", payout="21.00")
    BetSlipFactory(user=user, status=BetSlip.Status.LOST, stake="15.00", payout="0")
    BetSlipFactory(user=user, status=BetSlip.Status.PENDING, stake="5.00")  # ignored

    out = StringIO()
    call_command("backfill_stats", stdout=out)

    stats = UserStats.objects.get(user=user)
    assert stats.total_bets == 2
    assert stats.total_wins == 1
    assert stats.total_losses == 1
    assert stats.total_staked == Decimal("25.00")
    assert stats.total_payout == Decimal("21.00")
    assert stats.net_profit == Decimal("-4.00")
    assert "1 created" in out.getvalue()


def test_backfill_includes_parlay_totals():
    user = UserFactory()
    ParlayFactory(user=user, status=Parlay.Status.WON, stake="20.00", payout="100.00")
    ParlayFactory(user=user, status=Parlay.Status.LOST, stake="10.00", payout="0")

    call_command("backfill_stats", stdout=StringIO())

    stats = UserStats.objects.get(user=user)
    assert stats.total_bets == 2
    assert stats.total_wins == 1
    assert stats.total_losses == 1
    assert stats.total_staked == Decimal("30.00")
    assert stats.total_payout == Decimal("100.00")
    assert stats.net_profit == Decimal("70.00")


def test_backfill_updates_existing_stats():
    user = UserFactory()
    UserStats.objects.create(user=user, total_bets=99)  # stale data
    BetSlipFactory(user=user, status=BetSlip.Status.WON, stake="10.00", payout="20.00")

    out = StringIO()
    call_command("backfill_stats", stdout=out)

    stats = UserStats.objects.get(user=user)
    assert stats.total_bets == 1  # recalculated, not 99
    assert "1 updated" in out.getvalue()


def test_backfill_skips_users_with_no_bets():
    UserFactory()  # no bets at all

    call_command("backfill_stats", stdout=StringIO())

    assert UserStats.objects.count() == 0


def test_backfill_computes_streaks():
    user = UserFactory()
    BetSlipFactory(user=user, status=BetSlip.Status.WON, stake="10.00", payout="20.00")
    BetSlipFactory(user=user, status=BetSlip.Status.WON, stake="10.00", payout="20.00")
    BetSlipFactory(user=user, status=BetSlip.Status.LOST, stake="10.00", payout="0")

    call_command("backfill_stats", stdout=StringIO())

    stats = UserStats.objects.get(user=user)
    assert stats.best_streak == 2
    assert stats.current_streak == -1
