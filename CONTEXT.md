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
Das Ablegen, Verschlagworten und Verknüpfen eines **Eingangs** durch **Regeln**, das zu einer **Notiz** führt; ohne passende Regel macht die KI einen **Vorschlag**.
_Avoid_: Verarbeiten, Taggen

**Bestandteil**:
Ein prüfbarer Teil eines **Eingangs**: Absender, Empfänger (An/Cc), Betreff, Mailtext, Anhangname oder **Anhangtext**. Alles, was eine **Regel** entscheidet, muss aus Bestandteilen ableitbar sein.
_Avoid_: Feld, Attribut

**Anhangtext**:
Der Text der Anhänge eines **Eingangs**, aus dem PDF gelesen oder per Texterkennung (OCR) aus Scans und Fotos gewonnen. Er liegt im Daten-Repo unter `anhangtext/<id>.txt`, damit Regeln und Beispiele ihn später noch prüfen können.
_Avoid_: OCR-Ergebnis, Volltext

**Regel**:
Eine feste, ohne KI ausführbare Vorschrift aus **Wenn** und **Dann**: Wenn alle **Bedingungen** zutreffen, dann gilt, was die Regel festlegt. Es gibt drei Arten: **Ordnerregel** (Ordner und Merkmale), **Merkmalregel** (nur Merkmale wie Person, **Objekt**, **Steuerbezug**) und **Aussortierregel** (Dann: aussortieren). Regeln entstehen aus dem **Bestand** und aus Vorschlägen; Harald übernimmt sie.
_Avoid_: Route, Filter, Automatismus, Vertrag (ein Vertrag ist eine Regel mit Nummer-Bedingung)

**Bedingung**:
Ein Teil des **Wenn** einer **Regel**: welcher **Bestandteil** (oder „überall“), wie verglichen wird und mit welchen Werten. Vergleiche: ganzes Wort (Standard), Wortteil (nur ausdrücklich), Nummer (Trennzeichen egal, „624/220429“ = „624 220429“) und „nicht“. Werte einer Bedingung sind „oder“, mehrere Bedingungen „und“.
_Avoid_: Muster, Kriterium

**Regelkonflikt**:
Zwei **Ordnerregeln** passen auf denselben **Eingang**. Ordnerregeln müssen eindeutig sein; ein Konflikt wird beim Anlegen gegen den **Bestand** geprüft und im laufenden Betrieb nicht entschieden, der Eingang landet mit beiden Regeln bei Harald, und eine Regel wird nachgeschärft. **Merkmalregeln** dürfen zusammen passen, ihre Merkmale addieren sich.
_Avoid_: Kollision, Doppeltreffer

**Wert im Ordner**:
Der Unterordner einer **Ordnerregel** enthält einen Wert aus dem **Eingang**, am besten eine gleichbleibende Nummer (Vertrag, Kunde, Kassenzeichen), sonst den Namen der Gegenpartei, nie eine Rechnungsnummer. Neue Ordner schlägt das System als „Gegenpartei_Nummer“ vor; bestehende Drive-Ordner behalten ihren Namen.
_Avoid_: Ordnerschlüssel

**Bestand**:
Alles bisher Hereingekommene mit seinen **Bestandteilen**: **Notizen**, offene **Eingänge** und **Indexeinträge** (`index/bestand.jsonl`). An ihm werden **Regeln** geprüft (wie viele Mails passen, welche **Regelkonflikte**), und aus ihm und der **Ordnerliste** wurden die Regeln neu aufgebaut.
_Avoid_: Historie, Trainingsdaten

**Vorschlag**:
Ordner und Merkmale, die die KI für einen **Eingang** annimmt, zu dem keine **Regel** passt, mit Begründung. Die KI legt nie selbst ab; Harald übernimmt, ändert oder verwirft, und aus seiner Ablage kann ein **Regelvorschlag** werden.
_Avoid_: Empfehlung, Prognose

**Regelvorschlag**:
Eine **Regel**, die das System vorschlägt, mit Beispielmails aus dem **Bestand** und ihren **Regelkonflikten**: aus dem Neuaufbau (Nummer oder Gegenpartei im Ordnernamen, **Kennungen** der Dokumente im Ordner) oder weil Harald zweimal Gleiches abgelegt hat. Gilt erst, wenn Harald sie übernimmt.

**Kennung**:
Ein Wert, der in jedem Schreiben einer Gegenpartei wiederkehrt und einen Ordner erkennbar macht: Vertrags-, Kunden-, Mitglieds-, Versicherten-, Policennummer, Kassenzeichen, Steuernummer, oder die Domain der Gegenpartei. Gelesen aus den Dokumenten, die schon im Ordner liegen; zählt nur, wenn sie zu diesem Ordner gehört (beschriftet oder mehrfach, nicht in vielen Ordnern). Rechnungs-, Telefon-, Kontonummern, Beträge und Daten sind keine Kennung.
_Avoid_: Merkmal (das ist, was eine Regel setzt)
_Avoid_: Regelentwurf

**Objekt**:
Worauf sich ein Inhalt bezieht, z. B. Kieler Str. 37 oder das Auto. Eine **Notiz** kann mehrere haben; Versicherungen beziehen sich immer auf ein Objekt und ein Risiko.
_Avoid_: Immobilie (zu eng), Asset

**Steuerbezug**:
Für welchen **Steuerposten** ein Inhalt zählt. Unabhängig vom Ablageordner; eine **Notiz** kann mehrere haben. Er kommt fest aus dem Ordner (`ordner` in `config/steuerposten.yaml`), aus **Regeln** oder von Harald.
_Avoid_: Steuerkategorie, Anlage (nur ein Teil davon)

**Steuerposten**:
Eine Angabe der Steuererklärung als Person · Anlage · **Objekt** · Posten, z. B. „Harald · Anlage V · Kieler 37 · Schuldzinsen“ (`harald.v.kieler37.schuldzinsen`), ohne Zeilennummern. Die Liste in `config/steuerposten.yaml` entstand aus den Erklärungen 2024/2025; neue Posten schlägt die KI vor, Harald bestätigt. Jede Person hat eigene Posten; Zusammenveranlagung ist Sache der Steuererklärung, nicht des Sammelns.
_Avoid_: Steuerkategorie, Zeile

**Betrag**:
Der Endbetrag eines Belegs, dazu Zahlungs- oder Fälligkeitsdatum und bei Handwerkern der Lohnanteil (§35a), aus Mailtext und **Anhangtext** gelesen. Die **Steuerübersicht** summiert ihn je **Steuerposten**.
_Avoid_: Summe, Preis

**Steuerübersicht**:
Je Jahr und **Person** die Belege nach Anlage und **Steuerposten** mit Summen, Links und fehlenden Belegen (Posten, die im Vorjahr Belege hatten), als `steuer/<jahr>.json` und CSV für WISO; in der Web-App der Reiter „Steuer“.
_Avoid_: Steuerreport

**Ordnerliste**:
Alle bekannten Unterordner der Drive-Ablage je Thema, auch mehrstufig (z. B. „Finanzen/Karten“). Sie steht in `config/ordner.yaml` im Daten-Repo und wächst mit jedem Ablegen in einen neuen Ordner. Die Web-App zeigt sie als Ordnerauswahl, die für eine Mail wahrscheinlichsten Ordner stehen oben.
_Avoid_: Ordnerbaum (die Brücke kann Drive nicht auflisten, die Liste ist das, was das System kennt)

**Jahresordner**:
Die oberste Ebene der Drive-Ablage, ein Ordner je Jahr (2020 … 2027), darin die Themenordner. Das laufende Jahr heißt in Drive „0-2026“, damit es oben steht; beim Jahreswechsel benennt Harald um. Die Web-App zeigt immer nur die Jahreszahl („2026“), das System merkt sich die Ordner über ihre ID.
_Avoid_: Jahresablage, Archivjahr

**Zugehörigkeitsjahr**:
Das Jahr, in dessen **Jahresordner** ein Inhalt kommt. Mit Geldfluss ist es das Jahr der Zahlung (steuerliche Relevanz; ersatzweise Fälligkeit oder Abbuchungstermin, bis **Umsätze** den echten Tag liefern), ohne Geldfluss das Jahr, das der Inhalt betrifft, sonst das Datum der Mail. Beispiel: Beitragsrechnung vom Dezember 2026, abgebucht am 01.01.2027 → 2027; Abrechnung für 2026 mit Nachzahlung 2027 → 2027. Steht als `jahr` in der **Notiz**, wenn es vom Empfangsjahr abweicht.
_Avoid_: Empfangsjahr (das ist nur der Ersatz), Belegjahr

**Dauerablage**:
Der Ordner „0000-dauerhaft“ für Inhalte, die viele Jahre betreffen (Kauf-, Darlehens-, Miet-, Rentenvertrag, Grundbuch, Versicherungsschein, Förderbescheid). Er hat eigene Unterordner (z. B. „03 Kieler 37“, „Immobilien“). Ein solcher Inhalt liegt in seinem **Jahresordner** und zusätzlich als Kopie in der Dauerablage. Das System schlägt das vor, Harald bestätigt es.
_Avoid_: 0000 (so heißt der Ordner nicht), Archiv

**Spam-Wert**:
Wie sehr eine Mail nach Werbung oder Spam aussieht, von 0 bis 1, aus Merkmalen im Mail-Kopf (Abmeldelink, Massenversand, Spam-Markierung des Anbieters, Gmail-Kategorie) und Betreff. Ab der Spam-Schwelle wird aussortiert; die Mail bleibt als **Indexeintrag** mit Grund auffindbar. Was der Spam-Wert nicht erkennt, sortiert eine **Aussortierregel** aus.
_Avoid_: Spam-Score, Junk

**Umbau**:
Eine strukturelle Änderung über viele **Notizen** hinweg (Themen zusammenlegen, archivieren, Duplikate auflösen); braucht Haralds Freigabe.
_Avoid_: Refactoring, Aufräumen

**Änderungsprotokoll**:
Die nachvollziehbare Liste aller Änderungen, die die KI beim **Einordnen** oder bei einem **Umbau** vorgenommen hat.
_Avoid_: Log

**Zugangsdaten**:
Was ein **Adapter** braucht, um seine **Quelle** zu erreichen (Adresse, Passwort, API-Schlüssel). Sie liegen als GitHub-Secret und sind danach nicht mehr lesbar; die einzige lesbare Kopie hat Haralds Google Passwortmanager. Für Mail-Konten sind es App-Passwörter, nie das normale Konto-Passwort, deshalb liegt nichts doppelt.
_Avoid_: Credentials, Login, Secret (für den Wert selbst)

## Wörter in der Web-App

Die Web-App spricht Alltagssprache; die Begriffe oben gelten in Code und Doku.

| Web-App | Begriff |
| --- | --- |
| Zu erledigen, offen | **Eingang** |
| abgelegt | **Notiz** |
| nur gemerkt | **Indexeintrag** |
| aussortiert | verworfen (**Spam-Wert** oder Aussortierregel) |
| Vorschlag | **Vorschlag** der KI oder **Regelvorschlag** |
| erkannt an | die **Bedingungen** der **Regel**, die gepasst haben |
| passt auch auf | **Regelkonflikt** |
| Steuer | **Steuerübersicht** |
| Ordner in Drive, „2026 › 08Versicherungen › …“ | **Jahresordner**, Themenordner (`ablage` in `config/themen.yaml`) und Unterordner, immer mit den echten Drive-Namen |
| Einrichtung | Regeln, **Ordnerliste**, Personen, **Steuerposten**, **Zugangsdaten**, Abrufe |

## Relationships

- Ein **Adapter** bedient genau eine **Quelle**; eine **Quelle** hat höchstens einen **Adapter**.
- Ein **Adapter** erzeugt **Eingänge**; **Einordnen** macht aus einem **Eingang** genau eine **Notiz**.
- Eine **Notiz** hat null oder ein **Original**.
- Eine **Notiz** gehört mindestens einer **Person**.
- Eine **Notiz** hat ein Hauptthema (bestimmt den einen Drive-Ordner), beliebig viele weitere Themen, **Objekte** und **Steuerbezüge**.
- Der Drive-Ordner einer **Notiz** ist **Jahresordner** (nach **Zugehörigkeitsjahr**) › Themenordner › Unterordner; dazu höchstens eine Kopie in der **Dauerablage**.
- **Einordnen** läuft in Stufen: **Regel** (genau eine **Ordnerregel** passt, dazu alle passenden **Merkmalregeln**), **Spam-Wert**, sonst **Vorschlag** der KI. Passen zwei Ordnerregeln, ist das ein **Regelkonflikt** und kommt zu Harald.
- Eine **Regel** hat eine oder mehrere **Bedingungen** auf **Bestandteilen**; eine **Ordnerregel** zeigt auf einen Unterordner mit **Wert im Ordner**.
- Ein **Steuerbezug** zeigt auf genau einen **Steuerposten**; ein **Steuerposten** gehört genau einer **Person**.
- Jedes **Einordnen** und jeder **Umbau** erzeugt Einträge im **Änderungsprotokoll**.

## Flagged ambiguities

- „Dokument“ wurde sowohl für PDFs als auch für Notizen benutzt. Geklärt: die Datei heißt **Original**, die Markdown-Fassung heißt **Notiz**.
- „Jahr“ einer Mail: Empfangsjahr oder Jahr, zu dem sie gehört? Geklärt (2026-11-01): abgelegt wird nach **Zugehörigkeitsjahr**, bei Geldfluss zählt die Zahlung.
- Regeln: Bis Oktober 2026 entschieden Verwerfen-Liste, Prüfen-Liste, Regeln, Vertragsliste, Ablagewissen und Lernen vom Absender nebeneinander. Geklärt (2026-11-02, ADR 0004): eine Regelart Wenn/Dann aus **Bestandteilen**, eindeutig, aus dem **Bestand** neu aufgebaut.
- Ordnernamen: Die Web-App zeigte Kurznamen („Albert-Einstein 59 / versicherung“), die Harald in Drive nicht wiederfand. Geklärt: überall die echten Drive-Namen mit Nummern und Jahr, mit Link in den Ordner.
