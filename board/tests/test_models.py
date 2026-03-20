import pytest

from board.models import BoardPost, PostType
from board.tests.factories import BoardPostFactory
from users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def test_board_post_str():
    user = UserFactory(email="pundit@example.com")
    post = BoardPostFactory(author=user, post_type=PostType.PREDICTION)

    result = str(post)

    assert "pundit@example.com" in result
    assert "Prediction" in result
    assert post.id_hash in result


def test_board_post_default_ordering_is_newest_first():
    user = UserFactory()
    first = BoardPostFactory(author=user, body="First")
    second = BoardPostFactory(author=user, body="Second")

    posts = list(BoardPost.objects.all())

    assert posts[0] == second
    assert posts[1] == first


def test_board_post_has_id_hash():
    post = BoardPostFactory()

    assert post.id_hash
    assert len(post.id_hash) == 8


def test_board_post_timestamps():
    post = BoardPostFactory()

    assert post.created_at is not None
    assert post.updated_at is not None


def test_reply_relationship():
    parent = BoardPostFactory()
    reply = BoardPostFactory(parent=parent)

    assert reply.parent == parent
    assert reply in parent.replies.all()


def test_cascade_delete_removes_replies():
    parent = BoardPostFactory()
    BoardPostFactory(parent=parent)
    BoardPostFactory(parent=parent)

    parent.delete()

    assert BoardPost.objects.count() == 0


def test_cascade_delete_on_author():
    user = UserFactory()
    BoardPostFactory(author=user)
    BoardPostFactory(author=user)

    user.delete()

    assert BoardPost.objects.count() == 0


def test_post_type_choices():
    assert PostType.RESULTS_TABLE == "results_table"
    assert PostType.PREDICTION == "prediction"
    assert PostType.META == "meta"


def test_is_hidden_defaults_to_false():
    post = BoardPostFactory()

    assert post.is_hidden is False


def test_parent_null_for_top_level_post():
    post = BoardPostFactory()

    assert post.parent is None


def test_related_name_board_posts():
    user = UserFactory()
    BoardPostFactory(author=user)
    BoardPostFactory(author=user)

    assert user.board_posts.count() == 2
