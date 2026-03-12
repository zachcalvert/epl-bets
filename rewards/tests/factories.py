import factory

from rewards.models import Reward, RewardDistribution
from users.tests.factories import UserFactory


class RewardFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Reward

    name = factory.Sequence(lambda n: f"Reward {n}")
    amount = "50.00"
    description = "Test reward"
    created_by = factory.SubFactory(UserFactory)


class RewardDistributionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = RewardDistribution

    reward = factory.SubFactory(RewardFactory)
    user = factory.SubFactory(UserFactory)
