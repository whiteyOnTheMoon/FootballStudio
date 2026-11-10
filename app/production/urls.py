"""M1 test-job API: no rendering endpoint yet."""
from django.urls import path

from . import views

app_name = "production"

urlpatterns = [
    path("test/", views.create_test_job, name="create-test"),
    path("list/", views.test_job_list, name="list"),
]
