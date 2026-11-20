# md2pdf — Markdown zu PDF (A4)

Kleines Node-Skript, das Markdown offline in ein A4-PDF wandelt — ohne pandoc,
LibreOffice oder Chromium. Es bettet Lato (Regular/Bold) und IBM Plex Mono als
TrueType ein, der Text bleibt im PDF selektierbar. Entstanden für die
§14a-Dokumente (Anschlusspläne), funktioniert aber für beliebige Markdown-Dateien.

## Voraussetzungen

- Node.js ≥ 18 (getestet mit Node 24)
- Nur für Schaltbild-Seiten (`--svg`): `@resvg/resvg-js` — im Ordner
  `tools/md2pdf` bereitstellen (`package.json` liegt bei), sonst bricht nur der
  SVG-Pfad ab, reine Text-PDFs laufen ohne diese Abhängigkeit.

## Benutzung

```bash
node tools/md2pdf/md2pdf.mjs <eingabe.md> <ausgabe.pdf> [Optionen]
```

| Option | Bedeutung |
| --- | --- |
| `--svg <datei.svg>` | Schaltbild, das an der Marke `<!-- GRAFIK -->` als Querseite eingefügt wird |
| `--footer "text"` | Fußzeile links (Standard: `Weitergabefassung`) |
| `--author "Name"` | Autor in den PDF-Metadaten; ohne Angabe bleibt das Feld leer |
| `--head-right "text"` | Kopfzeile rechts, z. B. `v3.4 · Stand 2026-11-20` |

## Unterstütztes Markdown

Überschriften (`#` bis `####`), Absätze, Listen (auch verschachtelt und
nummeriert), Tabellen, Zitate, Codeblöcke, Trennlinien sowie inline `**fett**`,
`*kursiv*`, `` `code` `` und `[Link](ziel)`. Ein YAML-Kopf (`---`) wird
übersprungen.

### Marken

| Marke | Wirkung |
| --- | --- |
| `<!-- GRAFIK -->` | fügt die mit `--svg` übergebene Grafik als Querseite ein |
| `<!-- LAYOUT -->` | erzeugt eine Schrankansicht aus der Tabelle unter „1. Betriebsmittel“ |
| `<!-- WIRING -->` | erzeugt eine Aderliste aus der Tabelle unter „5. Aderliste“ |

Die Marken `LAYOUT` und `WIRING` sind auf die Gliederung der §14a-Dokumente
zugeschnitten; ohne passende Überschriften passiert nichts.

## §14a-PDFs reproduzieren

Die §14a-Unterlagen selbst liegen **nicht** in diesem Repo (personenbezogene
Daten, siehe `docs/adr/0001-code-und-daten-getrennt.md`), sondern im privaten
Daten-Repo. Der Ablauf:

1. Markdown-Quelle und Schaltbild (SVG) aus dem Daten-Repo nehmen.
2. PDF erzeugen:

```bash
node tools/md2pdf/md2pdf.mjs anschlussplan.md anschlussplan.pdf \
  --svg schaltbild.svg \
  --head-right "v3.4 · Stand 2026-11-20" \
  --footer "Weitergabefassung"
```

3. Ergebnis prüfen: Das Skript meldet Seitenzahl und Dateigröße; bei zu breiten
   Zeilen zusätzlich `OVERFLOW` mit Position und Textanfang.

Der Autor wird bewusst nicht fest vorgegeben — die PDF-Metadaten bleiben so
PII-frei, solange `--author` nicht gesetzt wird.

## Schriften und Lizenzen

- `fonts/Lato-Regular.ttf`, `fonts/Lato-Bold.ttf` — Lato, SIL Open Font License 1.1
- `fonts/IBMPlexMono-Regular.ttf` — IBM Plex Mono, SIL Open Font License 1.1
- Lizenztexte: `fonts/Lato-OFL.txt`, `fonts/IBMPlexMono-OFL.txt`
