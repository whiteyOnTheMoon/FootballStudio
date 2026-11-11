"""Explicit, owner-attributed browser decision on a researched fact.

A human review is different from source access and evidence role marking.
Only the existing audited review service can change a fact's status.
"""
from django import forms

from .fact_proposals import _short_text
from .models import Fact


class HumanFactDecisionForm(forms.Form):
    expected_version = forms.IntegerField(
        min_value=1, max_value=999_999_999, widget=forms.HiddenInput,
    )
    decision = forms.ChoiceField(
        label="Nach inhaltlicher Prüfung festgestelltes Ergebnis",
        choices=(
            (Fact.Verification.VERIFIED, "Verifiziert – eindeutig gestützt"),
            (Fact.Verification.CONFLICTED, "Widersprüchlich – ungelöste Gegenbelege"),
            (Fact.Verification.INSUFFICIENT, "Nicht ausreichend belegt"),
            (Fact.Verification.REJECTED, "Verworfen – für das Skript ungeeignet"),
        ),
    )
    review_note = forms.CharField(
        label="Eigene Prüfbegründung (30–500 Zeichen)",
        min_length=30, max_length=500,
        widget=forms.Textarea(attrs={"rows": 4}),
        help_text=(
            "Was belegt die Fundstelle, welche Alternativen oder Widersprüche "
            "wurden geprüft und warum ist die Entscheidung gerechtfertigt?"
        ),
    )
    source_checked = forms.BooleanField(
        required=False,
        label=(
            "Ich habe die konkrete Quelle und ihre Belege selbst gelesen "
            "und mit genau dieser Aussage verglichen."
        ),
    )
    season_checked = forms.BooleanField(
        required=False,
        label=(
            "Ich habe die angegebene Saison/Bezugszeit mit allen "
            "stützenden Belegfundstellen abgeglichen."
        ),
    )
    review_confirmed = forms.BooleanField(
        required=True,
        label=(
            "Ich bestätige meine bewusste, eigene Entscheidung. "
            "Die Software hat diese Aussage nicht automatisch überprüft."
        ),
    )

    def __init__(self, *args, fact, initial_version=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fact = fact
        self.is_seasonal = (
            isinstance(fact.value, dict) and bool(fact.value.get("season"))
        )
        if not self.is_bound and initial_version is not None:
            self.initial["expected_version"] = initial_version

    def clean_review_note(self):
        try:
            return _short_text(
                self.cleaned_data["review_note"], "review rationale",
                min_length=30, max_length=500,
            )
        except ValueError as exc:
            raise forms.ValidationError(str(exc)) from None

    def clean(self):
        fields = super().clean()
        if fields.get("decision") == Fact.Verification.VERIFIED:
            if not fields.get("source_checked"):
                self.add_error(
                    "source_checked",
                    "Eine Verifikation verlangt die persönliche Prüfung der Belege.",
                )
            if self.is_seasonal and not fields.get("season_checked"):
                self.add_error(
                    "season_checked",
                    "Für diesen Fakt muss die konkrete Saison geprüft sein.",
                )
        if fields.get("decision") == Fact.Verification.CONFLICTED and not fields.get(
            "source_checked"
        ):
            self.add_error(
                "source_checked",
                "Widersprechende und stützende Belege müssen geprüft sein.",
            )
        return fields
