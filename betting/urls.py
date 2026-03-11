from django.urls import path

from betting.views import (
    MyBetsView,
    OddsBoardPartialView,
    OddsBoardView,
    PlaceBetView,
    QuickBetFormView,
)

app_name = "betting"

urlpatterns = [
    path("", OddsBoardView.as_view(), name="odds"),
    path("partial/", OddsBoardPartialView.as_view(), name="odds_partial"),
    path("place/<int:match_pk>/", PlaceBetView.as_view(), name="place_bet"),
    path("my-bets/", MyBetsView.as_view(), name="my_bets"),
    path("quick-bet/<int:match_pk>/", QuickBetFormView.as_view(), name="quick_bet_form"),
]
