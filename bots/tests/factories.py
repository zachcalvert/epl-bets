import factory

from betting.tests.factories import UserBalanceFactory
from bots.models import BotProfile
from users.tests.factories import UserFactory


class BotProfileFactory(factory.django.DjangoModelFactory):
    """Creates a BotProfile linked to a bot user."""

    class Meta:
        model = BotProfile
        exclude = ["_skip"]

    _skip = False

    user = factory.SubFactory("bots.tests.factories.BotUserFactory", bot_profile=None)
    strategy_type = BotProfile.StrategyType.FRONTRUNNER
    persona_prompt = "You are a test bot. Stay in character."
    avatar_icon = "robot"
    avatar_bg = "#374151"
    is_active = True


class BotUserFactory(UserFactory):
    """A User with is_bot=True, no usable password, and a BotProfile.

    Pass bot_profile=None to skip BotProfile creation.
    Use bot_profile__strategy_type=... to customize the profile.
    """

    class Meta:
        model = UserFactory._meta.model
        skip_postgeneration_save = True

    email = factory.Sequence(lambda n: f"bot{n}@bots.eplbets.local")
    display_name = factory.Sequence(lambda n: f"Bot {n}")
    is_bot = True

    bot_profile = factory.RelatedFactory(
        BotProfileFactory,
        factory_related_name="user",
    )

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        user = super()._create(model_class, *args, **kwargs)
        user.set_unusable_password()
        user.save(update_fields=["password"])
        return user


class BotUserWithBalanceFactory(BotUserFactory):
    balance = factory.RelatedFactory(UserBalanceFactory, factory_related_name="user")
