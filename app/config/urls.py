"""Routes for the foundational M1 Django application."""
from django.contrib import admin
from django.urls import path
from app.studio import views

urlpatterns = [
    path("", views.home, name="home"),
    path("healthz/", views.healthz, name="healthz"),
    path("admin/", admin.site.urls),
]
