# Second Brain

Persönlicher Wissensspeicher von Harald, der aus mehreren Quellen befüllt wird und sich mit KI-Hilfe selbst organisiert.

## Language

**Quelle**:
Ein externer Ort, aus dem Inhalte ins Second Brain kommen (z. B. ein Mail-Postfach, ein Bankkonto, ein Ordner mit PDFs, das Web).
_Avoid_: Kanal, Feed

**Adapter**:
Das Bindeglied zu genau einer **Quelle**, das deren Inhalte abholt und als **Eingang** ablegt.
_Avoid_: Plugin, Connector, Importer

**Person**:
Ein Haushaltsmitglied (Harald, Samantha, Uschi), dem eine **Notiz** zugeordnet ist; gemeinsame Inhalte (z. B. Gemeinschaftskonto) gehören mehreren **Personen**.
_Avoid_: Nutzer, Steuerfall, Owner

**Eingang**:
Ein neu hereingekommener, noch nicht eingeordneter Inhalt.
_Avoid_: Inbox-Item, Rohdaten

**Original**:
Die unveränderte Datei aus einer **Quelle** (z. B. das PDF, die Mail), die neben ihrer **Notiz** aufbewahrt wird.
_Avoid_: Anhang, Rohdatei

**Notiz**:
Die Markdown-Darstellung eines Inhalts im Second Brain, mit Zusammenfassung, Metadaten und Verknüpfungen; verweist ggf. auf ihr **Original**.
_Avoid_: Seite, Eintrag, Dokument

**Umsatz**:
Eine einzelne Kontobewegung aus einer Bank-**Quelle**; wird keine **Notiz**, kann aber mit der **Notiz** ihres Belegs verknüpft werden.
_Avoid_: Buchung, Transaktion

**Indexeintrag**:
Eine nur auffindbar gehaltene Mail (Absender, Betreff, Datum, Kurzinhalt), die keine **Notiz** wird.
_Avoid_: Metadaten-Eintrag

**Einordnen**:
Das automatische Ablegen, Verschlagworten, Verknüpfen und Zusammenfassen eines **Eingangs** durch die KI, das zu einer **Notiz** führt.
_Avoid_: Verarbeiten, Taggen

**Regel**:
Eine feste, ohne KI ausführbare Vorschrift, wie ein bestimmter **Eingang** eingeordnet wird (z. B. „Absender ionos → Thema EDV“). Die KI schlägt neue **Regeln** vor, wenn sie wiederholt Gleiches einordnet.
_Avoid_: Route, Filter, Automatismus

**Umbau**:
Eine strukturelle Änderung über viele **Notizen** hinweg (Themen zusammenlegen, archivieren, Duplikate auflösen); braucht Haralds Freigabe.
_Avoid_: Refactoring, Aufräumen

**Änderungsprotokoll**:
Die nachvollziehbare Liste aller Änderungen, die die KI beim **Einordnen** oder bei einem **Umbau** vorgenommen hat.
_Avoid_: Log

## Relationships

- Ein **Adapter** bedient genau eine **Quelle**; eine **Quelle** hat höchstens einen **Adapter**.
- Ein **Adapter** erzeugt **Eingänge**; **Einordnen** macht aus einem **Eingang** genau eine **Notiz**.
- Eine **Notiz** hat null oder ein **Original**.
- Eine **Notiz** gehört mindestens einer **Person**.
- **Einordnen** versucht zuerst eine **Regel**; nur wenn keine passt, ordnet die KI ein.
- Jedes **Einordnen** und jeder **Umbau** erzeugt Einträge im **Änderungsprotokoll**.

## Flagged ambiguities

- „Dokument“ wurde sowohl für PDFs als auch für Notizen benutzt. Geklärt: die Datei heißt **Original**, die Markdown-Fassung heißt **Notiz**.
