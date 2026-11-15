# Wärmepumpe sperrt nur die Zusatzheizung, nicht den Kompressor

Die Wärmepumpe Vaillant aroTHERM plus VWL 75/6 A mit uniTOWER VIH QW 190/6 E hat einen potentialfreien EVU-Eingang (X206 / S20), der werksseitig gebrückt ist. Die ursprüngliche Planung öffnete diese Brücke im §14a-Fall über ein Koppelrelais und ging davon aus, dass der Regler VRC 720 dann die Zusatzheizung sperrt.

Das ist nur richtig, wenn der Regler entsprechend konfiguriert ist. Bei der Einstellung einer Gesamtsperre würde der Kompressor hart abgeschaltet; das wäre keine Dimmung und würde die Mindestleistung von 4,2 kW unterschreiten. Außerdem ist die Klemmenzuordnung S20/S21 und die Wirkung des Parameters „EVU-Sperre“ (Code 17) an der verbauten Anlage zu verifizieren.

Entscheidung: Die §14a-Sperre wirkt ausschließlich auf die Zusatzheizung (9-kW-Heizstab); der Kompressor läuft weiter. Die potentialfreie Schleife wird über ein Koppelrelais Finder 38.51 geführt (Ruhekontakt 11–12 geschlossen = Normalbetrieb). Die werkseitige Brücke an S20 wird entfernt. Die Steuerleitung ist geschirmt (J-Y(ST)Y 2×2×0,8), der Schirm wird einseitig im Zählerschrank auf PE gelegt. Auf S20 wird keine Fremdspannung eingespeist.

## Considered Options

- Gesamtsperre der Wärmepumpe: verworfen, keine Dimmung, Unterschreitung der Mindestleistung.
- Sperre nur der Zusatzheizung: gewählt, lässt den Kompressor arbeiten und hält die Restleistung unter 4,2 kW.
- Steuerung über ebusd/Cloud statt Hardwarekontakt: verworfen für die §14a-Funktion, weil sie von Software und Netzwerk abhängt; die Cloud-Anbindung bleibt für Komfort und Monitoring.

## Consequences

- Die §14a-Funktion ist hardwareseitig fail-safe; bei Ausfall der Steuerspannung bleibt die Anlage betriebsbereit, die Störung ist zu melden.
- Der Heizstab steht im Dimmfall nicht zur Verfügung; die Warmwasserbereitung muss der Kompressor allein leisten.
- Die Parameter und die Klemmenzuordnung sind vor Inbetriebnahme am Gerät zu prüfen (offene Punkte E5, E6).
