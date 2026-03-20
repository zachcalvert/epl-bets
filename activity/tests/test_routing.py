from activity.routing import websocket_urlpatterns


class TestActivityRouting:
    def test_websocket_url_pattern_registered(self):
        paths = [str(p.pattern) for p in websocket_urlpatterns]
        assert "ws/activity/" in paths

    def test_single_route_defined(self):
        assert len(websocket_urlpatterns) == 1
