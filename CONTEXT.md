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
Eine feste, ohne KI ausführbare Vorschrift, wie ein bestimmter **Eingang** eingeordnet wird (z. B. „Absender ionos → Thema EDV“). Sie gilt immer (**Konfidenz** 1,0). Harald legt **Regeln** an einer konkreten Mail an, nicht vorab.
_Avoid_: Route, Filter, Automatismus

**Konfidenz**:
Wie sicher eine Einordnung ist, von 0 bis 1. Ab der **Schwelle** (Standard 0,8) wird ohne Rückfrage abgelegt, darunter landet der **Eingang** mit **Vorschlag** bei Harald.
_Avoid_: Score, Wahrscheinlichkeit

**Vorschlag**:
Thema, Unterordner und Personen, die das System für einen **Eingang** unterhalb der **Schwelle** annimmt, mit **Konfidenz** und Begründung. Harald übernimmt, ändert oder verwirft ihn; seine Entscheidung wird zur **Notiz**, aus der die **Heuristik** lernt.
_Avoid_: Empfehlung, Prognose

**Heuristik**:
Einordnen ohne **Regel** und ohne KI, aus vorhandenen **Notizen** (gleicher Absender, gleiche Domain), dem **Ablagewissen** und Stichwörtern der Themen.
_Avoid_: Machine Learning, Klassifikator

**Ablagewissen**:
Bekannte Gegenparteien aus der Drive-Ablage und früheren Steuererklärungen (z. B. „HUK, Hausrat → Versicherungen/01HUK_Hausrat“). Liefert **Vorschläge**, legt aber allein nichts ab.
_Avoid_: Stammdaten, Mapping

**Spam-Wert**:
Wie sehr eine Mail nach Werbung oder Spam aussieht, von 0 bis 1, aus Merkmalen im Mail-Kopf (Abmeldelink, Massenversand, Spam-Markierung des Anbieters, Gmail-Kategorie) und Betreff. Ab der Spam-Schwelle wird verworfen; die Mail bleibt als **Indexeintrag** mit Grund auffindbar.
_Avoid_: Spam-Score, Junk

**Umbau**:
Eine strukturelle Änderung über viele **Notizen** hinweg (Themen zusammenlegen, archivieren, Duplikate auflösen); braucht Haralds Freigabe.
_Avoid_: Refactoring, Aufräumen

**Änderungsprotokoll**:
Die nachvollziehbare Liste aller Änderungen, die die KI beim **Einordnen** oder bei einem **Umbau** vorgenommen hat.
_Avoid_: Log

**Zugangsdaten**:
Was ein **Adapter** braucht, um seine **Quelle** zu erreichen (Adresse, Passwort, API-Schlüssel). Sie liegen als GitHub-Secret und sind danach nicht mehr lesbar; die einzige lesbare Kopie hat Haralds Google Passwortmanager, und zwar nur einmal (ein GMX-Passwort, das Chrome schon unter gmx.net kennt, wird nicht zusätzlich unter der Web-App gespeichert).
_Avoid_: Credentials, Login, Secret (für den Wert selbst)

## Relationships

- Ein **Adapter** bedient genau eine **Quelle**; eine **Quelle** hat höchstens einen **Adapter**.
- Ein **Adapter** erzeugt **Eingänge**; **Einordnen** macht aus einem **Eingang** genau eine **Notiz**.
- Eine **Notiz** hat null oder ein **Original**.
- Eine **Notiz** gehört mindestens einer **Person**.
- **Einordnen** läuft in Stufen: **Regel**, **Spam-Wert**, **Heuristik**, optional KI. Die erste Stufe mit genügend **Konfidenz** entscheidet; sonst entsteht ein **Vorschlag**.
- Jedes **Einordnen** und jeder **Umbau** erzeugt Einträge im **Änderungsprotokoll**.

## Flagged ambiguities

- „Dokument“ wurde sowohl für PDFs als auch für Notizen benutzt. Geklärt: die Datei heißt **Original**, die Markdown-Fassung heißt **Notiz**.
