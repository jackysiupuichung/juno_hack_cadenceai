"""URL configuration for the Cadence backend."""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("capture.urls")),
    path("api/", include("loop.urls")),
]
