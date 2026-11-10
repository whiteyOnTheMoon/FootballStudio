# FS-010a – Vereinsdatenmodell und Katalogregeln

**Stand:** M1-Implementierung, Datenbankmodelle und Migration vorhanden. **Keine externen Vereinsdaten importiert.**

Das Datenmodell bildet **Land (Country) → Liga (League) → Verein (Club)** ab. Alle drei Entitäten sind dynamisch aus PostgreSQL lesbar und im Django Admin bearbeitbar. Der erste nutzbare Prototyp muss später zusätzlich **echte Dropdowns mit API-Datenquelle** (#24) und manuelle Vereinsanlage (#25) anbieten; eine fest verdrahtete Pilot-Club-ID ist ausdrücklich ausgeschlossen.

## Beziehungen und Felder

| Modell | Kernfelder | Beziehungen |
| --- | --- | --- |
| `Country` | ISO-3166-Alpha-2-Code, Name, aktiv | besitzt Ligen |
| `League` | Name, Stufe/Tier, Provider und externe ID, aktiv | gehört zu einem Land, besitzt Vereine |
| `Club` | Name, Provider/Provider-ID, Kennzeichen manuell, aktiv, Änderungszeitpunkte | gehört zu einer Liga |

Die Country-Codes werden als Großbuchstaben gespeichert. Die Namen von Liga und Verein sind innerhalb ihrer Elternbeziehung **case-insensitiv eindeutig**; doppelte Schreibvarianten derselben Liga/desselben Vereins werden per PostgreSQL-/SQLite-Constraint zurückgewiesen. Gleichnamige Ligen in verschiedenen Ländern bzw. Clubs in verschiedenen Ligen sind erlaubt.

Ein manuell angelegter Club hat standardmäßig `provider="manual"` und `is_manual=True`. Spätere Katalogimporte erhalten ihre reale Provider-ID sowie `is_manual=False`. Namen, IDs und Clubzuordnung werden **nicht** mit fiktiven Vereinen vorbefüllt.

## Tests und Migrationsdisziplin

- `python manage.py makemigrations --check --dry-run` muss **keine unversionierten Schemaänderungen** finden.
- `python manage.py migrate --noinput` muss auf einer frischen PostgreSQL-Testdatenbank erfolgreich sein.
- `python manage.py test app.clubs` prüft Beziehungen, zwei Ligen innerhalb eines Landes, andere Länder, manuelle Änderung und Dublettenschutz.
- Die Compose-Integration wird auf GitHub Actions gegen PostgreSQL ausgeführt; SQLite-Tests ergänzen die Unit-Prüfung.
- Bestehende Datenbanken dürfen nicht mit `down -v` oder gelöscht werden, nur um neue Migrationen zu testen.

## Noch offen

Die tatsächliche **Länder-, Ligen- und Vereinsabdeckung** (mindestens die beiden höchsten Ligen je unterstützt ausgewähltem Land; dritte soweit möglich) muss der Adapter mit geeigneter freier Datenquelle in #24 umsetzen und nachweisen. Die folgenden Tickets sorgen dann für manuelle Eingabe (#25), Jobbezug (#23/#26) und die Benutzeroberfläche. Dieses Dokument behauptet **keine** erfolgreiche API-Abfrage.
