"""Validation of the M1 test job: club, title, and selected hierarchy."""
from django import forms

from app.clubs.catalog import CATALOG


class TestJobForm(forms.Form):
    country = forms.ChoiceField(
        choices=[(code, descriptor["name"]) for code, descriptor in CATALOG.items()]
    )
    league = forms.IntegerField(min_value=1)
    club = forms.IntegerField(min_value=1)
    title = forms.CharField(min_length=4, max_length=180, strip=True)

    def clean_title(self):
        title = " ".join(self.cleaned_data["title"].split())
        if len(title) < 4:
            raise forms.ValidationError("Please enter a meaningful title.")
        return title
