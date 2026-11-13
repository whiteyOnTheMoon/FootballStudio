"""M1 test-job API: no rendering endpoint yet."""
from django.urls import path

from . import film_views, views

app_name = "production"

urlpatterns = [
    path("test/", views.create_test_job, name="create-test"),
    path("film/", film_views.create_film_request, name="create-film"),
    path("film/<int:job_id>/", film_views.film_status_json, name="film-status"),
    path("list/", views.test_job_list, name="list"),
]
