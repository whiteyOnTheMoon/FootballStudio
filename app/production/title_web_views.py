"""FS-015b: explicit manual title editing for owned M1 prototype jobs.

No automatic suggestions or paid requests. A stale edit never replaces a newer
title. Existing film jobs cannot have their titles changed by this M1 form.
"""
from django import forms
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from .models import ProductionJob


class ManualTitleForm(forms.Form):
    title = forms.CharField(min_length=4, max_length=180, strip=True)
    revision = forms.CharField(max_length=80)

    def clean_title(self):
        value = " ".join(self.cleaned_data["title"].split())
        if (
            len(value) < 4 or len(value) > 180
            or not value.isprintable()
            or "<" in value or ">" in value
        ):
            raise forms.ValidationError("Enter a plain-text title (4–180 characters).")
        return value


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def edit_manual_title(request, job_id):
    job = get_object_or_404(
        ProductionJob, pk=job_id, owner=request.user,
        kind=ProductionJob.Kind.PROTOTYPE,
        status__in=(ProductionJob.Status.DRAFT, ProductionJob.Status.QUEUED),
    )
    if request.method == "POST":
        form = ManualTitleForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                current = get_object_or_404(
                    ProductionJob.objects.select_for_update(),
                    pk=job_id, owner=request.user,
                    kind=ProductionJob.Kind.PROTOTYPE,
                    status__in=(ProductionJob.Status.DRAFT, ProductionJob.Status.QUEUED),
                )
                if form.cleaned_data["revision"] != current.updated_at.isoformat():
                    return HttpResponse(
                        "The title was changed elsewhere. Reload before saving.",
                        status=409, content_type="text/plain",
                    )
                if form.cleaned_data["title"] != current.title:
                    current.title = form.cleaned_data["title"]
                    current.full_clean()
                    current.save(update_fields=["title", "updated_at"])
            return redirect("home")
    else:
        form = ManualTitleForm(initial={
            "title": job.title, "revision": job.updated_at.isoformat(),
        })
    return render(request, "studio/manual_title.html", {
        "job": job, "form": form,
    })
