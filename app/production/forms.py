"""Validation of the M1 test job: club, title, and selected hierarchy."""
from django import forms

class TestJobForm(forms.Form):
    country = forms.CharField(min_length=2, max_length=3)
    league = forms.IntegerField(min_value=1)
    club = forms.IntegerField(min_value=1)
    title = forms.CharField(min_length=4, max_length=180, strip=True)

    def clean_title(self):
        title = " ".join(self.cleaned_data["title"].split())
        if len(title) < 4:
            raise forms.ValidationError("Please enter a meaningful title.")
        return title
