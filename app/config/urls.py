"""Routes for the foundational M1 Django application."""
from django.contrib import admin
from django.contrib.auth.views import LoginView, LogoutView
from app.accounts.forms import EmailAuthenticationForm
from django.urls import include, path
from app.studio import views
from app.production import views as production_views
from app.production import title_web_views, wikimedia_auto_views, fact_web_views, source_web_views, evidence_web_views, fact_decision_web_views, script_preview_views, scene_storyboard_views, preflight_web_views, research_consent_web_views

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
    path("jobs/<int:job_id>/research/auto-wikimedia/stadium/",
         wikimedia_auto_views.enrich_free_wikimedia_stadium,
         name="research-auto-wikimedia-stadium"),
    path("jobs/<int:job_id>/research/auto-wikimedia/",
         wikimedia_auto_views.start_free_wikimedia_research,
         name="research-auto-wikimedia"),
    path("jobs/<int:job_id>/research/", production_views.research_dossier,
         name="research-job"),
    path("jobs/<int:job_id>/research/facts/new/", fact_web_views.manual_fact_proposal,
         name="research-new-fact"),
    path("jobs/<int:job_id>/research/sources/new/", source_web_views.manual_official_source,
         name="research-new-source"),
    path("jobs/<int:job_id>/research/facts/<int:fact_id>/evidence/new/",
         evidence_web_views.review_evidence, name="research-review-evidence"),
    path("jobs/<int:job_id>/research/facts/<int:fact_id>/decision/",
         fact_decision_web_views.decide_fact_in_browser, name="research-decide-fact"),
    path("jobs/<int:job_id>/research/script-preview/",
         script_preview_views.safe_script_preview, name="research-script-preview"),
    path("jobs/<int:job_id>/research/scenes/",
         scene_storyboard_views.scene_storyboard, name="research-scene-plan"),
    path("jobs/<int:job_id>/research/preflight/",
         preflight_web_views.official_research_preflight,
         name="research-preflight"),
    path("jobs/<int:job_id>/research/requests/source/<int:source_id>/",
         research_consent_web_views.approve_one_time_research,
         name="research-approve-source"),
    path("jobs/<int:job_id>/research/requests/",
         research_consent_web_views.list_research_requests,
         name="research-requests"),
    path("jobs/<int:job_id>/research/requests/<int:request_id>/cancel/",
         research_consent_web_views.cancel_research_request,
         name="research-cancel-request"),
    path("jobs/<int:job_id>/title/", title_web_views.edit_manual_title,
         name="edit-manual-title"),
    path("admin/", admin.site.urls),
]
