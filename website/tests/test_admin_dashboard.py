from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from activity.models import ActivityEvent
from betting.tests.factories import BetSlipFactory, ParlayFactory
from board.tests.factories import BoardPostFactory
from discussions.tests.factories import CommentFactory
from users.tests.factories import UserFactory


@pytest.fixture
def superuser(db):
    return UserFactory(is_superuser=True, is_staff=True)


@pytest.fixture
def regular_user(db):
    return UserFactory()


# ---------------------------------------------------------------------------
# Access control
# ---------------------------------------------------------------------------

DASHBOARD_URLS = [
    "website:admin_dashboard",
    "website:admin_dashboard_bets",
    "website:admin_dashboard_comments",
    "website:admin_dashboard_tasks",
    "website:admin_dashboard_users",
    "website:admin_dashboard_activity_queue",
]


@pytest.mark.django_db
@pytest.mark.parametrize("url_name", DASHBOARD_URLS)
def test_anonymous_redirected_to_login(client, url_name):
    response = client.get(reverse(url_name))
    assert response.status_code == 302
    assert "/login/" in response.url


@pytest.mark.django_db
@pytest.mark.parametrize("url_name", DASHBOARD_URLS)
def test_regular_user_gets_403(client, regular_user, url_name):
    client.force_login(regular_user)
    response = client.get(reverse(url_name))
    assert response.status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize("url_name", DASHBOARD_URLS)
def test_superuser_gets_200(client, superuser, url_name):
    client.force_login(superuser)
    response = client.get(reverse(url_name))
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Stats panel
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_dashboard_stats_context(client, superuser):
    # Create some data
    UserFactory(is_bot=True)
    UserFactory()  # regular user
    BetSlipFactory(stake="25.00")
    BetSlipFactory(stake="50.00")
    ParlayFactory()
    CommentFactory()
    CommentFactory(is_deleted=True)
    BoardPostFactory()

    client.force_login(superuser)
    response = client.get(reverse("website:admin_dashboard"))

    assert response.context["active_bets"] == 2
    assert response.context["active_parlays"] == 1
    assert response.context["total_comments"] == 1  # 1 not deleted
    assert response.context["total_bets_all_time"] == 3  # 2 bets + 1 parlay


@pytest.mark.django_db
def test_dashboard_empty_stats(client, superuser):
    client.force_login(superuser)
    response = client.get(reverse("website:admin_dashboard"))

    assert response.context["total_users"] == 1  # just the superuser
    assert response.context["active_bets"] == 0
    assert response.context["total_in_play"] == 0
    assert response.context["total_bets_all_time"] == 0


# ---------------------------------------------------------------------------
# Bets panel
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_bets_panel_returns_recent(client, superuser):
    now = timezone.now()
    old_bet = BetSlipFactory(stake="10.00")
    old_bet.created_at = now - timedelta(hours=2)
    old_bet.save(update_fields=["created_at"])

    new_parlay = ParlayFactory()
    new_parlay.created_at = now - timedelta(minutes=5)
    new_parlay.save(update_fields=["created_at"])

    client.force_login(superuser)
    response = client.get(reverse("website:admin_dashboard_bets"))

    assert response.status_code == 200
    content = response.content.decode()
    assert "Bet" in content or "Parlay" in content


@pytest.mark.django_db
def test_bets_panel_pagination(client, superuser):
    for _ in range(25):
        BetSlipFactory()

    client.force_login(superuser)

    # First page should have "View all"
    response = client.get(reverse("website:admin_dashboard_bets"))
    content = response.content.decode()
    assert "View all" in content

    # Offset page
    response = client.get(reverse("website:admin_dashboard_bets") + "?offset=20")
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Comments panel
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_comments_panel_merges_sources(client, superuser):
    now = timezone.now()
    comment = CommentFactory(body="match comment here")
    comment.created_at = now - timedelta(minutes=10)
    comment.save(update_fields=["created_at"])

    post = BoardPostFactory(body="board post here")
    post.created_at = now - timedelta(minutes=5)
    post.save(update_fields=["created_at"])

    client.force_login(superuser)
    response = client.get(reverse("website:admin_dashboard_comments"))

    content = response.content.decode()
    assert "Match" in content
    assert "Board" in content


@pytest.mark.django_db
def test_comments_panel_excludes_deleted_and_hidden(client, superuser):
    CommentFactory(is_deleted=True, body="deleted comment")
    BoardPostFactory(is_hidden=True, body="hidden post")

    client.force_login(superuser)
    response = client.get(reverse("website:admin_dashboard_comments"))

    content = response.content.decode()
    assert "deleted comment" not in content
    assert "hidden post" not in content


@pytest.mark.django_db
def test_comments_panel_pagination(client, superuser):
    for _ in range(25):
        CommentFactory()

    client.force_login(superuser)
    response = client.get(reverse("website:admin_dashboard_comments"))
    assert "View all" in response.content.decode()


# ---------------------------------------------------------------------------
# Tasks panel
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_tasks_panel_shows_results(client, superuser):
    from django_celery_results.models import TaskResult

    TaskResult.objects.create(
        task_id="test-task-123",
        task_name="matches.tasks.fetch_live_scores",
        status="SUCCESS",
        date_done=timezone.now(),
    )

    client.force_login(superuser)
    response = client.get(reverse("website:admin_dashboard_tasks"))

    content = response.content.decode()
    assert "fetch_live_scores" in content
    assert "SUCCESS" in content


@pytest.mark.django_db
def test_tasks_panel_pagination(client, superuser):
    from django_celery_results.models import TaskResult

    for i in range(25):
        TaskResult.objects.create(
            task_id=f"task-{i}",
            task_name="test.task",
            status="SUCCESS",
            date_done=timezone.now(),
        )

    client.force_login(superuser)
    response = client.get(reverse("website:admin_dashboard_tasks"))
    assert "View all" in response.content.decode()


# ---------------------------------------------------------------------------
# Users panel
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_users_panel_excludes_bots(client, superuser):
    UserFactory(is_bot=True, email="bot@example.com")
    UserFactory(display_name="HumanUser")

    client.force_login(superuser)
    response = client.get(reverse("website:admin_dashboard_users"))

    content = response.content.decode()
    assert "HumanUser" in content
    assert "bot@example.com" not in content


@pytest.mark.django_db
def test_users_panel_pagination(client, superuser):
    for _ in range(25):
        UserFactory()

    client.force_login(superuser)
    response = client.get(reverse("website:admin_dashboard_users"))
    # 26 non-bot users (25 + superuser), so has_more should be True
    assert "View all" in response.content.decode()


# ---------------------------------------------------------------------------
# Activity queue panel
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_activity_queue_shows_pending_events(client, superuser):
    ActivityEvent.objects.create(
        event_type="bot_bet",
        message="BotUser placed a bet on Arsenal v Chelsea",
        icon="lightning",
    )
    # Already broadcast — should NOT appear
    ActivityEvent.objects.create(
        event_type="score_change",
        message="Goal! Arsenal 1-0 Chelsea",
        icon="soccer-ball",
        broadcast_at=timezone.now(),
    )

    client.force_login(superuser)
    response = client.get(reverse("website:admin_dashboard_activity_queue"))

    content = response.content.decode()
    assert "BotUser placed a bet" in content
    assert "Goal! Arsenal" not in content


@pytest.mark.django_db
def test_activity_queue_empty_state(client, superuser):
    client.force_login(superuser)
    response = client.get(reverse("website:admin_dashboard_activity_queue"))

    content = response.content.decode()
    assert "Queue empty" in content


@pytest.mark.django_db
def test_activity_queue_shows_queued_count_in_stats(client, superuser):
    ActivityEvent.objects.create(event_type="bot_bet", message="e1", icon="lightning")
    ActivityEvent.objects.create(event_type="bot_bet", message="e2", icon="lightning")
    ActivityEvent.objects.create(
        event_type="bot_bet", message="e3", icon="lightning",
        broadcast_at=timezone.now(),
    )

    client.force_login(superuser)
    response = client.get(reverse("website:admin_dashboard"))

    assert response.context["queued_events"] == 2
