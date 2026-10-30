# Code und Daten in getrennten Repos, Abläufe laufen im Daten-Repo

Das Second Brain hat zwei Repos: `second-brain` enthält nur Code und soll später veröffentlicht werden können, `second-brain-data` ist privat und enthält alle Notizen, Regeln, Einstellungen und Protokolle. Die GitHub-Actions-Workflows laufen im Daten-Repo und holen den Code aus dem Code-Repo, damit Logs und Fehlermeldungen mit persönlichen Daten nie in einem öffentlichen Repo landen. steuer-automation wird nicht umgebaut, weil seine Historie Belege und Secrets enthält; brauchbarer Code wird ohne Historie übernommen.

## Considered Options

- steuer-automation zum Code-Repo umbauen: verworfen, Historie nicht veröffentlichbar.
- Ein einziges privates Repo: verworfen, Code wäre nie teilbar.

## Consequences

- Regeln (z. B. Absender → Thema) gelten als persönliche Daten und liegen im Daten-Repo, nicht beim Code.
- Das Code-Repo braucht Beispielkonfigurationen statt echter Werte.
