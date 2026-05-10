from django.urls import path
from . import views

urlpatterns = [
    path("", views.index, name="index"),

    path("dashboard", views.dashboard, name="dashboard"),
    path("dashboard/", views.dashboard, name="dashboard"),

    path("mapa", views.mapa, name="mapa"),
    path("mapa/", views.mapa, name="mapa"),

    path("distribucion", views.distribucion, name="distribucion"),
    path("distribucion/", views.distribucion, name="distribucion"),

    path("api/dashboard/", views.api_dashboard, name="api_dashboard"),
    path("api/route/", views.api_route, name="api_route"),
    path("api/load-plan/", views.api_load_plan, name="api_load_plan"),
    path("api/gemini-chat", views.api_gemini_chat, name="api_gemini_chat"),
    path("api/gemini-chat/", views.api_gemini_chat, name="api_gemini_chat"),
]
