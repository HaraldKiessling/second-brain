# Regeln aus Bestandteilen des Eingangs, eindeutig, neu aus dem Bestand

Bis Oktober 2026 entschieden fünf Dinge nebeneinander, wohin eine Mail kommt: Verwerfen-Liste, Prüfen-Liste der Versicherer, Regeln (Wortteil in Absender, Empfänger, Betreff), Vertragsliste und Ablagewissen, dazu das Lernen vom Absender. Das war nicht nachvollziehbar, Wortteile schlugen falsch an („auto“ in „automatisch“, „notar“ in jedem Betreff), und den Inhalt der Anhänge las nichts. Harald (2026-11-02): Ordner und Merkmale müssen aus Bestandteilen der Mail ableitbar sein, auch aus Mailtext und Anhang; die alten Regeln werden gelöscht und aus dem Bestand mit KI neu aufgebaut.

Entscheidung:

- **Eine Regelart** mit **Wenn** (Bedingungen) und **Dann** (Ordner und Merkmale). Verwerfen ist eine Regel mit „Dann: aussortieren“, ein Vertrag eine Regel mit einer Nummer-Bedingung. Prüfen-Liste, Vertragsliste, Ablagewissen und das Lernen vom Absender entfallen.
- **Bestandteile**, die eine Bedingung prüfen kann: Absender, Empfänger, Betreff, Text (Mailtext), Anhangname, Anhangtext. Den Anhangtext liest der Abruf aus PDFs; enthält ein PDF keinen Text, liest ihn Tesseract (Texterkennung, deutsch). Andere **Quellen** (Drive-Eingangsmappe, Konten, Portale) liefern dieselben Bestandteile, soweit sie sie haben; fehlende bleiben leer.
- **Vergleich**: ganzes Wort (Standard), Wortteil (nur ausdrücklich), Nummer (Trennzeichen egal), „kommt nicht vor“. Alle Bedingungen einer Regel müssen zutreffen, innerhalb einer Bedingung reicht eines der Wörter.
- **Nachvollziehbar**: Zu jeder Einordnung wird festgehalten, welche Bedingung auf welchen Teil gepasst hat (`regel_treffer` in der Notiz).
- **Wert im Unterordner**: Der Unterordner einer Ordnerregel enthält einen Wert aus dem Eingang, am besten eine gleichbleibende Nummer (Vertrag, Kunde, Mitglied), sonst den Namen der Gegenpartei. Keine Rechnungsnummer. Bestehende Drive-Ordner behalten ihren Namen; neue schlägt das System als „Gegenpartei_Nummer“ vor.
- **Eindeutig**: Auf einen Eingang darf genau eine **Ordnerregel** passen. Passen mehrere, ist das ein **Regelkonflikt**: Beim Anlegen prüft das System die Regel gegen alle bisherigen Eingänge und zeigt Überschneidungen, Harald schärft nach. Tritt ein Konflikt im Abruf auf, kommt der Eingang mit beiden Regeln nach „Zu erledigen“. **Merkmalregeln** (nur Personen, weitere Themen, Objekte, Steuerbezug) dürfen zusätzlich passen.
- **Stufen**: Spam-Wert (bleibt, braucht keine Pflege), dann Regeln, dann KI-Vorschlag. Ohne passende Regel entscheidet nie etwas ohne Haralds Freigabe; gelernt wird nur über **Regelvorschläge** (zweimal Gleiches abgelegt, oder Neuaufbau).
- **Neuaufbau**: `regeln/mail.json` wird geleert (Version 3). Die KI liest den Bestand (Notizen, Ordnerliste, Dateien in den Drive-Ordnern 2025 und 2026 mit Text, Mail-Index) und schreibt je Ordner einen Regelvorschlag, dessen Bedingungen in diesen Dokumenten vorkommen. Jeder Vorschlag zeigt die Eingänge, auf die er passen würde; Harald übernimmt einzeln oder „alle übernehmen“ für Vorschläge ohne Konflikt.
- **Steuer**: Jeder Ordner kann einen festen **Steuerbezug** haben, Steuerregeln (Merkmalregeln) ergänzen inhaltliche Fälle (z. B. ausgewiesener Arbeitslohn → §35a). Ein Steuerbezug ist ein **Steuerposten** aus `config/steuerposten.yaml` (Person · Anlage · Objekt · Posten, ohne Zeilennummern), gebaut aus den Steuererklärungen 2024/2025; neue Posten gelten erst nach Haralds OK. Aus Text und Texterkennung kommen **Betrag**, Zahlungs- oder Fälligkeitsdatum und bei §35a der Lohnanteil in die Notiz. Das Steuerjahr ist das **Zugehörigkeitsjahr**. Der Reiter „Steuer“ zeigt je Jahr und Person Summen, Belege und fehlende Belege und bietet eine CSV für WISO. Zusammenveranlagung und Aufteilung auf Objekte sind Sache der Steuererklärung bzw. kommen später mit den Umsätzen.

## Considered Options

- Erste passende Regel gewinnt (wie bisher) oder die genauere gewinnt: verworfen, Harald will eindeutige Regeln, Überschneidungen werden nachgeschärft.
- Alte Regeln, Verwerfen-Liste und Vertragsliste übernehmen: verworfen, Harald will komplett neu beginnen; die Inhalte entstehen aus dem Bestand wieder.
- Texterkennung über die KI (Bild an das Modell): verworfen, kostet je Seite; Tesseract läuft kostenlos im Abruf.
- Zeilennummern der Steuerformulare als Steuerbezug: verworfen, sie ändern sich jedes Jahr.

## Consequences

- Bis Harald die neuen Regelvorschläge übernimmt, landen mehr Mails mit KI-Vorschlag in „Zu erledigen“.
- Der Abruf braucht Tesseract und poppler im GitHub-Lauf (apt), das Drive-Skript bleibt unverändert.
- Der Neuaufbau liest Drive-Dateien über die Drive-Brücke bzw. den Drive-Zugang des Laufs; Ordner, die Harald nur in Drive anlegt, kommen weiter über einen Abgleich der Ordnerliste hinein.
