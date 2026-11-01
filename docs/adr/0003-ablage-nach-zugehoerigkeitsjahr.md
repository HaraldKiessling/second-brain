# Ablage nach Zugehörigkeitsjahr, Kopie in 0000-dauerhaft

Bisher kam jede Mail in den Jahresordner ihres Empfangsdatums. Harald legt aber nach dem Jahr ab, zu dem ein Dokument gehört: mit Geldfluss zählt das Jahr der Zahlung, weil das für die Steuer zählt (eine Beitragsrechnung vom Dezember 2026, abgebucht im Januar 2027, gehört nach 2027; eine Abrechnung für 2026 mit Nachzahlung 2027 ebenfalls nach 2027), ohne Geldfluss das Jahr, das es betrifft. Dokumente, die viele Jahre betreffen, liegen zusätzlich in „0000-dauerhaft“, das eigene Unterordner hat (nach Objekt, z. B. „03 Kieler 37“).

Entscheidung: Der Abruf bestimmt das **Zugehörigkeitsjahr** aus Mailtext und Anhangnamen (`src/second_brain/jahr.py`: Zahlung, Fälligkeit oder Abbuchung vor einem Datum; sonst „Abrechnung 2026“, „Beitragsjahr 2027“; sonst Zeitraumbeginn; sonst Mail-Datum) oder übernimmt das Jahr der KI. Weicht es vom Empfangsjahr ab, steht es als `jahr` mit `jahr_grund` in der Notiz und als Hinweis in der Web-App, wo Harald es ändern kann. Den echten Zahltag liefern später die Kontoumsätze.

Die Dauerablage schlägt das System nur vor (`dauerhaft_vorschlag`); erst Haralds Bestätigung setzt `dauerhaft: <Unterordner>`. Die Kopie lädt der Drive-Schritt mit den vorhandenen Aktionen `hochladen` und `verschieben` hoch, die Drive-Brücke bleibt unverändert. Fehlen die Dateien im Lauf, holt `second-brain nachholen` sie aus dem Postfach.

Alle Jahresordner und Themenordner stehen mit ID in `config/themen.yaml` (`jahre`, `drive`, `dauerhaft`). IDs gelten über den Jahreswechsel: „0-2026“ und „2026“ meinen denselben Ordner. Hat ein Thema in einem älteren Jahr keinen gleichnamigen Ordner, legt die Brücke ihn im Jahresordner an.

Verworfen: eine Verknüpfung statt Kopie in 0000-dauerhaft (bräuchte eine neue Brücken-Aktion und damit eine Neubereitstellung durch Harald); Ablage nach Empfangsdatum mit Steuerbezug als Feld (findet Harald in Drive nicht wieder).
