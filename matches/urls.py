from django.urls import path

from matches.views import DashboardView, FixturesView, LeagueTableView, MatchDetailView

app_name = "matches"

urlpatterns = [
    path("", DashboardView.as_view(), name="dashboard"),
    path("fixtures/", FixturesView.as_view(), name="fixtures"),
    path("table/", LeagueTableView.as_view(), name="table"),
    path("match/<int:pk>/", MatchDetailView.as_view(), name="match_detail"),
]
