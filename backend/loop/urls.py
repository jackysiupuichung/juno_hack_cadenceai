from django.urls import path

from . import views

urlpatterns = [
    path("timeline", views.timeline, name="timeline"),
    path("summarise", views.summarise, name="summarise"),
    path("checkin", views.checkin, name="checkin"),
    path("brief", views.brief, name="brief"),
    path("reset", views.reset, name="reset"),
]
