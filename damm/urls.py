from django.urls import path
from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("distribucion", views.distribucion, name="distribucion"),
    path("mapa", views.mapa, name="mapa"),
]