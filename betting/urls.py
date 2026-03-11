from django.urls import path

from betting.views import OddsBoardPartialView, OddsBoardView

app_name = "betting"

urlpatterns = [
    path("", OddsBoardView.as_view(), name="odds"),
    path("partial/", OddsBoardPartialView.as_view(), name="odds_partial"),
]
