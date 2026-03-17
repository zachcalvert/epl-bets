"""
Challenge evaluation engine.

Called from betting hooks (bet placement and settlement) to update
challenge progress for the acting user.  Follows the same pattern as
betting/badges.py — a dispatch table of evaluator functions.
"""

import logging
from decimal import Decimal

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import models, transaction
from django.utils import timezone

from challenges.models import Challenge, ChallengeTemplate, UserChallenge

logger = logging.getLogger(__name__)

# Event types that evaluators can react to
PLACEMENT_EVENTS = {"bet_placed", "parlay_placed"}
SETTLEMENT_EVENTS = {"bet_settled", "parlay_settled"}


# ── Evaluators ───────────────────────────────────────────────────────────────
# Each receives (user_challenge, event_type, context) and returns an int
# increment (0 means "does not apply to this event").
#
# For TOTAL_STAKED and BET_ALL_MATCHES the return value is the new absolute
# progress (we overwrite rather than increment).


def _eval_bet_count(uc, event_type, ctx):
    if event_type not in PLACEMENT_EVENTS:
        return 0
    return 1


def _eval_bet_on_underdog(uc, event_type, ctx):
    if event_type not in PLACEMENT_EVENTS:
        return 0
    odds_min = Decimal(uc.challenge.template.criteria_params.get("odds_min", "3.00"))
    if ctx.get("odds") and Decimal(str(ctx["odds"])) >= odds_min:
        return 1
    return 0


def _eval_win_count(uc, event_type, ctx):
    if event_type not in SETTLEMENT_EVENTS:
        return 0
    return 1 if ctx.get("won") else 0


def _eval_win_streak(uc, event_type, ctx):
    """Increment on win, reset to 0 on loss."""
    if event_type not in SETTLEMENT_EVENTS:
        return 0
    if ctx.get("won"):
        return 1
    # Lost — reset progress to 0 (return special sentinel)
    return -uc.progress  # subtracting current progress resets to 0


def _eval_parlay_placed(uc, event_type, ctx):
    if event_type != "parlay_placed":
        return 0
    min_legs = uc.challenge.template.criteria_params.get("min_legs", 2)
    if ctx.get("leg_count", 0) >= min_legs:
        return 1
    return 0


def _eval_parlay_won(uc, event_type, ctx):
    if event_type != "parlay_settled":
        return 0
    return 1 if ctx.get("won") else 0


def _eval_total_staked(uc, event_type, ctx):
    """Progress = cumulative stake during this challenge window.

    We query actual bets rather than just adding, to stay accurate
    across concurrent requests.
    """
    if event_type not in PLACEMENT_EVENTS:
        return 0

    from betting.models import BetSlip, Parlay

    user = uc.user
    challenge = uc.challenge
    singles_total = (
        BetSlip.objects.filter(
            user=user,
            created_at__gte=challenge.starts_at,
            created_at__lte=challenge.ends_at,
        ).aggregate(total=models.Sum("stake"))["total"]
        or Decimal("0")
    )
    parlays_total = (
        Parlay.objects.filter(
            user=user,
            created_at__gte=challenge.starts_at,
            created_at__lte=challenge.ends_at,
        ).aggregate(total=models.Sum("stake"))["total"]
        or Decimal("0")
    )
    new_progress = int(singles_total + parlays_total)
    # Return delta so the update logic works
    return new_progress - uc.progress


def _eval_bet_all_matches(uc, event_type, ctx):
    """Progress = number of distinct matches the user has bet on this matchday."""
    if event_type not in PLACEMENT_EVENTS:
        return 0

    from betting.models import BetSlip

    user = uc.user
    challenge = uc.challenge
    distinct_matches = (
        BetSlip.objects.filter(
            user=user,
            created_at__gte=challenge.starts_at,
            created_at__lte=challenge.ends_at,
        )
        .values("match")
        .distinct()
        .count()
    )
    return distinct_matches - uc.progress


def _eval_correct_predictions(uc, event_type, ctx):
    if event_type not in SETTLEMENT_EVENTS:
        return 0
    return 1 if ctx.get("won") else 0


# ── Dispatch table ───────────────────────────────────────────────────────────

EVALUATORS = {
    ChallengeTemplate.CriteriaType.BET_COUNT: _eval_bet_count,
    ChallengeTemplate.CriteriaType.BET_ON_UNDERDOG: _eval_bet_on_underdog,
    ChallengeTemplate.CriteriaType.WIN_COUNT: _eval_win_count,
    ChallengeTemplate.CriteriaType.WIN_STREAK: _eval_win_streak,
    ChallengeTemplate.CriteriaType.PARLAY_PLACED: _eval_parlay_placed,
    ChallengeTemplate.CriteriaType.PARLAY_WON: _eval_parlay_won,
    ChallengeTemplate.CriteriaType.TOTAL_STAKED: _eval_total_staked,
    ChallengeTemplate.CriteriaType.BET_ALL_MATCHES: _eval_bet_all_matches,
    ChallengeTemplate.CriteriaType.CORRECT_PREDICTIONS: _eval_correct_predictions,
}


# ── Public entry point ───────────────────────────────────────────────────────


def update_challenge_progress(user, event_type, context):
    """
    Evaluate all active challenges for *user* and update progress.

    Called from betting hooks via transaction.on_commit so this runs
    outside the bet's atomic block.

    Args:
        user:       The user who placed/settled a bet.
        event_type: "bet_placed" | "bet_settled" | "parlay_placed" | "parlay_settled"
        context:    Dict with keys like match, odds, stake, won, leg_count, etc.
    """
    active_challenges = Challenge.objects.filter(
        status=Challenge.Status.ACTIVE
    ).select_related("template")

    if not active_challenges:
        return

    # Lazy-enroll user into any active challenges they haven't joined
    existing_challenge_ids = set(
        UserChallenge.objects.filter(
            user=user,
            challenge__in=active_challenges,
        ).values_list("challenge_id", flat=True)
    )

    new_user_challenges = []
    for challenge in active_challenges:
        if challenge.pk not in existing_challenge_ids:
            new_user_challenges.append(
                UserChallenge(
                    user=user,
                    challenge=challenge,
                    target=challenge.target,
                )
            )
    if new_user_challenges:
        UserChallenge.objects.bulk_create(
            new_user_challenges, ignore_conflicts=True
        )

    # Evaluate each in-progress challenge
    user_challenges = (
        UserChallenge.objects.filter(
            user=user,
            challenge__in=active_challenges,
            status=UserChallenge.Status.IN_PROGRESS,
        )
        .select_related("challenge__template")
    )

    for uc in user_challenges:
        criteria_type = uc.challenge.template.criteria_type
        evaluator = EVALUATORS.get(criteria_type)
        if not evaluator:
            logger.warning(
                "No evaluator for criteria_type=%s (challenge=%s)",
                criteria_type,
                uc.challenge.pk,
            )
            continue

        try:
            increment = evaluator(uc, event_type, context)
        except Exception:
            logger.exception(
                "Evaluator error for criteria_type=%s user=%s challenge=%s",
                criteria_type,
                user.pk,
                uc.challenge.pk,
            )
            continue

        if increment == 0:
            continue

        _apply_progress(uc, increment)


def _apply_progress(uc, increment):
    """Atomically update progress and handle completion."""
    from betting.balance import log_transaction
    from betting.models import BalanceTransaction, UserBalance

    with transaction.atomic():
        uc_locked = (
            UserChallenge.objects.select_for_update()
            .get(pk=uc.pk, status=UserChallenge.Status.IN_PROGRESS)
        )

        new_progress = max(uc_locked.progress + increment, 0)
        uc_locked.progress = new_progress

        if new_progress >= uc_locked.target:
            uc_locked.status = UserChallenge.Status.COMPLETED
            uc_locked.completed_at = timezone.now()

            # Credit reward
            reward = uc_locked.challenge.template.reward_amount
            balance, _ = UserBalance.objects.select_for_update().get_or_create(
                user=uc_locked.user
            )
            log_transaction(
                balance, reward,
                BalanceTransaction.Type.CHALLENGE_REWARD,
                f"Challenge: {uc_locked.challenge.template.name}",
            )
            uc_locked.reward_credited = True

            logger.info(
                "Challenge completed: user=%s challenge=%s reward=%s",
                uc_locked.user.pk,
                uc_locked.challenge.pk,
                reward,
            )

        uc_locked.save(
            update_fields=["progress", "status", "completed_at", "reward_credited"]
        )

    # Broadcast celebration outside the atomic block
    if uc_locked.status == UserChallenge.Status.COMPLETED:
        _broadcast_challenge_complete(uc_locked)


def _broadcast_challenge_complete(user_challenge):
    """Send a challenge_notification WS event to the user."""
    try:
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"user_notifications_{user_challenge.user.pk}",
            {
                "type": "challenge_notification",
                "user_challenge_id": user_challenge.pk,
            },
        )
    except Exception:
        logger.exception(
            "Failed to broadcast challenge notification for user_challenge %s",
            user_challenge.pk,
        )
