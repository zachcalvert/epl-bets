"""
Celery tasks for challenge rotation and expiration.
"""

import logging
import random
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from challenges.models import Challenge, ChallengeTemplate, UserChallenge

logger = logging.getLogger(__name__)

# How many challenges to activate per rotation
DAILY_COUNT = 3
WEEKLY_COUNT = 2

# How far back to look when avoiding repeats
DAILY_LOOKBACK_DAYS = 7
WEEKLY_LOOKBACK_DAYS = 21


def _recently_used_template_ids(challenge_type, lookback_days):
    """Return template IDs used in recent challenges to avoid repetition."""
    cutoff = timezone.now() - timedelta(days=lookback_days)
    return set(
        Challenge.objects.filter(
            template__challenge_type=challenge_type,
            starts_at__gte=cutoff,
        ).values_list("template_id", flat=True)
    )


def _has_matches_today():
    """Check if there are any EPL matches today (or tomorrow for dailies)."""
    from matches.models import Match

    today = timezone.now().date()
    tomorrow = today + timedelta(days=1)
    return Match.objects.filter(
        kickoff__date__gte=today,
        kickoff__date__lte=tomorrow,
        status__in=[Match.Status.SCHEDULED, Match.Status.TIMED],
    ).exists()


def _get_current_matchday():
    """Return the current/next matchday number."""
    from matches.models import Match

    upcoming = (
        Match.objects.filter(
            status__in=[Match.Status.SCHEDULED, Match.Status.TIMED],
        )
        .order_by("kickoff")
        .values_list("matchday", flat=True)
        .first()
    )
    return upcoming


def _expire_and_fail(challenge_type=None, queryset=None):
    """Expire challenges and mark in-progress UserChallenges as FAILED."""
    if queryset is None:
        queryset = Challenge.objects.filter(
            template__challenge_type=challenge_type,
            status=Challenge.Status.ACTIVE,
        )

    challenge_ids = list(queryset.values_list("pk", flat=True))
    if not challenge_ids:
        return 0

    # Fail in-progress user challenges
    failed_count = UserChallenge.objects.filter(
        challenge_id__in=challenge_ids,
        status=UserChallenge.Status.IN_PROGRESS,
    ).update(status=UserChallenge.Status.FAILED)

    # Expire the challenges
    expired_count = Challenge.objects.filter(pk__in=challenge_ids).update(
        status=Challenge.Status.EXPIRED
    )

    logger.info(
        "Expired %d challenges, failed %d user challenges (type=%s)",
        expired_count,
        failed_count,
        challenge_type,
    )
    return expired_count


@shared_task(max_retries=1)
def rotate_daily_challenges():
    """Expire yesterday's daily challenges and create new ones."""
    # Expire active dailies
    _expire_and_fail(challenge_type=ChallengeTemplate.ChallengeType.DAILY)

    # Skip if no matches today/tomorrow (international break)
    if not _has_matches_today():
        logger.info("No matches today — skipping daily challenge creation.")
        return "skipped: no matches"

    # Pick templates avoiding recent repeats
    recent_ids = _recently_used_template_ids(
        ChallengeTemplate.ChallengeType.DAILY, DAILY_LOOKBACK_DAYS
    )
    candidates = list(
        ChallengeTemplate.objects.filter(
            challenge_type=ChallengeTemplate.ChallengeType.DAILY,
            is_active=True,
        ).exclude(pk__in=recent_ids)
    )

    # Fall back to all active templates if not enough candidates
    if len(candidates) < DAILY_COUNT:
        candidates = list(
            ChallengeTemplate.objects.filter(
                challenge_type=ChallengeTemplate.ChallengeType.DAILY,
                is_active=True,
            )
        )

    selected = random.sample(candidates, min(DAILY_COUNT, len(candidates)))

    now = timezone.now()
    # Daily challenges expire at the next 5 AM UTC
    tomorrow_5am = now.replace(hour=5, minute=0, second=0, microsecond=0)
    if tomorrow_5am <= now:
        tomorrow_5am += timedelta(days=1)

    created = []
    for template in selected:
        challenge = Challenge.objects.create(
            template=template,
            status=Challenge.Status.ACTIVE,
            starts_at=now,
            ends_at=tomorrow_5am,
        )
        created.append(challenge)

    logger.info("Created %d daily challenges: %s", len(created), [c.pk for c in created])
    return f"created: {len(created)}"


@shared_task(max_retries=1)
def rotate_weekly_challenges():
    """Expire last week's weekly challenges and create new ones."""
    _expire_and_fail(challenge_type=ChallengeTemplate.ChallengeType.WEEKLY)

    matchday = _get_current_matchday()
    if matchday is None:
        logger.info("No upcoming matchday — skipping weekly challenge creation.")
        return "skipped: no matchday"

    recent_ids = _recently_used_template_ids(
        ChallengeTemplate.ChallengeType.WEEKLY, WEEKLY_LOOKBACK_DAYS
    )
    candidates = list(
        ChallengeTemplate.objects.filter(
            challenge_type=ChallengeTemplate.ChallengeType.WEEKLY,
            is_active=True,
        ).exclude(pk__in=recent_ids)
    )

    if len(candidates) < WEEKLY_COUNT:
        candidates = list(
            ChallengeTemplate.objects.filter(
                challenge_type=ChallengeTemplate.ChallengeType.WEEKLY,
                is_active=True,
            )
        )

    selected = random.sample(candidates, min(WEEKLY_COUNT, len(candidates)))

    now = timezone.now()
    # Weekly challenges end next Tuesday at 5 AM UTC
    days_until_tuesday = (1 - now.weekday()) % 7
    if days_until_tuesday == 0:
        days_until_tuesday = 7
    next_tuesday_5am = (now + timedelta(days=days_until_tuesday)).replace(
        hour=5, minute=0, second=0, microsecond=0
    )

    # Determine actual match count for BET_ALL_MATCHES challenges
    from matches.models import Match

    matchday_match_count = Match.objects.filter(matchday=matchday).count()

    created = []
    for template in selected:
        # Override target for BET_ALL_MATCHES with actual match count
        if template.criteria_type == ChallengeTemplate.CriteriaType.BET_ALL_MATCHES:
            template.criteria_params = {
                **template.criteria_params,
                "target": matchday_match_count or 10,
            }
            template.save(update_fields=["criteria_params"])

        challenge = Challenge.objects.create(
            template=template,
            status=Challenge.Status.ACTIVE,
            starts_at=now,
            ends_at=next_tuesday_5am,
            matchday=matchday,
        )
        created.append(challenge)

    logger.info(
        "Created %d weekly challenges for matchday %s: %s",
        len(created),
        matchday,
        [c.pk for c in created],
    )
    return f"created: {len(created)}"


@shared_task(max_retries=1)
def expire_challenges():
    """Catch-all: expire any past-due ACTIVE challenges."""
    now = timezone.now()
    overdue = Challenge.objects.filter(
        status=Challenge.Status.ACTIVE,
        ends_at__lte=now,
    )
    count = _expire_and_fail(queryset=overdue)
    if count:
        logger.info("expire_challenges: expired %d overdue challenges", count)
    return f"expired: {count}"
