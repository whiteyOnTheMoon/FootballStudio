"""Routes for the foundational M1 Django application."""
from django.contrib import admin
from django.contrib.auth.views import LoginView, LogoutView
from app.accounts.forms import EmailAuthenticationForm
from django.urls import include, path
from app.studio import views
from app.production import views as production_views

urlpatterns = [
    path("", views.home, name="home"),
    path("accounts/login/", LoginView.as_view(
        template_name="registration/login.html",
        authentication_form=EmailAuthenticationForm,
        redirect_authenticated_user=True,
    ), name="login"),
    path("accounts/logout/", LogoutView.as_view(next_page="login"), name="logout"),
    path("healthz/", views.healthz, name="healthz"),
    path("clubs/api/", include(("app.clubs.urls", "clubs"), namespace="clubs")),
    path("jobs/api/", include(("app.production.urls", "production"), namespace="production")),
    path("jobs/<int:job_id>/research/", production_views.research_dossier,
         name="research-job"),
    path("admin/", admin.site.urls),
]
