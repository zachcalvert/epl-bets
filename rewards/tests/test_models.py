from decimal import Decimal

import pytest

from betting.models import UserBalance
from rewards.tests.factories import RewardDistributionFactory, RewardFactory
from users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


class TestRewardModel:
    def test_str_includes_name_and_amount(self):
        reward = RewardFactory(name="Welcome Bonus", amount="100.00")
        assert str(reward) == "Welcome Bonus (100.00 credits)"

    def test_distribute_to_users_creates_distributions(self):
        reward = RewardFactory(amount="50.00")
        users = UserFactory.create_batch(3)
        for user in users:
            UserBalance.objects.create(user=user, balance=Decimal("1000.00"))

        distributions = reward.distribute_to_users(users)

        assert len(distributions) == 3
        assert reward.distributions.count() == 3

    def test_distribute_credits_user_balances(self):
        reward = RewardFactory(amount="75.00")
        user = UserFactory()
        UserBalance.objects.create(user=user, balance=Decimal("1000.00"))

        reward.distribute_to_users([user])

        user_balance = UserBalance.objects.get(user=user)
        assert user_balance.balance == Decimal("1075.00")

    def test_distribute_skips_duplicate_users(self):
        reward = RewardFactory(amount="50.00")
        user = UserFactory()
        UserBalance.objects.create(user=user, balance=Decimal("1000.00"))

        reward.distribute_to_users([user])
        distributions = reward.distribute_to_users([user])

        assert distributions == []
        assert reward.distributions.count() == 1
        assert UserBalance.objects.get(user=user).balance == Decimal("1050.00")

    def test_distribute_creates_balance_if_missing(self):
        reward = RewardFactory(amount="25.00")
        user = UserFactory()

        reward.distribute_to_users([user])

        balance = UserBalance.objects.get(user=user)
        assert balance.balance == Decimal("1025.00")


class TestRewardDistributionModel:
    def test_str_shows_reward_and_user(self):
        dist = RewardDistributionFactory()
        assert dist.reward.name in str(dist)
        assert str(dist.user) in str(dist)

    def test_seen_defaults_to_false(self):
        dist = RewardDistributionFactory()
        assert dist.seen is False
