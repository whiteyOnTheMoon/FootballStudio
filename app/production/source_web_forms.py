"""Strict HTML fields for a manually inspected official club/league source."""
from django import forms

from .fact_proposals import _short_text
from .manual_source_import import validate_manual_source_url


class ManualOfficialSourceForm(forms.Form):
    expected_version = forms.IntegerField(
        min_value=0, max_value=999_999_999, widget=forms.HiddenInput,
    )
    context = forms.ChoiceField(
        choices=(
            ("club", "Offizielle Website des ausgewählten Vereins"),
            ("league", "Offizielle Website der ausgewählten Liga"),
        ),
        label="Wozu gehört die Quelle?",
    )
    url = forms.CharField(
        max_length=750, label="Selbst geprüfte HTTPS-Seite",
        widget=forms.URLInput(attrs={
            "placeholder": "https://verein.example.org/geschichte",
            "autocomplete": "url",
            "inputmode": "url",
        }),
    )
    title = forms.CharField(
        min_length=4, max_length=160, label="Kurzer Seitentitel",
    )
    basis = forms.CharField(
        min_length=20, max_length=300, label="Warum ist dies die offizielle Quelle?",
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text=(
            "Eigene kurze Begründung der Vereins-/Liga-Zuordnung und "
            "der Prüfung der Quelle, keine kopierten Artikeltexte."
        ),
    )
    identity_confirmed = forms.BooleanField(
        required=True,
        label=(
            "Ich habe selbst geprüft, dass diese Website wirklich zum oben "
            "ausgewählten Verein beziehungsweise zur Liga gehört."
        ),
    )
    terms_confirmed = forms.BooleanField(
        required=True,
        label=(
            "Ich habe die Website-Bedingungen geprüft und die hier "
            "vorgesehene manuelle Quellenreferenz ist danach zulässig. "
            "Das ist keine Freigabe fremder Inhalte zur Veröffentlichung."
        ),
    )
    access_confirmed = forms.BooleanField(
        required=True,
        label=(
            "Ich habe diese konkrete Seite selbst im Browser geöffnet und "
            "konnte sie lesen. FootballStudio ruft sie nicht automatisch ab."
        ),
    )

    def __init__(self, *args, initial_version=None, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound and initial_version is not None:
            self.initial["expected_version"] = initial_version

    def clean_url(self):
        try:
            canonical, _domain = validate_manual_source_url(
                self.cleaned_data["url"]
            )
            return canonical
        except ValueError as exc:
            raise forms.ValidationError(str(exc)) from None

    def clean_title(self):
        try:
            return _short_text(
                self.cleaned_data["title"], "source title",
                min_length=4, max_length=160,
            )
        except ValueError as exc:
            raise forms.ValidationError(str(exc)) from None

    def clean_basis(self):
        try:
            return _short_text(
                self.cleaned_data["basis"], "confirmation basis",
                min_length=20, max_length=300,
            )
        except ValueError as exc:
            raise forms.ValidationError(str(exc)) from None
