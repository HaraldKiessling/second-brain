# Keine Kundeneinspeisung in Netzbetreiber-Klemmen, beide Steuerbox-Varianten vorbereitet

Der ursprüngliche Plan versorgte die FNN-Steuerbox über L und N aus dem Kundenverteiler und brückte die Kundenphase auf den Relaisausgang C1. Der obere Anschlussraum (OAR) ist an dieser Anlage **nicht plombiert**; daraus folgt aber nicht, dass Kundenadern an Netzbetreiber-Klemmen gelegt werden dürfen. Die Steuerbox bleibt Betriebsmittel des Netzbetreibers; eine Fremdeinspeisung auf C1 ist ein Rückeinspeiserisiko und kann den Steuerkontakt überbrücken.

Entscheidung: Kundenseitig wird ausschließlich der Steuerausgang benutzt. Es werden **beide** Varianten vorbereitet: (A) potentialfreier Kontakt COM/NO schaltet die 230-V-Spule des Koppelrelais, versorgt über einen eigenen LS B6A; (B) ein geschalteter L'-Ausgang geht über die Klemme -X1.3 auf dieselbe Spule. Eine Brücke B1 wählt die aktive Variante; gleichzeitige Einspeisung ist ausgeschlossen. Welche Variante gilt, entscheidet der Netzbetreiber vor Ort.

## Considered Options

- Steuerbox aus dem Kundenverteiler versorgen und C1 brücken: verworfen, Rückeinspeisung und Überbrückung des Steuerkontakts.
- Nur Variante A vorsehen: verworfen, weil die Schnittstelle von infra Fürth nicht öffentlich dokumentiert ist.
- Beide Varianten vorbereiten und vor Ort wählen: gewählt, keine Nacharbeit im Verteiler.

## Consequences

- Der OAR bleibt zugänglich, wird aber nicht umverdrahtet.
- Es sind drei Klemmen auf -X1 nötig (L, N, L').
- Die Auswahl ist im Übergabeprotokoll zu dokumentieren.
