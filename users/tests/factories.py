import factory

from betting.models import UserBalance
from users.models import User


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    password = "password123"

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        password = kwargs.pop("password", "password123")
        manager = cls._get_manager(model_class)
        return manager.create_user(*args, password=password, **kwargs)


class UserBalanceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = UserBalance

    user = factory.SubFactory(UserFactory)
