# Wärmepumpe: EVU-Sperre über S21 als Schließer

Die ursprüngliche Planung ging von einem Öffner an Klemme S20 mit werkseitiger Brücke aus. Die Vaillant-Installationsanleitung „Elektrische Anschlüsse aroTHERM plus" (09-20, Kap. 3 EVU-Sperre) belegt: Der Lastabwurfkontakt liegt an **X106/S21**, ist ein **potentialfreier Schließer** mit 24 V/0,1 A und muss zum Blockieren **geschlossen** werden. Eine werkseitige Brücke ist nicht dokumentiert; offen bedeutet Normalbetrieb. Die Bezeichnung „Code 17" ist nicht belegt.

Entscheidung: Das Koppelrelais -K1 schließt im §14a-Fall den Kontakt 11–14 und damit die Schleife S21-1/S21-2. Im Normalbetrieb ist die Schleife offen. Es wird keine Spannung auf S21 gelegt. Die Steuerleitung ist geschirmt (J-Y(ST)Y 2×2×0,8), der Schirm wird einseitig auf PE gelegt. Die Sperre wirkt auf die Zusatzheizung; der Kompressor läuft weiter.

## Considered Options

- Öffner an S20 mit Brücke: verworfen, durch Herstellerdokument nicht gedeckt.
- Schließer an S21: gewählt, entspricht der Herstellerangabe.
- Sperre über ebusd/Cloud: verworfen für die §14a-Funktion, weil softwareabhängig.

## Consequences

- Die Logik ist gegenüber der ersten Fassung invertiert: Relais angezogen = Sperre.
- Der Parameter für die EVU-Sperre am VRC 720 ist vor Ort zu prüfen; „nur Zusatzheizung" muss eingestellt sein.
- Bei Ausfall der Steuerspannung bleibt die WP normal betriebsbereit; die Störung ist zu melden.
