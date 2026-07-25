from django.urls import path

from . import views

urlpatterns = [
    path("patient", views.patient, name="patient"),
    path("disease-contexts", views.disease_contexts, name="disease-contexts"),
    path("drugs", views.drugs, name="drugs"),
    path("conditions", views.conditions, name="conditions"),
    path("conditions/<uuid:condition_id>", views.condition_detail, name="condition-detail"),
    path("visits", views.visits, name="visits"),
    path("visits/<uuid:visit_id>", views.visit_detail, name="visit-detail"),
    path("timeline", views.timeline, name="timeline"),
    path("summarise", views.summarise, name="summarise"),
    path("checkin/context", views.checkin_context, name="checkin-context"),
    path("checkin/session", views.checkin_session, name="checkin-session"),
    path("checkin", views.checkin, name="checkin"),
    path("plan", views.plan, name="plan"),
    path("events", views.events, name="events"),
    path("brief", views.brief, name="brief"),
    path("ask", views.ask, name="ask"),
    path("reset", views.reset, name="reset"),
]
