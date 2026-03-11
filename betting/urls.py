from django.urls import path

from betting.views import OddsBoardView

app_name = "betting"

urlpatterns = [
    path("", OddsBoardView.as_view(), name="odds"),
]
