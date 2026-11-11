"""Bounded, source-scoped HTML input for a *manual, unverified* football fact.

There is deliberately no URL field, no background crawl, no automatic
evidence role promotion and no output to a film/script from this form.
"""
from django import forms

from .fact_proposals import _value
from .models import SourceReference


PREDICATES = (
    ("founded_year", "Gründungsjahr"),
    ("stadium_name", "Stadionname"),
    ("competition_win", "Wettbewerbserfolg (Wettbewerb und Saison)"),
    ("league_membership", "Ligazugehörigkeit (Liga und Saison)"),
    ("standings_position", "Tabellenplatz (Wettbewerb, Saison, Rang)"),
)
_FIELD_SETS = {
    "founded_year": ("founded_year",),
    "stadium_name": ("stadium_name",),
    "competition_win": ("competition", "season"),
    "league_membership": ("league_name", "season"),
    "standings_position": ("competition", "season", "position"),
}
_ALL_VALUE_FIELDS = frozenset({
    name for names in _FIELD_SETS.values() for name in names
})


class _SourceChoice(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        kind = (
            "Verein" if obj.source_kind == SourceReference.Kind.CLUB_OFFICIAL
            else "Liga"
        )
        return (
            f"{kind} · {obj.title or obj.url} · "
            f"abgerufen {obj.retrieved_at:%Y-%m-%d %H:%M} UTC "
            f"(Quelle #{obj.pk})"
        )


class ManualFactProposalForm(forms.Form):
    expected_version = forms.IntegerField(
        min_value=1, widget=forms.HiddenInput,
    )
    source = _SourceChoice(
        queryset=SourceReference.objects.none(),
        label="Bereits erfasste offizielle Quelle",
        empty_label="Bitte Quelle auswählen",
    )
    predicate = forms.ChoiceField(
        choices=PREDICATES, label="Art der Aussage",
    )
    founded_year = forms.IntegerField(
        required=False, label="Gründungsjahr", min_value=1800,
    )
    stadium_name = forms.CharField(
        required=False, max_length=160, label="Stadionname",
    )
    competition = forms.CharField(
        required=False, max_length=160, label="Wettbewerb",
    )
    league_name = forms.CharField(
        required=False, max_length=160, label="Liga",
    )
    season = forms.CharField(
        required=False, max_length=7, label="Saison (z. B. 2025/26)",
    )
    position = forms.IntegerField(
        required=False, min_value=1, max_value=30,
        label="Tabellenplatz",
    )
    assertion_text = forms.CharField(
        min_length=10, max_length=350, label="Konkrete Aussage",
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Selbst formulierter kurzer Satz. Keine langen Fremdtexte kopieren.",
    )
    locator = forms.CharField(
        min_length=3, max_length=180, label="Genaue Fundstelle",
        help_text="Zum Beispiel: Geschichte → Gründung, oder 2025/26 → Abschlusstabelle.",
    )
    evidence_summary = forms.CharField(
        min_length=10, max_length=350, label="Eigene kurze Belegzusammenfassung",
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    source_read_confirmed = forms.BooleanField(
        label=(
            "Ich habe die konkrete Quelle und Fundstelle selbst gelesen. "
            "Dieser Vorschlag ist noch nicht verifiziert."
        ),
        required=True,
    )

    def __init__(self, *args, sources, initial_version=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["source"].queryset = sources
        if initial_version is not None and not self.is_bound:
            self.initial["expected_version"] = initial_version

    def clean(self):
        data = super().clean()
        predicate = data.get("predicate")
        required_fields = _FIELD_SETS.get(predicate)
        if required_fields is None:
            return data

        for field in required_fields:
            if data.get(field) in (None, ""):
                self.add_error(field, "Für diese Faktenart erforderlich.")

        for field in _ALL_VALUE_FIELDS.difference(required_fields):
            if data.get(field) not in (None, ""):
                self.add_error(field, "Dieses Feld gehört nicht zur ausgewählten Faktenart.")

        if self.errors:
            return data

        if predicate == "founded_year":
            value = data["founded_year"]
        elif predicate == "stadium_name":
            value = data["stadium_name"]
        elif predicate == "competition_win":
            value = {"competition": data["competition"], "season": data["season"]}
        elif predicate == "league_membership":
            value = {"league": data["league_name"], "season": data["season"]}
        else:
            value = {
                "competition": data["competition"],
                "season": data["season"], "position": data["position"],
            }

        try:
            data["fact_value"] = _value(predicate, value)
        except ValueError as exc:
            raise forms.ValidationError(str(exc)) from None
        return data
