from rewards.routing import websocket_urlpatterns


def test_websocket_routing_pattern_targets_notification_consumer():
    pattern = websocket_urlpatterns[0]

    assert pattern.pattern._route == "ws/notifications/"
