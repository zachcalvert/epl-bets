import logging
from decimal import Decimal

from celery import shared_task
from django.db import transaction

from betting.models import BetSlip, Parlay, ParlayLeg, UserBalance
from betting.services import sync_odds
from matches.models import Match
from website.transparency import GLOBAL_SCOPE, match_scope, page_scope, record_event

logger = logging.getLogger(__name__)


def settle_parlay_legs(match, winning_selection):
    """
    Settle all pending ParlayLeg records for a given match.

    `winning_selection` is a BetSlip.Selection value, or None if the match
    was cancelled/postponed (all legs voided).

    After settling legs, evaluate each affected parlay.
    """

    pending_legs = ParlayLeg.objects.filter(
        match=match, status=ParlayLeg.Status.PENDING
    ).select_related("parlay")

    if not pending_legs.exists():
        return

    affected_parlay_ids = set()

    for leg in pending_legs:
        if winning_selection is None:
            # Cancelled / postponed — void this leg
            leg.status = ParlayLeg.Status.VOID
        elif leg.selection == winning_selection:
            leg.status = ParlayLeg.Status.WON
        else:
            leg.status = ParlayLeg.Status.LOST
        leg.save(update_fields=["status"])
        affected_parlay_ids.add(leg.parlay_id)

    # Evaluate each affected parlay now that legs have been updated
    for parlay_id in affected_parlay_ids:
        try:
            _evaluate_parlay(parlay_id)
        except Exception:
            logger.exception("settle_parlay_legs: error evaluating parlay %d", parlay_id)


def _recalculate_combined_odds(parlay, legs):
    """Recalculate combined_odds using only non-VOID legs. Updates parlay in place."""
    active_legs = [leg for leg in legs if leg.status != ParlayLeg.Status.VOID]
    if not active_legs:
        parlay.combined_odds = Decimal("1.00")
    else:
        combined = Decimal("1.00")
        for leg in active_legs:
            combined *= leg.odds_at_placement
        parlay.combined_odds = combined.quantize(Decimal("0.01"))


def _evaluate_parlay(parlay_id):
    """
    Inspect all legs of a parlay and settle it if all legs are resolved.

    States:
      - any LOST  → parlay LOST
      - any PENDING → still waiting (recalc odds if voids exist)
      - all VOID  → parlay VOID, refund stake
      - all settled, no LOST, some WON → parlay WON
    """
    try:
        with transaction.atomic():
            parlay = Parlay.objects.select_for_update().get(pk=parlay_id)
            if parlay.status != Parlay.Status.PENDING:
                return

            legs = list(parlay.legs.all())
            if not legs:
                logger.error("_evaluate_parlay: parlay %d has no legs — marking LOST", parlay_id)
                parlay.status = Parlay.Status.LOST
                parlay.payout = Decimal("0")
                parlay.save(update_fields=["status", "payout"])
                return

            statuses = {leg.status for leg in legs}

            if ParlayLeg.Status.LOST in statuses:
                parlay.status = Parlay.Status.LOST
                parlay.payout = Decimal("0")
                parlay.save(update_fields=["status", "payout"])
                logger.info("_evaluate_parlay: parlay %d LOST", parlay_id)
                return

            if ParlayLeg.Status.PENDING in statuses:
                # Still waiting — recalc odds if any voids have appeared
                if ParlayLeg.Status.VOID in statuses:
                    _recalculate_combined_odds(parlay, legs)
                    parlay.save(update_fields=["combined_odds"])
                return

            # All legs settled (WON and/or VOID, no PENDING, no LOST)
            if all(leg.status == ParlayLeg.Status.VOID for leg in legs):
                # Every leg voided — refund full stake
                parlay.status = Parlay.Status.VOID
                parlay.payout = parlay.stake
                parlay.save(update_fields=["status", "payout"])

                balance = UserBalance.objects.select_for_update().get(user=parlay.user)
                balance.balance += parlay.stake
                balance.save(update_fields=["balance"])
                logger.info("_evaluate_parlay: parlay %d VOID — refunded %s", parlay_id, parlay.stake)
                return

            # Mix of WON and VOID — recalculate odds on active legs and pay out
            _recalculate_combined_odds(parlay, legs)
            payout = min(parlay.stake * parlay.combined_odds, parlay.max_payout)
            parlay.status = Parlay.Status.WON
            parlay.payout = payout
            parlay.save(update_fields=["status", "payout", "combined_odds"])

            balance = UserBalance.objects.select_for_update().get(user=parlay.user)
            balance.balance += payout
            balance.save(update_fields=["balance"])
            logger.info(
                "_evaluate_parlay: parlay %d WON — payout %s (combined odds %s)",
                parlay_id,
                payout,
                parlay.combined_odds,
            )

    except Parlay.DoesNotExist:
        logger.error("_evaluate_parlay: parlay %d not found", parlay_id)


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
    logger.info("settle_match_bets: starting for match %d", match_id)

    try:
        match = Match.objects.select_related("home_team", "away_team").get(pk=match_id)
    except Match.DoesNotExist:
        logger.error("settle_match_bets: match %d not found", match_id)
        return

    pending_bets = BetSlip.objects.filter(match=match, status=BetSlip.Status.PENDING)
    pending_parlay_legs = ParlayLeg.objects.filter(match=match, status=ParlayLeg.Status.PENDING)
    if not pending_bets.exists() and not pending_parlay_legs.exists():
        logger.info("settle_match_bets: no pending bets or parlay legs for match %d", match_id)
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
        # Settle parlay legs for this voided match
        settle_parlay_legs(match, winning_selection=None)
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
    # Settle parlay legs for this match
    settle_parlay_legs(match, winning_selection)
