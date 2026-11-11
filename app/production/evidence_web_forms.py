"""Owner-scoped browser form for deliberate, source-specific evidence reviews.

Not a fact verification form. Source and fact must already belong to the
selected current dossier; no URL field or automatic network access exists.
"""
from django import forms

from .fact_proposals import _short_text
from .models import SourceConfirmation, SourceReference


class _EvidenceSourceChoice(forms.ModelChoiceField):
    def label_from_instance(self, source):
        try:
            manual = source.manual_confirmation
        except SourceConfirmation.DoesNotExist:
            manual = None
        date = manual.checked_at if manual is not None else source.retrieved_at
        provenance = "manuell geprüft" if manual is not None else "importiert"
        return (
            f"Quelle #{source.pk} · {source.title or source.url} "
            f"({provenance}, {date:%Y-%m-%d %H:%M} UTC)"
        )


class EvidenceReviewForm(forms.Form):
    expected_version = forms.IntegerField(
        min_value=1, max_value=999_999_999, widget=forms.HiddenInput,
    )
    source = _EvidenceSourceChoice(
        queryset=SourceReference.objects.none(),
        label="Bereits gespeicherte und erreichbare Quelle",
        empty_label="Bitte Quelle auswählen",
    )
    role = forms.ChoiceField(
        choices=(
            ("supports", "Stützender Beleg"),
            ("contradicts", "Widersprechender Beleg"),
            ("context_only", "Nur Hintergrund / Kontext"),
        ),
        label="Bewertung der konkreten Fundstelle",
    )
    locator = forms.CharField(
        min_length=3, max_length=180, label="Konkrete Fundstelle",
        help_text="Zum Beispiel: Geschichte → Gründung oder Saison 2025/26 → Abschlusstabelle.",
    )
    summary = forms.CharField(
        min_length=15, max_length=350,
        label="Eigene knappe Zusammenfassung dieser Fundstelle",
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Den Inhalt in eigenen Worten zusammenfassen, keine ganzen Artikel kopieren.",
    )
    source_checked = forms.BooleanField(
        required=True,
        label=(
            "Ich habe die ausgewählte Quelle und genau diese Fundstelle selbst "
            "gelesen und mit der Aussage verglichen. Die Rolle ist keine "
            "endgültige Freigabe des Fakts."
        ),
    )

    def __init__(self, *args, sources, initial_version=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["source"].queryset = sources
        if initial_version is not None and not self.is_bound:
            self.initial["expected_version"] = initial_version

    def clean_locator(self):
        try:
            return _short_text(
                self.cleaned_data["locator"], "evidence locator",
                min_length=3, max_length=180,
            )
        except ValueError as exc:
            raise forms.ValidationError(str(exc)) from None

    def clean_summary(self):
        try:
            return _short_text(
                self.cleaned_data["summary"], "evidence summary",
                min_length=15, max_length=350,
            )
        except ValueError as exc:
            raise forms.ValidationError(str(exc)) from None
