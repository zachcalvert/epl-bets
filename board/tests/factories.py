import factory

from board.models import BoardPost, PostType
from users.tests.factories import UserFactory


class BoardPostFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = BoardPost

    author = factory.SubFactory(UserFactory)
    post_type = PostType.RESULTS_TABLE
    body = factory.Sequence(lambda n: f"Test board post {n}")
    parent = None
