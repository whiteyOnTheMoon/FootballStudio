"""Authenticated API endpoints for live club selection."""
from django.urls import path

from . import views

app_name = "clubs"

urlpatterns = [
    path("countries/", views.countries, name="countries"),
    path("leagues/", views.leagues, name="leagues"),
    path("clubs/", views.clubs, name="clubs"),
    path("selection/", views.selection, name="selection"),
    path("manual/", views.create_manual_club, name="manual"),
]
