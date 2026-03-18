from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path

from betting.views import BalanceHistoryAPI, ProfileView

urlpatterns = [
    path("healthz", lambda r: HttpResponse("ok"), name="healthz"),
    path("admin/", admin.site.urls),
    path("api/", include("config.api_urls")),
    path("api/balance-history/<int:user_pk>/", BalanceHistoryAPI.as_view(), name="balance_history_api"),
    path("odds/", include("betting.urls")),
    path("profile/<int:user_pk>/", ProfileView.as_view(), name="profile"),
    path("", include("discussions.urls")),
    path("", include("challenges.urls")),
    path("", include("rewards.urls")),
    path("", include("website.urls")),
    path("", include("matches.urls")),
]
