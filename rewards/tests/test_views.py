import pytest
from django.urls import reverse

from rewards.tests.factories import RewardDistributionFactory
from users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


class TestDismissRewardView:
    def test_dismiss_marks_distribution_as_seen(self, client):
        user = UserFactory()
        client.force_login(user)
        dist = RewardDistributionFactory(user=user, seen=False)

        url = reverse("rewards:dismiss", args=[dist.pk])
        response = client.post(url)

        assert response.status_code == 200
        assert response.content == b""
        dist.refresh_from_db()
        assert dist.seen is True

    def test_dismiss_only_affects_own_distribution(self, client):
        user = UserFactory()
        other_user = UserFactory()
        client.force_login(user)
        dist = RewardDistributionFactory(user=other_user, seen=False)

        url = reverse("rewards:dismiss", args=[dist.pk])
        response = client.post(url)

        assert response.status_code == 200
        dist.refresh_from_db()
        assert dist.seen is False

    def test_dismiss_requires_login(self, client):
        dist = RewardDistributionFactory()

        url = reverse("rewards:dismiss", args=[dist.pk])
        response = client.post(url)

        assert response.status_code == 302

    def test_dismiss_already_seen_is_noop(self, client):
        user = UserFactory()
        client.force_login(user)
        dist = RewardDistributionFactory(user=user, seen=True)

        url = reverse("rewards:dismiss", args=[dist.pk])
        response = client.post(url)

        assert response.status_code == 200
        dist.refresh_from_db()
        assert dist.seen is True
