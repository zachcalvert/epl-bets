import pytest
from django.urls import reverse

from betting.models import BetSlip
from betting.tests.factories import BetSlipFactory
from discussions.models import Comment
from discussions.tests.factories import CommentFactory
from matches.tests.factories import MatchFactory
from users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


# --- CommentListView ---


def test_comment_list_returns_200(client):
    match = MatchFactory()

    response = client.get(reverse("discussions:comment_list", args=[match.pk]))

    assert response.status_code == 200
    assert "Discussion" in response.content.decode()


def test_comment_list_shows_empty_state_when_no_comments(client):
    match = MatchFactory()

    response = client.get(reverse("discussions:comment_list", args=[match.pk]))

    assert response.status_code == 200
    assert "No comments yet" in response.content.decode()


def test_comment_list_shows_comments_for_match(client):
    match = MatchFactory()
    CommentFactory(match=match, body="Great match ahead")
    CommentFactory(body="Comment on different match")

    response = client.get(reverse("discussions:comment_list", args=[match.pk]))

    content = response.content.decode()
    assert "Great match ahead" in content
    assert "Comment on different match" not in content


def test_comment_list_shows_replies_nested_under_parent(client):
    match = MatchFactory()
    parent = CommentFactory(match=match, body="Top-level comment")
    CommentFactory(match=match, parent=parent, body="A reply to the parent")

    response = client.get(reverse("discussions:comment_list", args=[match.pk]))

    content = response.content.decode()
    assert "Top-level comment" in content
    assert "A reply to the parent" in content


def test_comment_list_shows_bet_position_badge(client):
    match = MatchFactory()
    user = UserFactory()
    BetSlipFactory(user=user, match=match, selection=BetSlip.Selection.HOME_WIN)
    CommentFactory(match=match, user=user, body="Backing the home team here")

    response = client.get(reverse("discussions:comment_list", args=[match.pk]))

    content = response.content.decode()
    assert "Backing the home team here" in content
    assert f"Backing {match.home_team.short_name}" in content


def test_comment_list_shows_draw_badge(client):
    match = MatchFactory()
    user = UserFactory()
    BetSlipFactory(user=user, match=match, selection=BetSlip.Selection.DRAW)
    CommentFactory(match=match, user=user, body="Draw is the play")

    response = client.get(reverse("discussions:comment_list", args=[match.pk]))

    assert "Backing Draw" in response.content.decode()


def test_comment_list_shows_away_badge(client):
    match = MatchFactory()
    user = UserFactory()
    BetSlipFactory(user=user, match=match, selection=BetSlip.Selection.AWAY_WIN)
    CommentFactory(match=match, user=user, body="Away win incoming")

    response = client.get(reverse("discussions:comment_list", args=[match.pk]))

    assert f"Backing {match.away_team.short_name}" in response.content.decode()


def test_comment_list_uses_most_recent_bet_for_badge(client):
    match = MatchFactory()
    user = UserFactory()
    BetSlipFactory(user=user, match=match, selection=BetSlip.Selection.HOME_WIN)
    BetSlipFactory(user=user, match=match, selection=BetSlip.Selection.AWAY_WIN)
    CommentFactory(match=match, user=user, body="Changed my mind")

    response = client.get(reverse("discussions:comment_list", args=[match.pk]))

    content = response.content.decode()
    assert f"Backing {match.away_team.short_name}" in content


def test_comment_list_shows_comment_count(client):
    match = MatchFactory()
    CommentFactory(match=match)
    CommentFactory(match=match)
    CommentFactory(match=match)

    response = client.get(reverse("discussions:comment_list", args=[match.pk]))

    assert "(3)" in response.content.decode()


def test_comment_list_does_not_count_replies_in_total(client):
    match = MatchFactory()
    parent = CommentFactory(match=match)
    CommentFactory(match=match, parent=parent)

    response = client.get(reverse("discussions:comment_list", args=[match.pk]))

    assert "(1)" in response.content.decode()


def test_comment_list_paginates_at_20(client):
    match = MatchFactory()
    user = UserFactory()
    for i in range(25):
        CommentFactory(match=match, user=user, body=f"Comment {i}")

    response = client.get(reverse("discussions:comment_list", args=[match.pk]))

    content = response.content.decode()
    assert "Comment 24" in content  # newest first
    assert "Comment 4" not in content  # 21st newest not on first page
    assert "Load more comments" in content


def test_comment_list_offset_returns_next_page(client):
    match = MatchFactory()
    user = UserFactory()
    for i in range(25):
        CommentFactory(match=match, user=user, body=f"Comment {i}")

    response = client.get(
        reverse("discussions:comment_list", args=[match.pk]),
        data={"offset": "20"},
    )

    content = response.content.decode()
    assert "Comment 4" in content  # oldest remaining after first 20
    assert "Comment 0" in content
    assert "Load more" not in content


def test_comment_list_shows_login_cta_for_anonymous(client):
    match = MatchFactory()

    response = client.get(reverse("discussions:comment_list", args=[match.pk]))

    assert "Log in to join the discussion" in response.content.decode()


def test_comment_list_shows_form_for_authenticated_user(client):
    match = MatchFactory()
    user = UserFactory()
    client.force_login(user)

    response = client.get(reverse("discussions:comment_list", args=[match.pk]))

    content = response.content.decode()
    assert "Log in to join the discussion" not in content
    assert "Join the discussion..." in content


def test_comment_list_hides_deleted_comments_without_replies(client):
    match = MatchFactory()
    CommentFactory(match=match, body="Visible comment")
    CommentFactory(match=match, body="Deleted comment", is_deleted=True)

    response = client.get(reverse("discussions:comment_list", args=[match.pk]))

    content = response.content.decode()
    assert "Visible comment" in content
    # Deleted top-level comments with no replies are hidden entirely by _visible_top_level_qs
    assert "Deleted comment" not in content


# --- CreateCommentView ---


def test_create_comment_redirects_anonymous_to_login(client):
    match = MatchFactory()

    response = client.post(
        reverse("discussions:create_comment", args=[match.pk]),
        data={"body": "Hello"},
    )

    assert response.status_code == 302
    assert reverse("website:login") in response.url


def test_create_comment_creates_top_level_comment(client):
    match = MatchFactory()
    user = UserFactory()
    client.force_login(user)

    response = client.post(
        reverse("discussions:create_comment", args=[match.pk]),
        data={"body": "My prediction for this match"},
    )

    assert response.status_code == 200
    comment = Comment.objects.get()
    assert comment.match == match
    assert comment.user == user
    assert comment.body == "My prediction for this match"
    assert comment.parent is None


def test_create_comment_returns_comment_html(client):
    match = MatchFactory()
    user = UserFactory(display_name="TestUser")
    client.force_login(user)

    response = client.post(
        reverse("discussions:create_comment", args=[match.pk]),
        data={"body": "Nice odds on this one"},
    )

    content = response.content.decode()
    assert "Nice odds on this one" in content
    assert "TestUser" in content


def test_create_comment_includes_oob_count_update(client):
    match = MatchFactory()
    user = UserFactory()
    client.force_login(user)

    client.post(
        reverse("discussions:create_comment", args=[match.pk]),
        data={"body": "First comment"},
    )
    response = client.post(
        reverse("discussions:create_comment", args=[match.pk]),
        data={"body": "Second comment"},
    )

    content = response.content.decode()
    assert 'id="comment-count"' in content
    assert 'hx-swap-oob="true"' in content
    assert "(2)" in content


def test_create_comment_shows_bet_badge(client):
    match = MatchFactory()
    user = UserFactory()
    BetSlipFactory(user=user, match=match, selection=BetSlip.Selection.DRAW)
    client.force_login(user)

    response = client.post(
        reverse("discussions:create_comment", args=[match.pk]),
        data={"body": "Drawing vibes"},
    )

    assert "Backing Draw" in response.content.decode()


def test_create_comment_rejects_empty_body(client):
    match = MatchFactory()
    user = UserFactory()
    client.force_login(user)

    response = client.post(
        reverse("discussions:create_comment", args=[match.pk]),
        data={"body": ""},
    )

    assert response.status_code == 422
    assert Comment.objects.count() == 0


def test_create_comment_rejects_body_over_1000_chars(client):
    match = MatchFactory()
    user = UserFactory()
    client.force_login(user)

    response = client.post(
        reverse("discussions:create_comment", args=[match.pk]),
        data={"body": "x" * 1001},
    )

    assert response.status_code == 422
    assert Comment.objects.count() == 0


# --- CreateReplyView ---


def test_create_reply_redirects_anonymous_to_login(client):
    match = MatchFactory()
    comment = CommentFactory(match=match)

    response = client.post(
        reverse("discussions:create_reply", args=[match.pk, comment.pk]),
        data={"body": "Nice one"},
    )

    assert response.status_code == 302
    assert reverse("website:login") in response.url


def test_create_reply_creates_reply_to_comment(client):
    match = MatchFactory()
    parent = CommentFactory(match=match, body="Top level")
    user = UserFactory()
    client.force_login(user)

    response = client.post(
        reverse("discussions:create_reply", args=[match.pk, parent.pk]),
        data={"body": "I agree with you"},
    )

    assert response.status_code == 200
    reply = Comment.objects.filter(parent=parent).get()
    assert reply.body == "I agree with you"
    assert reply.user == user
    assert reply.match == match


def test_create_reply_returns_reply_html(client):
    match = MatchFactory()
    parent = CommentFactory(match=match)
    user = UserFactory(display_name="Replier")
    client.force_login(user)

    response = client.post(
        reverse("discussions:create_reply", args=[match.pk, parent.pk]),
        data={"body": "My reply here"},
    )

    content = response.content.decode()
    assert "My reply here" in content
    assert "Replier" in content


def test_create_reply_rejects_reply_to_reply(client):
    match = MatchFactory()
    parent = CommentFactory(match=match)
    reply = CommentFactory(match=match, parent=parent)
    user = UserFactory()
    client.force_login(user)

    response = client.post(
        reverse("discussions:create_reply", args=[match.pk, reply.pk]),
        data={"body": "Nested too deep"},
    )

    assert response.status_code == 400
    assert Comment.objects.filter(parent=reply).count() == 0


def test_create_reply_rejects_empty_body(client):
    match = MatchFactory()
    parent = CommentFactory(match=match)
    user = UserFactory()
    client.force_login(user)

    response = client.post(
        reverse("discussions:create_reply", args=[match.pk, parent.pk]),
        data={"body": ""},
    )

    assert response.status_code == 422
    assert Comment.objects.filter(parent=parent).count() == 0


def test_create_reply_shows_bet_badge(client):
    match = MatchFactory()
    parent = CommentFactory(match=match)
    user = UserFactory()
    BetSlipFactory(user=user, match=match, selection=BetSlip.Selection.HOME_WIN)
    client.force_login(user)

    response = client.post(
        reverse("discussions:create_reply", args=[match.pk, parent.pk]),
        data={"body": "Home win for sure"},
    )

    assert f"Backing {match.home_team.short_name}" in response.content.decode()


# --- DeleteCommentView ---


def test_delete_comment_redirects_anonymous_to_login(client):
    match = MatchFactory()
    comment = CommentFactory(match=match)

    response = client.post(
        reverse("discussions:delete_comment", args=[match.pk, comment.pk]),
    )

    assert response.status_code == 302
    assert reverse("website:login") in response.url


def test_delete_comment_soft_deletes_own_comment(client):
    match = MatchFactory()
    user = UserFactory()
    comment = CommentFactory(match=match, user=user, body="My comment")
    client.force_login(user)

    response = client.post(
        reverse("discussions:delete_comment", args=[match.pk, comment.pk]),
    )

    assert response.status_code == 200
    comment.refresh_from_db()
    assert comment.is_deleted is True


def test_delete_comment_returns_empty_when_no_replies(client):
    match = MatchFactory()
    user = UserFactory()
    comment = CommentFactory(match=match, user=user)
    client.force_login(user)

    response = client.post(
        reverse("discussions:delete_comment", args=[match.pk, comment.pk]),
    )

    content = response.content.decode()
    # Should return OOB count update but no comment HTML
    assert 'id="comment-count"' in content
    assert "[Comment deleted]" not in content


def test_delete_comment_preserves_placeholder_when_has_replies(client):
    match = MatchFactory()
    user = UserFactory()
    comment = CommentFactory(match=match, user=user)
    CommentFactory(match=match, parent=comment, body="A reply that should stay")
    client.force_login(user)

    response = client.post(
        reverse("discussions:delete_comment", args=[match.pk, comment.pk]),
    )

    content = response.content.decode()
    assert "[Comment deleted]" in content
    assert "A reply that should stay" in content


def test_delete_comment_forbidden_for_other_user(client):
    match = MatchFactory()
    author = UserFactory()
    other_user = UserFactory()
    comment = CommentFactory(match=match, user=author)
    client.force_login(other_user)

    response = client.post(
        reverse("discussions:delete_comment", args=[match.pk, comment.pk]),
    )

    assert response.status_code == 403
    comment.refresh_from_db()
    assert comment.is_deleted is False


def test_delete_comment_updates_count_oob(client):
    match = MatchFactory()
    user = UserFactory()
    CommentFactory(match=match, user=user, body="Will keep")
    to_delete = CommentFactory(match=match, user=user, body="Will delete")
    client.force_login(user)

    response = client.post(
        reverse("discussions:delete_comment", args=[match.pk, to_delete.pk]),
    )

    content = response.content.decode()
    assert 'hx-swap-oob="true"' in content
    # Count should reflect only visible (non-deleted) top-level comments
    assert "(1)" in content


def test_delete_reply_does_not_update_count(client):
    match = MatchFactory()
    user = UserFactory()
    parent = CommentFactory(match=match)
    reply = CommentFactory(match=match, user=user, parent=parent, body="My reply")
    client.force_login(user)

    response = client.post(
        reverse("discussions:delete_comment", args=[match.pk, reply.pk]),
    )

    assert response.status_code == 200
    reply.refresh_from_db()
    assert reply.is_deleted is True
    # No OOB count update for replies
    assert "comment-count" not in response.content.decode()
