import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

django_asgi = get_asgi_application()

from activity.routing import websocket_urlpatterns as activity_ws  # noqa: E402
from matches.routing import websocket_urlpatterns as matches_ws  # noqa: E402
from rewards.routing import websocket_urlpatterns as rewards_ws  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi,
        "websocket": AuthMiddlewareStack(
            URLRouter(matches_ws + rewards_ws + activity_ws)
        ),
    }
)
