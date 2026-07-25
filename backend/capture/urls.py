from django.urls import path

from . import views

urlpatterns = [
    path("transcribe", views.transcribe, name="transcribe"),
    path("summarise", views.summarise, name="summarise"),
]
