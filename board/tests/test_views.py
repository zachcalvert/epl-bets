import pytest
from django.urls import reverse

from board.models import BoardPost, PostType
from board.tests.factories import BoardPostFactory
from users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


# --- BoardView ---


def test_board_page_returns_200(client):
    response = client.get(reverse("board:board"))

    assert response.status_code == 200
    assert "Message Board" in response.content.decode()


# --- PostListView ---


def test_post_list_returns_200(client):
    response = client.get(reverse("board:post_list"))

    assert response.status_code == 200


def test_post_list_shows_empty_state_when_no_posts(client):
    response = client.get(reverse("board:post_list"))

    assert "No posts yet" in response.content.decode()


def test_post_list_shows_posts(client):
    BoardPostFactory(body="Arsenal are winning the league")

    response = client.get(reverse("board:post_list"))

    assert "Arsenal are winning the league" in response.content.decode()


def test_post_list_filters_by_type(client):
    BoardPostFactory(body="Table talk", post_type=PostType.RESULTS_TABLE)
    BoardPostFactory(body="Bold prediction", post_type=PostType.PREDICTION)

    response = client.get(reverse("board:post_list"), data={"type": "prediction"})

    content = response.content.decode()
    assert "Bold prediction" in content
    assert "Table talk" not in content


def test_post_list_shows_replies_nested_under_parent(client):
    parent = BoardPostFactory(body="Top-level post")
    BoardPostFactory(body="A reply to the post", parent=parent)

    response = client.get(reverse("board:post_list"))

    content = response.content.decode()
    assert "Top-level post" in content
    assert "A reply to the post" in content


def test_post_list_includes_oob_post_count_on_initial_load(client):
    BoardPostFactory()
    BoardPostFactory()

    response = client.get(reverse("board:post_list"))

    content = response.content.decode()
    assert 'id="post-count"' in content
    assert 'hx-swap-oob="true"' in content
    assert "(2)" in content


def test_post_list_does_not_include_oob_count_on_pagination(client):
    user = UserFactory()
    for i in range(25):
        BoardPostFactory(author=user, body=f"Post {i}")

    response = client.get(reverse("board:post_list"), data={"offset": "20"})

    content = response.content.decode()
    assert "post-count" not in content


def test_post_list_paginates_at_20(client):
    user = UserFactory()
    for i in range(25):
        BoardPostFactory(author=user, body=f"Post {i:02d}")

    response = client.get(reverse("board:post_list"))

    content = response.content.decode()
    assert "Load more posts" in content


def test_post_list_hides_hidden_posts_for_regular_users(client):
    BoardPostFactory(body="Visible post")
    BoardPostFactory(body="Hidden post", is_hidden=True)

    response = client.get(reverse("board:post_list"))

    content = response.content.decode()
    assert "Visible post" in content
    assert "Hidden post" not in content


def test_post_list_shows_hidden_posts_for_superuser(client):
    superuser = UserFactory(is_superuser=True)
    client.force_login(superuser)
    BoardPostFactory(body="Visible post")
    BoardPostFactory(body="Hidden post", is_hidden=True)

    response = client.get(reverse("board:post_list"))

    content = response.content.decode()
    assert "Visible post" in content
    assert "Hidden" in content


def test_post_list_does_not_count_replies_in_total(client):
    parent = BoardPostFactory()
    BoardPostFactory(parent=parent)

    response = client.get(reverse("board:post_list"))

    assert "(1)" in response.content.decode()


# --- CreatePostView ---


def test_create_post_redirects_anonymous_to_login(client):
    response = client.post(
        reverse("board:create_post"),
        data={"body": "Hello", "post_type": PostType.META},
    )

    assert response.status_code == 302
    assert reverse("website:login") in response.url


def test_create_post_creates_board_post(client):
    user = UserFactory()
    client.force_login(user)

    response = client.post(
        reverse("board:create_post"),
        data={"body": "My hot take", "post_type": PostType.PREDICTION},
    )

    assert response.status_code == 200
    post = BoardPost.objects.get()
    assert post.author == user
    assert post.body == "My hot take"
    assert post.post_type == PostType.PREDICTION
    assert post.parent is None


def test_create_post_returns_post_html(client):
    user = UserFactory(display_name="Pundit")
    client.force_login(user)

    response = client.post(
        reverse("board:create_post"),
        data={"body": "Title race is over", "post_type": PostType.RESULTS_TABLE},
    )

    content = response.content.decode()
    assert "Title race is over" in content
    assert "Pundit" in content


def test_create_post_includes_oob_count_update(client):
    user = UserFactory()
    client.force_login(user)

    client.post(
        reverse("board:create_post"),
        data={"body": "First", "post_type": PostType.META},
    )
    response = client.post(
        reverse("board:create_post"),
        data={"body": "Second", "post_type": PostType.META},
    )

    content = response.content.decode()
    assert 'id="post-count"' in content
    assert 'hx-swap-oob="true"' in content
    assert "(2)" in content


def test_create_post_rejects_empty_body(client):
    user = UserFactory()
    client.force_login(user)

    response = client.post(
        reverse("board:create_post"),
        data={"body": "", "post_type": PostType.META},
    )

    assert response.status_code == 422
    assert BoardPost.objects.count() == 0


def test_create_post_rejects_body_over_2000_chars(client):
    user = UserFactory()
    client.force_login(user)

    response = client.post(
        reverse("board:create_post"),
        data={"body": "x" * 2001, "post_type": PostType.META},
    )

    assert response.status_code == 422
    assert BoardPost.objects.count() == 0


# --- CreateReplyView ---


def test_create_reply_redirects_anonymous_to_login(client):
    post = BoardPostFactory()

    response = client.post(
        reverse("board:create_reply", args=[post.id_hash]),
        data={"body": "Nice one"},
    )

    assert response.status_code == 302
    assert reverse("website:login") in response.url


def test_create_reply_creates_reply(client):
    parent = BoardPostFactory(body="Top level")
    user = UserFactory()
    client.force_login(user)

    response = client.post(
        reverse("board:create_reply", args=[parent.id_hash]),
        data={"body": "I agree"},
    )

    assert response.status_code == 200
    reply = BoardPost.objects.filter(parent=parent).get()
    assert reply.body == "I agree"
    assert reply.author == user


def test_create_reply_returns_reply_html(client):
    parent = BoardPostFactory()
    user = UserFactory(display_name="Replier")
    client.force_login(user)

    response = client.post(
        reverse("board:create_reply", args=[parent.id_hash]),
        data={"body": "My reply here"},
    )

    content = response.content.decode()
    assert "My reply here" in content
    assert "Replier" in content


def test_create_reply_rejects_reply_to_reply(client):
    parent = BoardPostFactory()
    reply = BoardPostFactory(parent=parent)
    user = UserFactory()
    client.force_login(user)

    response = client.post(
        reverse("board:create_reply", args=[reply.id_hash]),
        data={"body": "Nested too deep"},
    )

    assert response.status_code == 400
    assert BoardPost.objects.filter(parent=reply).count() == 0


def test_create_reply_rejects_reply_to_hidden_post(client):
    parent = BoardPostFactory(is_hidden=True)
    user = UserFactory()
    client.force_login(user)

    response = client.post(
        reverse("board:create_reply", args=[parent.id_hash]),
        data={"body": "Replying to hidden"},
    )

    assert response.status_code == 400
    assert BoardPost.objects.filter(parent=parent).count() == 0


def test_create_reply_rejects_empty_body(client):
    parent = BoardPostFactory()
    user = UserFactory()
    client.force_login(user)

    response = client.post(
        reverse("board:create_reply", args=[parent.id_hash]),
        data={"body": ""},
    )

    assert response.status_code == 422
    assert BoardPost.objects.filter(parent=parent).count() == 0


def test_create_reply_rejects_body_over_2000_chars(client):
    parent = BoardPostFactory()
    user = UserFactory()
    client.force_login(user)

    response = client.post(
        reverse("board:create_reply", args=[parent.id_hash]),
        data={"body": "x" * 2001},
    )

    assert response.status_code == 422
    assert BoardPost.objects.filter(parent=parent).count() == 0


# --- HidePostView ---


def test_hide_post_redirects_anonymous_to_login(client):
    post = BoardPostFactory()

    response = client.post(reverse("board:hide_post", args=[post.id_hash]))

    assert response.status_code == 302
    assert reverse("website:login") in response.url


def test_hide_post_forbidden_for_non_superuser(client):
    post = BoardPostFactory()
    user = UserFactory()
    client.force_login(user)

    response = client.post(reverse("board:hide_post", args=[post.id_hash]))

    assert response.status_code == 403
    post.refresh_from_db()
    assert post.is_hidden is False


def test_hide_post_toggles_hidden_on(client):
    post = BoardPostFactory()
    superuser = UserFactory(is_superuser=True)
    client.force_login(superuser)

    response = client.post(reverse("board:hide_post", args=[post.id_hash]))

    assert response.status_code == 200
    post.refresh_from_db()
    assert post.is_hidden is True
    assert "Hidden" in response.content.decode()


def test_hide_post_toggles_hidden_off(client):
    post = BoardPostFactory(is_hidden=True)
    superuser = UserFactory(is_superuser=True)
    client.force_login(superuser)

    response = client.post(reverse("board:hide_post", args=[post.id_hash]))

    assert response.status_code == 200
    post.refresh_from_db()
    assert post.is_hidden is False


def test_hide_post_returns_restore_button_when_hiding(client):
    post = BoardPostFactory()
    superuser = UserFactory(is_superuser=True)
    client.force_login(superuser)

    response = client.post(reverse("board:hide_post", args=[post.id_hash]))

    assert "Restore" in response.content.decode()
