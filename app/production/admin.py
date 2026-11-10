"""Admin inspection of prototype jobs; the client UI uses owner-scoped APIs."""
from django.contrib import admin

from .models import ProductionJob


@admin.register(ProductionJob)
class ProductionJobAdmin(admin.ModelAdmin):
    list_display = (
        "id", "club_name", "league_name", "country_code",
        "kind", "status", "owner", "created_at",
    )
    list_filter = ("kind", "status", "language", "country_code")
    search_fields = ("club_name", "title", "owner__email")
    readonly_fields = (
        "owner", "club", "country_code", "league_name", "club_name",
        "kind", "language", "status", "title", "created_at", "updated_at",
        "started_at", "finished_at", "output_path", "error_message",
    )
    def has_add_permission(self, request):
        return False
