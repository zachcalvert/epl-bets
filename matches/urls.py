from django.urls import path
from django.views.generic import RedirectView

from matches.views import (
    DashboardUnderTheHoodPartialView,
    DashboardView,
    LeaderboardPartialView,
    LeaderboardView,
    LeagueTableView,
    MatchDetailView,
    MatchOddsPartialView,
    MatchStatusCardPartialView,
    MatchUnderTheHoodPartialView,
)

app_name = "matches"

urlpatterns = [
    path("", DashboardView.as_view(), name="dashboard"),
    path(
        "under-the-hood/",
        DashboardUnderTheHoodPartialView.as_view(),
        name="dashboard_under_the_hood",
    ),
    path("leaderboard/", LeaderboardView.as_view(), name="leaderboard"),
    path("leaderboard/partial/", LeaderboardPartialView.as_view(), name="leaderboard_partial"),
    path("fixtures/", RedirectView.as_view(url="/", permanent=True), name="fixtures"),
    path("table/", LeagueTableView.as_view(), name="table"),
    path("match/<int:pk>/", MatchDetailView.as_view(), name="match_detail"),
    path(
        "match/<int:pk>/under-the-hood/",
        MatchUnderTheHoodPartialView.as_view(),
        name="match_under_the_hood",
    ),
    path(
        "match/<int:pk>/status-card/",
        MatchStatusCardPartialView.as_view(),
        name="match_status_card",
    ),
    path("match/<int:pk>/odds/", MatchOddsPartialView.as_view(), name="match_odds_partial"),
]
