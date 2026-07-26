from django.urls import path

from . import views

urlpatterns = [
    path("auth/signup", views.signup, name="signup"),
    path("auth/login", views.login, name="login"),
    path("auth/me", views.me, name="me"),
    path("patient", views.patient, name="patient"),
    path("disease-contexts", views.disease_contexts, name="disease-contexts"),
    path("drugs", views.drugs, name="drugs"),
    path("conditions", views.conditions, name="conditions"),
    path("conditions/<uuid:condition_id>", views.condition_detail, name="condition-detail"),
    path("visits", views.visits, name="visits"),
    path("visits/<uuid:visit_id>", views.visit_detail, name="visit-detail"),
    path("timeline", views.timeline, name="timeline"),
    path("caretaker", views.caretaker_context, name="caretaker-context"),
    path("medications", views.medications, name="medications"),
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
