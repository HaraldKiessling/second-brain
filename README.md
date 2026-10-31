# second-brain

Code für ein selbstorganisierendes Second Brain: Adapter holen Inhalte aus Quellen (Mail, Banken, Drive, Web), feste Regeln ordnen sie ohne KI ein, und nur Unbekanntes geht an eine KI. Ergebnis sind Markdown-Notizen, die sich mit Obsidian und einer Web-App nutzen lassen.

Dieses Repo enthält **nur Code** und keine persönlichen Daten, Einstellungen oder Secrets. Alle Daten liegen in einem separaten, privaten Daten-Repo; die Abläufe laufen dort (siehe `docs/adr/0001-code-und-daten-getrennt.md`).

## Aufbau

| Pfad | Inhalt |
| --- | --- |
| `CONTEXT.md` | Glossar: Quelle, Adapter, Eingang, Notiz, Regel, … |
| `docs/notiz-format.md` | Format einer Notiz und der Regeln |
| `src/second_brain/` | Notiz-Format, Regel-Engine, Prüfung, Kommandozeile |
| `.github/workflows/mail-abruf.yml` | wiederverwendbarer Ablauf: Mails abholen |
| `web/` | Web-App: Eingang (Vorschläge bestätigen, Regel aus Mail, Spam), Mails (wo liegt welche Mail, Ablage ändern, Mail als PDF nach Drive), Zugangsdaten (als GitHub-Secrets, ausfüllbar mit dem Google Passwortmanager), Regeln, Einstellungen, Abläufe; läuft auf GitHub Pages |
| `beispiel-daten/` | Minimales Daten-Repo als Vorlage und für Tests |

Vorhanden: Mail-Adapter (IMAP, z. B. GMX und Gmail) mit Einordnen in Stufen (Regel, Spam-Wert, Heuristik, optional KI über OpenRouter), Ablage der Anhänge in die Google-Drive-Ordner (über ein Apps-Script im Agentenkonto, `drive-bruecke/`) und Web-App. Geplant: Adapter für Banken, Drive und Web, Drive-Sicherung.

## Benutzung

```bash
pip install -e '.[test]'
pytest
second-brain pruefen beispiel-daten
second-brain einordnen beispiel-daten "billing@hoster-beispiel.de" "Ihre Rechnung" --anhang rechnung.pdf
second-brain mail-abruf beispiel-daten --konto test --eml ordner-mit-eml-dateien
MAIL_USER=… MAIL_PASSWORD=… second-brain mail-abruf <daten-repo> --konto gmx --host imap.gmx.net
```

## Lizenz

AGPL-3.0, siehe `LICENSE`.
