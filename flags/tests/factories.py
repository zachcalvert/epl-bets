import factory

from flags.models import FeatureFlag


class FeatureFlagFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = FeatureFlag

    name = factory.Sequence(lambda n: f"flag-{n}")
    description = factory.Sequence(lambda n: f"Description for flag {n}")
    is_enabled_for_all = False
