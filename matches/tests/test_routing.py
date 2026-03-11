from matches.routing import websocket_urlpatterns


def test_websocket_routing_pattern_targets_live_updates_consumer():
    pattern = websocket_urlpatterns[0]

    assert pattern.pattern.regex.pattern == r"ws/live/(?P<scope>\w+)/$"
