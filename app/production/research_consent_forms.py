"""CSRF-bound explicit consent fields, not a general-purpose fetch form."""
from django import forms


class OneTimeResearchConsentForm(forms.Form):
    expected_version = forms.IntegerField(
        min_value=1, max_value=999_999_999, widget=forms.HiddenInput,
    )
    request_key = forms.UUIDField(widget=forms.HiddenInput)
    domain_rechecked = forms.BooleanField(
        required=True,
        label=(
            "Ich habe die ausgewählte Domain für diesen Verein bzw. diese "
            "Liga erneut kontrolliert und bestätige ihre Zuordnung."
        ),
    )
    terms_rechecked = forms.BooleanField(
        required=True,
        label=(
            "Ich habe die aktuellen Website-Bedingungen erneut selbst geprüft. "
            "Meine Bestätigung ist keine Lizenz zur Übernahme fremder Artikel."
        ),
    )
    one_time_approved = forms.BooleanField(
        required=True,
        label=(
            "Ich erlaube ausdrücklich genau eine zeitlich begrenzte "
            "Recherche dieser Quelle (maximal 1+3 HTML-Seiten). "
            "Die Freigabe wird jetzt nur gespeichert; es erfolgt noch KEIN Abruf."
        ),
    )
