# Zugangsdaten über den Google Passwortmanager eingeben

Die Web-App fragt Zugangsdaten in echten Formularen ab, eines pro Konto, mit Nutzername und Passwort. So kann der Google Passwortmanager in Chrome sie auf Rechner und Handy ausfüllen und neue Werte speichern. GitHub-Secrets sind nach dem Setzen nicht mehr lesbar, deshalb ist der Passwortmanager die einzige lesbare Kopie. Jedes Passwort soll dort nur einmal liegen: Wo Chrome es schon unter einer anderen Seite kennt (GMX unter gmx.net), holt Harald es über „Andere Passwörter“, und die Web-App bietet dafür kein Speichern an. Konten ohne Nutzernamen bekommen einen festen (Token: Repo-Name, OpenRouter: „OpenRouter“), damit der Eintrag erkennbar ist.

## Considered Options

- Bitwarden: verworfen, Harald nutzt für den Alltag den Google Passwortmanager.
- Einträge von gmx.net automatisch auf der Web-App anbieten: nicht möglich, Chrome gibt Passwörter fremder Seiten nicht heraus und erlaubt keine eigene Seitenverknüpfung für fremde Domains.

## Consequences

- Ob Chrome Speichern anbietet, steuert die Web-App nur indirekt: Formular nach erfolgreichem Speichern ausblenden (anbieten) oder Passwortfeld vor dem Abschicken ersetzen (nicht anbieten). Das ist Chrome-Verhalten und kann sich ändern.
