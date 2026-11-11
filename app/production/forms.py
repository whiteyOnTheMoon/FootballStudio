"""Validation for an M1 test job and optional user-entered market-value research."""
from decimal import Decimal

from django import forms
from django.utils import timezone

from .market_values import _source_url


class TestJobForm(forms.Form):
    country = forms.CharField(min_length=2, max_length=3)
    league = forms.IntegerField(min_value=1)
    club = forms.IntegerField(min_value=1)
    title = forms.CharField(min_length=4, max_length=180, strip=True)
    # Numeric input means millions (e.g. 125.50 = 125,500,000 EUR).
    market_value_millions = forms.DecimalField(
        max_digits=8, decimal_places=2, min_value=Decimal("0.01"), required=False,
    )
    market_value_currency = forms.ChoiceField(
        choices=(("EUR", "EUR"), ("GBP", "GBP"), ("USD", "USD")), required=False,
    )
    market_value_as_of = forms.DateField(required=False)
    market_value_source_url = forms.URLField(required=False, max_length=500)

    def clean_title(self):
        title = " ".join(self.cleaned_data["title"].split())
        if len(title) < 4:
            raise forms.ValidationError("Please enter a meaningful title.")
        return title

    def clean_market_value_source_url(self):
        url = self.cleaned_data["market_value_source_url"]
        if not url:
            return ""
        try:
            return _source_url(url)
        except ValueError as exc:
            raise forms.ValidationError(str(exc)) from None

    def clean(self):
        fields = super().clean()
        amount = fields.get("market_value_millions")
        source = fields.get("market_value_source_url")
        as_of = fields.get("market_value_as_of")
        if amount is None:
            if source or as_of:
                raise forms.ValidationError(
                    "Enter a market value when providing its source or date."
                )
        else:
            if as_of and as_of > timezone.localdate():
                self.add_error("market_value_as_of", "The date cannot be in the future.")
        return fields
