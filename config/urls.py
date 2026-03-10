from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("config.api_urls")),
    path("matches/", include("matches.urls")),
    path("betting/", include("betting.urls")),
    path("", include("website.urls")),
]
