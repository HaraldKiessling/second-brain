# Notiz-Format

Eine **Notiz** (siehe `CONTEXT.md`) ist eine Markdown-Datei unter `notizen/<jahr>/<thema>/` im Daten-Repo. Sie beginnt mit YAML-Frontmatter und hat genau eine Überschrift erster Ebene als Titel.

```markdown
---
id: 2026-10-28-ionos-rechnung-oktober
erstellt: 2026-10-28
quelle: gmx
personen: [harald]
themen: [edv]
ablage: 0-2026/31 Harald/ionos
original: https://drive.google.com/file/d/…
eingeordnet_durch: regel/ionos
umsaetze: [ing-giro/2026-10-30/0042]
---

# IONOS Rechnung Oktober 2026

Monatsrechnung Hosting, 12,00 € brutto.
Verknüpft: [[IONOS]]
```

## Felder

| Feld | Pflicht | Inhalt |
| --- | --- | --- |
| `id` | ja | eindeutig im Daten-Repo; nur `a-z`, `0-9`, `-`; Konvention `<datum>-<absender>-<kurztitel>` |
| `erstellt` | ja | Datum des Inhalts (nicht des Imports), `JJJJ-MM-TT` |
| `quelle` | ja | Name der Quelle, z. B. `gmx`, `gmail`, `drive`, `web`, `manuell` |
| `personen` | ja | Liste von Schlüsseln aus `config/personen.yaml` |
| `themen` | ja | Liste von Schlüsseln aus `config/themen.yaml`; das erste ist das Hauptthema und bestimmt den Drive-Ordner, die weiteren sind Schlagworte |
| `ablage` | nein | Pfad des Originals in der Drive-Ablage |
| `original` | nein | Link auf das Original |
| `eingeordnet_durch` | nein | `regel/<name>`, `ki/<modell>`, `spam` oder `manuell` |
| `regel_treffer` | nein | woran die Regel erkannt hat, z. B. „Anhangtext: Nummer 624/220429“ (Web-App: „erkannt an“) |
| `regelkonflikt` | nein | nur im Eingang: Namen der Ordnerregeln, die zugleich passten (ADR 0004) |
| `objekte` | nein | Liste von Schlüsseln aus `config/bezuege.yaml` (`objekte`), worauf sich der Inhalt bezieht, z. B. `kieler37`, `auto` |
| `steuer` | nein | Liste von **Steuerposten** aus `config/steuerposten.yaml`, z. B. `harald.v.kieler37.schuldzinsen`; fest aus dem Ordner (`ordner`), aus Regeln oder von Harald |
| `betrag`, `zahlung`, `lohnanteil` | nein | Endbetrag in Euro, Zahlungs- oder Fälligkeitsdatum und Lohnanteil (§35a), aus Mailtext und Anhangtext gelesen; Grundlage der Steuerübersicht |
| `absender`, `empfaenger` | nein | Absender und Empfänger (An/Cc) der Mail |
| `umsaetze` | nein | Verweise auf verknüpfte Umsätze, `<konto>/<datum>/<nr>` |
| `anhaenge`, `drive` | nein | Dateinamen der Anhänge und ihr Ort in Drive (`<ordner-id>:<pfad>`) |
| `mail_drive`, `mail_pdf` | nein | Mail soll als PDF in den Drive-Ordner (Web-App, Regel oder KI-Vorschlag); `mail_pdf` ist ihr Ort, sobald sie dort liegt; ohne `mail_drive` kommt ein vorhandenes PDF in den Ordner „Second Brain Papierkorb“ des Agentenkontos. Das PDF druckt Chrome im Ablauf, die Drive-Brücke braucht dafür keine neue Version |
| `ohne_anhang` | nein | Mail ohne Dokument, trotzdem abgelegt |
| `jahr`, `jahr_grund` | nein | **Zugehörigkeitsjahr**, wenn es vom Jahr in `erstellt` abweicht, und woran es erkannt wurde (z. B. „Zahlung am 01.01.2027“); bestimmt den Jahresordner in `ablage` (ADR 0003) |
| `dateien`, `mail_pdf_id` | nein | Drive-IDs der hochgeladenen Anhänge (Name → ID) und des Mail-PDFs, für Links in Web-App und Notiztext |
| `dauerhaft_vorschlag` | nein | Grund, warum der Inhalt vermutlich viele Jahre betrifft (Vorschlag für 0000-dauerhaft) |
| `dauerhaft`, `drive_dauerhaft`, `dauerhaft_nein` | nein | von Harald bestätigt: Unterordner in 0000-dauerhaft für eine Kopie; ihr Ort, sobald sie dort liegt; oder abgelehnt |
| `nachholen` | nein | in der Web-App aus dem Index abgelegt; der nächste Abruf holt vollständigen Text und Anhänge (`second-brain nachholen`), sonst `nachholen_fehler` |

Die `ablage` darf mehrstufig sein (`0-2026/31 Harald/ionos/rechnungen`). Der erste Teil ist der Jahresordner; „0-2026“ und „2026“ meinen denselben Ordner (Jahreswechsel). Nach dem ersten Drive-Abgleich bekommt der Notiztext einen Abschnitt „Ablage in Drive“ mit Links auf Ordner und Dateien (zwischen `<!-- ablage -->` und `<!-- /ablage -->`, wird bei jeder Änderung neu geschrieben). In Regeln und Vorschlägen werden `{jahr}` und `{monat}` im Unterordner durch das Datum der Mail ersetzt.

Ein **Eingang** unter `eingang/` hat dasselbe Format mit leeren `personen` und `themen`, dazu `offen_grund` und, falls vorhanden, `vorschlag` (`thema`, `unterordner`, `personen`, `durch`, `grund`).

Weitere Felder sind erlaubt. `second-brain pruefen <daten-repo>` prüft alle Notizen und Regeln.

## Regeln

Regeln für Mails liegen im Daten-Repo unter `regeln/mail.json` (Version 3, ADR 0004). Jede Regel hat `name`, `art` (`ordner`, `merkmal` oder `aussortieren`), `wenn` und `dann`:

```json
{"version": 3, "standard_personen": ["harald"], "regeln": [
  {"name": "huk-kfz", "art": "ordner",
   "wenn": [{"teil": "ueberall", "vergleich": "nummer", "werte": ["624/220429"]}],
   "dann": {"thema": "versicherungen", "unterordner": "07HUK_Kfz_624_220429-P",
            "steuer": ["harald.vor.uebrige-versicherungen"]}}
]}
```

`teil` ist `absender`, `empfaenger`, `betreff`, `text`, `anhangname`, `anhangtext` oder `ueberall`; `vergleich` ist `wort` (Standard, ganzes Wort, Groß/klein und Umlaute egal), `wortteil`, `nummer` (Trennzeichen egal) oder `nicht`. Werte einer Bedingung sind „oder“, Bedingungen „und“. `dann` kann `thema`, `unterordner`, `personen`, `weitere_themen`, `objekte`, `steuer`, `mail_drive`, `ohne_anhang` und `dauerhaft` setzen, nie das Jahr. Ordnerregeln müssen eindeutig sein; `second-brain konflikte <daten-repo>` prüft sie gegen den Bestand. Regelvorschläge stehen in `regeln/mail-vorschlaege.json` (`second-brain neuaufbau` aus Ordnerliste und Bestand, `second-brain regelvorschlaege` aus der Ablage). Ein vollständiges Beispiel steht in `beispiel-daten/regeln/mail.json`.

## Einordnen in Stufen

`src/second_brain/einordnen.py` entscheidet für jede Mail: erst die Regeln (genau eine Ordnerregel, dazu alle passenden Merkmalregeln; passen zwei Ordnerregeln, kommt die Mail mit beiden in den Eingang), dann der Spam-Wert, sonst ein Vorschlag der KI im Eingang. Die KI legt nie selbst ab. Geprüft werden alle Bestandteile, auch der Text der Anhänge: PDF-Text, bei Scans und Fotos Texterkennung (Tesseract, deutsch); der Text liegt unter `anhangtext/<id>.txt`. Notiz oder Eingang wird nur eine Mail mit Dokument-Anhang (Bilder unter 50 KB zählen nicht, das sind Logos); ohne Dokument bleibt es beim Indexeintrag. Ausnahmen: eine Regel mit `"ohne_anhang": true`, Mails von `eigene_adressen` und Mails, die die KI für wichtig hält (Buchung, Vertrag, Termin …). Den festen Steuerbezug eines Ordners setzt `config/steuerposten.yaml` (`ordner`). Einstellbar sind Spam-Schwelle und KI in `config/einordnen.yaml`. Wie eine Mail eingeordnet würde, zeigt:

```
second-brain einordnen <daten-repo> "IONOS <rechnung@ionos.de>" "Ihre Rechnung" --anhang rechnung.pdf
```

Nur im Eingang bzw. bis zum nächsten Abruf: `vorschlag` (Vorschlag mit `alternativen`, optional `weitere_themen`, `objekte`, `steuer`), `vorschlag_anfordern` (Web-App „Neue Vorschläge“: `true` oder Haralds Hinweis an die KI; der Abruf ersetzt es durch einen neuen `vorschlag`) und `vorschlag_fehler`.
