# Keine Kundeneinspeisung in den plombierten Anschlussraum

Die ursprüngliche §14a-Planung versorgte die FNN-Steuerbox der infra Fürth über zwei Adern (L, N) aus dem kundeneigenen Verteiler und brückte die Kundenphase auf den Relaisausgang C1 der Steuerbox. Damit sollte die Steuerbox ohne Öffnen der Plombierung messbar bleiben.

Das ist unzulässig: Der obere Anschlussraum gehört dem Netzbetreiber, wird von ihm verplombt und versorgt (NAV § 13, VDE-AR-N 4100). Eine Kundenphase auf einem Relaiskontakt unbekannter Auslegung erzeugt ein Rückeinspeiserisiko und kann die Steuerbox zerstören; die Brücke kann den Steuerkontakt dauerhaft überbrücken und damit die §14a-Steuerbarkeit aufheben.

Entscheidung: Kundenseitige Schnittstelle ist ausschließlich der Steuerausgang der Steuerbox. Zwei Varianten sind zulässig: (A) potentialfreier Kontakt der Steuerbox schaltet die 230-V-Spule des Koppelrelais, die der Kunde über einen eigenen LS B6A bereitstellt; (B) die Steuerbox liefert einen geschalteten L'-Ausgang, der direkt auf die Spule geht. Welche Variante gilt, gibt der Netzbetreiber vor. Es wird keine Ader in den OAR eingeführt und keine Brücke auf C1 gelegt.

## Considered Options

- Steuerbox aus dem Kundenverteiler versorgen (ursprünglicher Plan): verworfen, unzulässig und gefährlich.
- Nur potentialfreien Kontakt zulassen: bevorzugt, weil dann keine 230-V-Fremdspannung in die Steuerbox gelangt; Variante B bleibt als netzbetreiberseitige Alternative offen.
- Messpunkte in den OAR legen: verworfen, dafür gibt es die kundeneigenen Messertrennklemmen außerhalb der Plombierung.

## Consequences

- Die Steuerbox muss vom Netzbetreiber versorgt werden; der Kunde stellt nur den Spulenkreis.
- Die Messertrennklemmen -X1.1/-X1.2 liegen außerhalb der Plombierung und bleiben bedienbar.
- Vor Bestellung ist die Variante (A oder B) beim Netzbetreiber abzufragen.
