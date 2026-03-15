import pytest
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory

from rewards.context_processors import unseen_rewards
from rewards.tests.factories import RewardDistributionFactory
from users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


class TestUnseenRewardsContextProcessor:
    def setup_method(self):
        self.factory = RequestFactory()

    def _make_request(self, user=None):
        request = self.factory.get("/")
        if user:
            request.user = user
        else:
            request.user = AnonymousUser()
        return request

    def test_returns_empty_for_anonymous_user(self):
        request = self._make_request()
        context = unseen_rewards(request)
        assert context["unseen_rewards"] == []

    def test_returns_unseen_distributions(self):
        user = UserFactory()
        d1 = RewardDistributionFactory(user=user, seen=False)
        d2 = RewardDistributionFactory(user=user, seen=False)
        RewardDistributionFactory(user=user, seen=True)

        request = self._make_request(user)
        context = unseen_rewards(request)

        assert len(context["unseen_rewards"]) == 2
        ids = {d.pk for d in context["unseen_rewards"]}
        assert d1.pk in ids
        assert d2.pk in ids

    def test_excludes_other_users_distributions(self):
        user = UserFactory()
        other = UserFactory()
        RewardDistributionFactory(user=other, seen=False)

        request = self._make_request(user)
        context = unseen_rewards(request)

        assert context["unseen_rewards"] == []

    def test_limits_to_five(self):
        user = UserFactory()
        for _ in range(7):
            RewardDistributionFactory(user=user, seen=False)

        request = self._make_request(user)
        context = unseen_rewards(request)

        assert len(context["unseen_rewards"]) == 5
