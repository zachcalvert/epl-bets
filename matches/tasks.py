import logging

from celery import shared_task
from django.conf import settings

from matches.services import sync_matches, sync_standings, sync_teams
from website.transparency import GLOBAL_SCOPE, match_scope, page_scope, record_event

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def fetch_teams(self):
    logger.info("fetch_teams: starting")
    try:
        created, updated = sync_teams(settings.CURRENT_SEASON)
        logger.info("fetch_teams: done created=%d updated=%d", created, updated)
    except Exception as exc:
        logger.exception("fetch_teams failed")
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@shared_task(bind=True, max_retries=3)
def fetch_fixtures(self):
    logger.info("fetch_fixtures: starting")
    try:
        created, updated = sync_matches(settings.CURRENT_SEASON)
        logger.info("fetch_fixtures: done created=%d updated=%d", created, updated)
    except Exception as exc:
        logger.exception("fetch_fixtures failed")
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@shared_task(bind=True, max_retries=3)
def fetch_standings(self):
    logger.info("fetch_standings: starting")
    try:
        created, updated = sync_standings(settings.CURRENT_SEASON)
        logger.info("fetch_standings: done created=%d updated=%d", created, updated)
    except Exception as exc:
        logger.exception("fetch_standings failed")
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@shared_task(bind=True, max_retries=3)
def fetch_live_scores(self):
    logger.info("fetch_live_scores: starting")
    try:
        # Snapshot live matches before sync to detect changes
        from matches.models import Match

        pre_sync = {
            m["pk"]: (m["home_score"], m["away_score"], m["status"])
            for m in Match.objects.filter(
                status__in=["IN_PLAY", "PAUSED", "FINISHED"],
                season=settings.CURRENT_SEASON,
            ).values("pk", "home_score", "away_score", "status")
        }

        created, updated = sync_matches(settings.CURRENT_SEASON, status="LIVE")
        logger.info("fetch_live_scores: done created=%d updated=%d", created, updated)
        record_event(
            scope=page_scope("dashboard"),
            scopes=[GLOBAL_SCOPE],
            category="celery",
            source="fetch_live_scores",
            action="scores_synced",
            summary="Live score sync completed.",
            detail=f"Updated {updated} matches and created {created} live records.",
            status="success",
        )

        # Broadcast changes via channel layer
        if updated > 0 or created > 0:
            _broadcast_score_changes(pre_sync)

    except Exception as exc:
        logger.exception("fetch_live_scores failed")
        raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))


def _broadcast_score_changes(pre_sync):
    """Compare current match state to pre-sync snapshot and broadcast changes."""
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer

    from matches.models import Match

    channel_layer = get_channel_layer()
    if not channel_layer:
        logger.warning("No channel layer configured, skipping broadcast")
        return

    send = async_to_sync(channel_layer.group_send)

    # Check all matches that were live or just finished
    current = Match.objects.filter(
        pk__in=list(pre_sync.keys())
    ).union(
        Match.objects.filter(
            status__in=["IN_PLAY", "PAUSED"],
            season=settings.CURRENT_SEASON,
        )
    ).values("pk", "home_score", "away_score", "status")

    for m in current:
        pk = m["pk"]
        old = pre_sync.get(pk)
        new_state = (m["home_score"], m["away_score"], m["status"])

        # Broadcast if score changed, status changed, or this is a newly live match
        if old is None or old != new_state:
            logger.info("Broadcasting score update for match %d", pk)
            send("live_scores", {"type": "score_update", "match_id": pk})
            send(f"match_{pk}", {"type": "match_score_update", "match_id": pk})
            record_event(
                scope=match_scope(pk),
                scopes=[GLOBAL_SCOPE, page_scope("dashboard"), page_scope("match_detail")],
                category="websocket",
                source="score_broadcast",
                action="score_broadcast",
                summary=f"Live score broadcast sent for match {pk}.",
                detail=f"Score/state changed from {old} to {new_state}.",
                status="info",
                entity_ref=pk,
            )

            # Trigger bet settlement when a match finishes
            old_status = old[2] if old else None
            new_status = m["status"]
            if new_status in ("FINISHED", "CANCELLED", "POSTPONED") and old_status != new_status:
                from betting.tasks import settle_match_bets

                logger.info("Triggering bet settlement for match %d (status: %s)", pk, new_status)
                settle_match_bets.delay(pk)
