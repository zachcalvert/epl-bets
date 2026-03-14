from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path

urlpatterns = [
    path("healthz", lambda r: HttpResponse("ok"), name="healthz"),
    path("admin/", admin.site.urls),
    path("api/", include("config.api_urls")),
    path("odds/", include("betting.urls")),
    path("", include("rewards.urls")),
    path("", include("website.urls")),
    path("", include("matches.urls")),
]
