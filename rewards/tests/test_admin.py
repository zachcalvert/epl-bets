from decimal import Decimal

import pytest
from django.urls import reverse

from betting.models import BetSlip, UserBalance
from betting.tests.factories import BetSlipFactory, UserBalanceFactory
from rewards.models import Reward, RewardDistribution
from rewards.tests.factories import RewardFactory
from users.models import User
from users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


class TestRewardAdmin:
    def test_distribute_to_all_users_action(self, admin_client):
        reward = RewardFactory(amount="50.00")
        users = UserFactory.create_batch(3)
        for user in users:
            UserBalance.objects.create(user=user, balance=Decimal("1000.00"))

        url = reverse("admin:rewards_reward_changelist")
        response = admin_client.post(
            url,
            {
                "action": "distribute_to_all_users",
                "_selected_action": [reward.pk],
            },
            follow=True,
        )

        assert response.status_code == 200
        # All active users get the reward (admin, factory users, etc.)
        active_count = User.objects.filter(is_active=True).count()
        assert RewardDistribution.objects.count() == active_count
        for user in users:
            assert UserBalance.objects.get(user=user).balance == Decimal("1050.00")

    def test_created_by_set_on_save(self, admin_client):
        add_url = reverse("admin:rewards_reward_add")
        response = admin_client.post(
            add_url,
            {
                "name": "Test Reward",
                "amount": "100.00",
                "description": "A test",
                "distributions-TOTAL_FORMS": "0",
                "distributions-INITIAL_FORMS": "0",
                "distributions-MIN_NUM_FORMS": "0",
                "distributions-MAX_NUM_FORMS": "1000",
            },
            follow=True,
        )

        assert response.status_code == 200
        reward = Reward.objects.get(name="Test Reward")
        assert reward.created_by is not None

    def test_create_reward_with_selected_users_creates_distributions(self, admin_client):
        users = UserFactory.create_batch(3)
        for user in users:
            UserBalance.objects.create(user=user, balance=Decimal("100.00"))

        add_url = reverse("admin:rewards_reward_add")
        response = admin_client.post(
            add_url,
            {
                "name": "Targeted Reward",
                "amount": "25.00",
                "description": "Only for selected users",
                "distribute_to": [u.pk for u in users[:2]],
                "distributions-TOTAL_FORMS": "0",
                "distributions-INITIAL_FORMS": "0",
                "distributions-MIN_NUM_FORMS": "0",
                "distributions-MAX_NUM_FORMS": "1000",
            },
            follow=True,
        )

        assert response.status_code == 200
        reward = Reward.objects.get(name="Targeted Reward")
        assert RewardDistribution.objects.filter(reward=reward).count() == 2
        assert UserBalance.objects.get(user=users[0]).balance == Decimal("125.00")
        assert UserBalance.objects.get(user=users[1]).balance == Decimal("125.00")
        # Third user was not selected – balance unchanged
        assert UserBalance.objects.get(user=users[2]).balance == Decimal("100.00")

    def test_create_reward_without_selected_users_creates_no_distributions(self, admin_client):
        add_url = reverse("admin:rewards_reward_add")
        response = admin_client.post(
            add_url,
            {
                "name": "No Distribution Reward",
                "amount": "10.00",
                "description": "No one selected",
                "distributions-TOTAL_FORMS": "0",
                "distributions-INITIAL_FORMS": "0",
                "distributions-MIN_NUM_FORMS": "0",
                "distributions-MAX_NUM_FORMS": "1000",
            },
            follow=True,
        )

        assert response.status_code == 200
        reward = Reward.objects.get(name="No Distribution Reward")
        assert RewardDistribution.objects.filter(reward=reward).count() == 0


class TestUserAdminGrantReward:
    def test_grant_latest_reward_action(self, admin_client):
        RewardFactory(amount="25.00")
        users = UserFactory.create_batch(2)
        for user in users:
            UserBalance.objects.create(user=user, balance=Decimal("500.00"))

        url = reverse("admin:users_user_changelist")
        response = admin_client.post(
            url,
            {
                "action": "grant_latest_reward",
                "_selected_action": [u.pk for u in users],
            },
            follow=True,
        )

        assert response.status_code == 200
        assert RewardDistribution.objects.count() == 2
        for user in users:
            assert UserBalance.objects.get(user=user).balance == Decimal("525.00")

    def test_grant_reward_warns_when_none_exist(self, admin_client):
        user = UserFactory()
        url = reverse("admin:users_user_changelist")
        response = admin_client.post(
            url,
            {
                "action": "grant_latest_reward",
                "_selected_action": [user.pk],
            },
            follow=True,
        )

        assert response.status_code == 200
        assert RewardDistribution.objects.count() == 0


class TestUserAdminSimulateBankruptcy:
    def test_simulate_bankruptcy_zeros_balance_and_settles_pending_bets(self, admin_client):
        user = UserFactory()
        UserBalanceFactory(user=user, balance="500.00")
        bet = BetSlipFactory(user=user, status=BetSlip.Status.PENDING)

        url = reverse("admin:users_user_changelist")
        response = admin_client.post(
            url,
            {
                "action": "simulate_bankruptcy",
                "_selected_action": [user.pk],
            },
            follow=True,
        )

        assert response.status_code == 200
        assert UserBalance.objects.get(user=user).balance == Decimal("0.00")
        bet.refresh_from_db()
        assert bet.status == BetSlip.Status.LOST
        assert bet.payout == 0

    def test_simulate_bankruptcy_handles_multiple_users(self, admin_client):
        users = UserFactory.create_batch(2)
        for user in users:
            UserBalanceFactory(user=user, balance="1000.00")

        url = reverse("admin:users_user_changelist")
        response = admin_client.post(
            url,
            {
                "action": "simulate_bankruptcy",
                "_selected_action": [u.pk for u in users],
            },
            follow=True,
        )

        assert response.status_code == 200
        for user in users:
            assert UserBalance.objects.get(user=user).balance == Decimal("0.00")
