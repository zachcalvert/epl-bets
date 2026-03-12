from django.urls import path

from matches.views import (
    DashboardView,
    FixturesView,
    LeaderboardPartialView,
    LeagueTableView,
    MatchDetailView,
    MatchOddsPartialView,
)

app_name = "matches"

urlpatterns = [
    path("", DashboardView.as_view(), name="dashboard"),
    path("leaderboard/", LeaderboardPartialView.as_view(), name="leaderboard_partial"),
    path("fixtures/", FixturesView.as_view(), name="fixtures"),
    path("table/", LeagueTableView.as_view(), name="table"),
    path("match/<int:pk>/", MatchDetailView.as_view(), name="match_detail"),
    path("match/<int:pk>/odds/", MatchOddsPartialView.as_view(), name="match_odds_partial"),
]
