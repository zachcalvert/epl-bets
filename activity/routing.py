from django.urls import path

from activity.consumers import ActivityConsumer

websocket_urlpatterns = [
    path("ws/activity/", ActivityConsumer.as_asgi()),
]
