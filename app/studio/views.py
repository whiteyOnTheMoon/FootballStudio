"""No production features yet: this is the M1 project foundation."""
from django.contrib.auth.decorators import login_required
from django.db import connections
from django.db.utils import DatabaseError
from django.http import HttpResponse, HttpResponseServerError
from django.shortcuts import render


@login_required
def home(request):
    return render(request, "studio/home.html")


def healthz(request):
    """Minimal readiness probe: require an available PostgreSQL/SQLite connection."""
    try:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
            if cursor.fetchone()[0] != 1:
                return HttpResponseServerError("unavailable", content_type="text/plain")
    except DatabaseError:
        # No internal database error or connection details in HTTP responses.
        return HttpResponseServerError("unavailable", content_type="text/plain")
    return HttpResponse("ok", content_type="text/plain")
