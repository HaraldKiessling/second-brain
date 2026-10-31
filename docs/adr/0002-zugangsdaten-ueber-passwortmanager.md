# Zugangsdaten über den Google Passwortmanager eingeben

Die Web-App fragt Zugangsdaten in echten Formularen ab, eines pro Konto, mit Nutzername und Passwort. So kann der Google Passwortmanager in Chrome sie auf Rechner und Handy ausfüllen und neue Werte speichern. GitHub-Secrets sind nach dem Setzen nicht mehr lesbar, deshalb ist der Passwortmanager die einzige lesbare Kopie. Jedes Passwort soll dort nur einmal liegen. Das ist gegeben, weil die Web-App nur eigene App-Passwörter und Schlüssel verlangt (GMX und Gmail lassen den IMAP-Abruf mit Zwei-Faktor-Anmeldung ohnehin nur mit App-Passwort zu), nie das normale Konto-Passwort. Konten ohne Nutzernamen bekommen einen festen (Token: Repo-Name, OpenRouter: „OpenRouter“), damit der Eintrag erkennbar ist.

## Considered Options

- Bitwarden: verworfen, Harald nutzt für den Alltag den Google Passwortmanager.
- Einträge von gmx.net automatisch auf der Web-App anbieten: nicht möglich, Chrome gibt Passwörter fremder Seiten nicht heraus und erlaubt keine eigene Seitenverknüpfung für fremde Domains.
- Das normale GMX-Passwort über „Andere Passwörter“ übernehmen und nicht speichern lassen (erste Fassung): verworfen, GMX lehnte es beim Abruf ab („authentication failed“), und die Wahl App- oder Konto-Passwort war verwirrend.

## Consequences

- Ob Chrome Speichern anbietet, steuert die Web-App nur indirekt: Sie blendet das Formular nach erfolgreichem Speichern aus. Das ist Chrome-Verhalten und kann sich ändern.
- Secrets mit Konto-Formular erscheinen nicht noch einmal in der Tabelle; ihr Stand steht im Formular.
