from decimal import Decimal

import pytest
from django.urls import reverse

from betting.models import UserBalance
from rewards.models import Reward, RewardDistribution
from rewards.tests.factories import RewardFactory
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
        from users.models import User

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


class TestUserAdminGrantReward:
    def test_grant_latest_reward_action(self, admin_client):
        reward = RewardFactory(amount="25.00")
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
