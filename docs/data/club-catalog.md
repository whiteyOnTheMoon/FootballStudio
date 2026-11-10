# Vereinsdatenmodell und aktueller Offline-Katalog

**Die frühere live abgefragte DE/GB-Auswahl ist durch den [Offline-Weltkatalog](offline-world-catalog.md) ersetzt.**

Der aktuelle Nutzerfluss ist **Konföderation → Nationalverband/Land → Liga → Verein**, nicht mehr Land → Liga → Verein. Die 55 UEFA-Verbände und viele weitere Länder sind als lokale Referenzdaten im Repository enthalten. Einzelne Vereinslisten liegen als versionierte OpenFootball-Datenpakete vor. Alle anderen Ligaeinträge werden als **ohne belegte Clubdaten** angezeigt.

**Es erfolgen keine regelmäßigen Anbieter-API-Aufrufe bei der Auswahl.** Der Import erfolgt bewusst über `python manage.py seed_world_catalog` aus lokalen JSON-Dateien.

Die Datenbankmodelle sind `Confederation`, `Country` (mit Verbandskennungen, darunter `GB`, `SCO`, `WAL`, `NIR`), `League` (Tier, Abdeckungsstatus, Quelle und Saison) sowie `Club` (Name, Herkunft, manuell/Provider) und `ProductionJob`. Alle Referenzen sind per Fremdschlüssel abgesichert.

Die **realistische Vollständigkeit** der weltweiten Clublisten ist weiterhin offen. Details, Quellen, Lizenzen, UEFA-Ausnahmen und Abnahmekriterien stehen in der [aktuellen Dokumentation](offline-world-catalog.md).
