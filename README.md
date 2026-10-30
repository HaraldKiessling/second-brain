# second-brain

Code für ein selbstorganisierendes Second Brain: Adapter holen Inhalte aus Quellen (Mail, Banken, Drive, Web), feste Regeln ordnen sie ohne KI ein, und nur Unbekanntes geht an eine KI. Ergebnis sind Markdown-Notizen, die sich mit Obsidian und einer Web-App nutzen lassen.

Dieses Repo enthält **nur Code** und keine persönlichen Daten, Einstellungen oder Secrets. Alle Daten liegen in einem separaten, privaten Daten-Repo; die Abläufe laufen dort (siehe `docs/adr/0001-code-und-daten-getrennt.md`).

## Aufbau

| Pfad | Inhalt |
| --- | --- |
| `CONTEXT.md` | Glossar: Quelle, Adapter, Eingang, Notiz, Regel, … |
| `docs/notiz-format.md` | Format einer Notiz und der Regeln |
| `src/second_brain/` | Notiz-Format, Regel-Engine, Prüfung, Kommandozeile |
| `beispiel-daten/` | Minimales Daten-Repo als Vorlage und für Tests |

Geplant: Adapter (GMX, Gmail, Banken, Drive, Web), KI-Einordnen über OpenRouter, Drive-Sicherung, Web-App.

## Benutzung

```bash
pip install -e '.[test]'
pytest
second-brain pruefen beispiel-daten
second-brain regel beispiel-daten "billing@hoster-beispiel.de" "Ihre Rechnung" --anhang
```

## Lizenz

AGPL-3.0, siehe `LICENSE`.
