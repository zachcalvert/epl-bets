import logging

from celery import shared_task

from betting.services import sync_odds
from website.transparency import GLOBAL_SCOPE, match_scope, page_scope, record_event

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def fetch_odds(self):
    logger.info("fetch_odds: starting")
    try:
        created, updated = sync_odds()
        logger.info("fetch_odds: done created=%d updated=%d", created, updated)
        record_event(
            scope=page_scope("odds_board"),
            scopes=[GLOBAL_SCOPE, page_scope("match_detail")],
            category="celery",
            source="fetch_odds",
            action="odds_synced",
            summary="Odds sync completed.",
            detail=f"Created {created} bookmaker rows and updated {updated} existing rows.",
            status="success",
        )
    except Exception as exc:
        logger.exception("fetch_odds failed")
        raise self.retry(exc=exc, countdown=120 * (2 ** self.request.retries))


@shared_task(bind=True, max_retries=3)
def settle_match_bets(self, match_id):
    """
    Settle all pending bets for a finished match.

    Called when a match transitions to FINISHED, CANCELLED, or POSTPONED.
    """
    from django.db import transaction

    from betting.models import BetSlip, UserBalance
    from matches.models import Match

    logger.info("settle_match_bets: starting for match %d", match_id)

    try:
        match = Match.objects.select_related("home_team", "away_team").get(pk=match_id)
    except Match.DoesNotExist:
        logger.error("settle_match_bets: match %d not found", match_id)
        return

    pending_bets = BetSlip.objects.filter(match=match, status=BetSlip.Status.PENDING)
    if not pending_bets.exists():
        logger.info("settle_match_bets: no pending bets for match %d", match_id)
        return

    # Handle void scenarios (cancelled/postponed)
    if match.status in (Match.Status.CANCELLED, Match.Status.POSTPONED):
        for bet in pending_bets.select_related("user"):
            with transaction.atomic():
                bet.status = BetSlip.Status.VOID
                bet.payout = bet.stake  # refund
                bet.save(update_fields=["status", "payout"])

                balance = UserBalance.objects.select_for_update().get(user=bet.user)
                balance.balance += bet.stake
                balance.save(update_fields=["balance"])

        logger.info(
            "settle_match_bets: voided %d bets for %s match %d",
            pending_bets.count(),
            match.status,
            match_id,
        )
        record_event(
            scope=match_scope(match_id),
            scopes=[GLOBAL_SCOPE, page_scope("match_detail")],
            category="betting",
            source="settle_match_bets",
            action="bets_voided",
            summary=f"Bets voided for match {match_id}.",
            detail=f"Refunded {pending_bets.count()} pending bets after status changed to {match.status}.",
            status="warning",
            entity_ref=match_id,
        )
        return

    # Match must be finished to settle
    if match.status != Match.Status.FINISHED:
        logger.warning(
            "settle_match_bets: match %d status is %s, not FINISHED",
            match_id,
            match.status,
        )
        return

    # Determine the result
    if match.home_score is None or match.away_score is None:
        logger.error("settle_match_bets: match %d has no scores", match_id)
        return

    if match.home_score > match.away_score:
        winning_selection = BetSlip.Selection.HOME_WIN
    elif match.home_score < match.away_score:
        winning_selection = BetSlip.Selection.AWAY_WIN
    else:
        winning_selection = BetSlip.Selection.DRAW

    won_count = 0
    lost_count = 0

    for bet in pending_bets.select_related("user"):
        with transaction.atomic():
            if bet.selection == winning_selection:
                payout = bet.stake * bet.odds_at_placement
                bet.status = BetSlip.Status.WON
                bet.payout = payout
                bet.save(update_fields=["status", "payout"])

                balance = UserBalance.objects.select_for_update().get(user=bet.user)
                balance.balance += payout
                balance.save(update_fields=["balance"])
                won_count += 1
            else:
                bet.status = BetSlip.Status.LOST
                bet.payout = 0
                bet.save(update_fields=["status", "payout"])
                lost_count += 1

    logger.info(
        "settle_match_bets: match %d settled — %d won, %d lost",
        match_id,
        won_count,
        lost_count,
    )
    record_event(
        scope=match_scope(match_id),
        scopes=[GLOBAL_SCOPE, page_scope("match_detail")],
        category="betting",
        source="settle_match_bets",
        action="bets_settled",
        summary=f"Bet settlement finished for match {match_id}.",
        detail=f"{won_count} winning slips and {lost_count} losing slips were processed.",
        status="success",
        entity_ref=match_id,
    )
