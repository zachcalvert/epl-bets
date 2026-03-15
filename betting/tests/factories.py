import factory
from django.utils import timezone

from betting.models import (
    Badge,
    BetSlip,
    Odds,
    Parlay,
    ParlayLeg,
    UserBadge,
    UserBalance,
    UserStats,
)
from matches.tests.factories import MatchFactory
from users.tests.factories import UserFactory


class OddsFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Odds

    match = factory.SubFactory(MatchFactory)
    bookmaker = factory.Sequence(lambda n: f"Bookmaker {n}")
    home_win = "2.10"
    draw = "3.30"
    away_win = "3.90"
    fetched_at = factory.LazyFunction(timezone.now)


class BetSlipFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = BetSlip

    user = factory.SubFactory(UserFactory)
    match = factory.SubFactory(MatchFactory)
    selection = BetSlip.Selection.HOME_WIN
    odds_at_placement = "2.10"
    stake = "10.00"
    status = BetSlip.Status.PENDING
    payout = None


class UserBalanceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = UserBalance

    user = factory.SubFactory(UserFactory)
    balance = "1000.00"


class ParlayFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Parlay

    user = factory.SubFactory(UserFactory)
    stake = "10.00"
    combined_odds = "6.00"
    status = Parlay.Status.PENDING
    payout = None


class ParlayLegFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ParlayLeg

    parlay = factory.SubFactory(ParlayFactory)
    match = factory.SubFactory(MatchFactory)
    selection = BetSlip.Selection.HOME_WIN
    odds_at_placement = "2.00"
    status = ParlayLeg.Status.PENDING


class UserStatsFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = UserStats

    user = factory.SubFactory(UserFactory)
    total_bets = 0
    total_wins = 0
    total_losses = 0
    total_staked = "0.00"
    total_payout = "0.00"
    net_profit = "0.00"
    current_streak = 0
    best_streak = 0


class BadgeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Badge

    slug = factory.Sequence(lambda n: f"badge_{n}")
    name = factory.Sequence(lambda n: f"Badge {n}")
    description = "Test badge"
    icon = "🏅"
    rarity = Badge.Rarity.COMMON


class UserBadgeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = UserBadge

    user = factory.SubFactory(UserFactory)
    badge = factory.SubFactory(BadgeFactory)
