from website.transparency import (
    GLOBAL_SCOPE,
    clear_events,
    get_events,
    match_scope,
    page_scope,
    record_event,
)


def test_record_event_stores_it_in_primary_and_extra_scopes():
    dashboard_scope = page_scope("dashboard")
    clear_events(dashboard_scope, GLOBAL_SCOPE)

    event = record_event(
        scope=dashboard_scope,
        scopes=[GLOBAL_SCOPE],
        category="htmx",
        source="leaderboard_partial",
        action="partial_refreshed",
        summary="Leaderboard refreshed.",
    )

    assert get_events(dashboard_scope) == [event]
    assert get_events(GLOBAL_SCOPE) == [event]


def test_record_event_trims_scope_to_most_recent_25_events():
    scope = match_scope(101)
    clear_events(scope)

    for index in range(30):
        record_event(
            scope=scope,
            category="websocket",
            source="match_detail",
            action="score_broadcast",
            summary=f"Event {index}",
        )

    events = get_events(scope, limit=30)

    assert len(events) == 25
    assert events[0]["summary"] == "Event 29"
    assert events[-1]["summary"] == "Event 5"


def test_get_events_returns_requested_limit():
    scope = page_scope("odds_board")
    clear_events(scope)

    for index in range(3):
        record_event(
            scope=scope,
            category="celery",
            source="fetch_odds",
            action="odds_synced",
            summary=f"Odds sync {index}",
        )

    events = get_events(scope, limit=2)

    assert [event["summary"] for event in events] == ["Odds sync 2", "Odds sync 1"]
