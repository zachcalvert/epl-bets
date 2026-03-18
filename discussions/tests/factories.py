import factory

from discussions.models import Comment
from matches.tests.factories import MatchFactory
from users.tests.factories import UserFactory


class CommentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Comment

    match = factory.SubFactory(MatchFactory)
    user = factory.SubFactory(UserFactory)
    parent = None
    body = factory.Sequence(lambda n: f"Test comment {n}")
