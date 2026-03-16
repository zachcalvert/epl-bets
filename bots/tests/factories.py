import factory

from betting.tests.factories import UserBalanceFactory
from users.tests.factories import UserFactory


class BotUserFactory(UserFactory):
    """A User with is_bot=True and no usable password."""

    email = factory.Sequence(lambda n: f"bot{n}@bots.eplbets.local")
    display_name = factory.Sequence(lambda n: f"Bot {n}")
    is_bot = True

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        user = super()._create(model_class, *args, **kwargs)
        user.set_unusable_password()
        user.save(update_fields=["password"])
        return user


class BotUserWithBalanceFactory(BotUserFactory):
    balance = factory.RelatedFactory(UserBalanceFactory, factory_related_name="user")
