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
| `themen` | ja | Liste von Schlüsseln aus `config/themen.yaml` |
| `ablage` | nein | Pfad des Originals in der Drive-Ablage |
| `original` | nein | Link auf das Original |
| `eingeordnet_durch` | nein | `regel/<name>`, `heuristik/<art>`, `ki/<modell>` oder `manuell` |
| `konfidenz` | nein | Konfidenz der Einordnung, nur wenn kleiner als 1 |
| `absender` | nein | Mail-Adresse des Absenders; daraus lernt die Heuristik |
| `umsaetze` | nein | Verweise auf verknüpfte Umsätze, `<konto>/<datum>/<nr>` |
| `anhaenge`, `drive` | nein | Dateinamen der Anhänge und ihr Ort in Drive (`<ordner-id>:<pfad>`) |
| `mail_drive`, `mail_pdf` | nein | Mail soll als PDF in den Drive-Ordner (Web-App, Regel, gelernt oder KI-Vorschlag); `mail_pdf` ist ihr Ort, sobald sie dort liegt; ohne `mail_drive` kommt ein vorhandenes PDF in den Papierkorb |
| `ohne_anhang` | nein | Mail ohne Dokument, trotzdem abgelegt; daraus lernt das Einordnen, dass dieser Absender wichtig ist |
| `nachholen` | nein | in der Web-App aus dem Index abgelegt; der nächste Abruf holt vollständigen Text und Anhänge (`second-brain nachholen`), sonst `nachholen_fehler` |

Die `ablage` darf mehrstufig sein (`0-2026/31 Harald/ionos/rechnungen`). In Regeln und Vorschlägen werden `{jahr}` und `{monat}` im Unterordner durch das Datum der Mail ersetzt.

Ein **Eingang** unter `eingang/` hat dasselbe Format mit leeren `personen` und `themen`, dazu `offen_grund` und, falls vorhanden, `vorschlag` (`thema`, `unterordner`, `personen`, `konfidenz`, `durch`, `grund`).

Weitere Felder sind erlaubt. `second-brain pruefen <daten-repo>` prüft alle Notizen und Regeln.

## Regeln

Regeln für Mails liegen im Daten-Repo unter `regeln/mail.json`. Ablauf und Muster sind in `src/second_brain/regeln.py` beschrieben; ein vollständiges Beispiel steht in `beispiel-daten/regeln/mail.json`.

## Einordnen in Stufen

`src/second_brain/einordnen.py` entscheidet für jede Mail: Regel, Spam-Wert, Heuristik, optional KI. Notiz oder Eingang wird nur eine Mail mit Dokument-Anhang (Bilder unter 50 KB zählen nicht, das sind Logos); ohne Dokument bleibt es beim Indexeintrag. Ausnahmen: eine Regel mit `"ohne_anhang": true` und Mails von `eigene_adressen` (was du dir selbst schickst). Hat Harald schon eine Mail eines Absenders ohne Anhang abgelegt, gilt das auch für die nächste; sonst fragt die KI (falls aktiv), ob eine Mail ohne Anhang wichtig ist (Buchung, Vertrag, Termin …), und legt sie mit Vorschlag in den Eingang. Die KI bekommt dafür bis zu 30 bisherige Ablagen als Beispiele. Regeln können zusätzlich `"mail_drive": true` haben: dann kommt die Mail selbst als PDF in den Drive-Ordner. Regeln können Absender, Empfänger (An/Cc) und Betreff prüfen; alle angegebenen Muster müssen passen. Einstellbar sind Schwelle, Spam-Schwelle und KI in `config/einordnen.yaml`, das Ablagewissen steht in `config/ablagewissen.yaml` (Beispiele in `beispiel-daten/config/`). Wie eine Mail eingeordnet würde, zeigt:

```
second-brain einordnen <daten-repo> "IONOS <rechnung@ionos.de>" "Ihre Rechnung" --anhang rechnung.pdf
```
