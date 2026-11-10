"""Validation of manually entered clubs in an existing, supported league."""
from django import forms

class ManualClubForm(forms.Form):
    country = forms.CharField(min_length=2, max_length=3)
    league = forms.IntegerField(min_value=1)
    name = forms.CharField(min_length=2, max_length=160, strip=True)

    def clean_name(self):
        value = " ".join(self.cleaned_data["name"].split())
        if len(value) < 2 or any(ord(char) < 32 for char in value):
            raise forms.ValidationError("Please enter a valid club name.")
        return value
