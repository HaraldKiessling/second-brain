# Wallbox: Vollabschaltung über 4-poliges Schütz statt Dimmen oder Phasenabwurf

Die erste Fassung wollte L2/L3 über ein Hager ESC227 abwerfen und einphasig weiterladen. Das Datenblatt weist ESC227 als **1 Schließer + 1 Öffner, 2-polig, 25 A** aus — für eine dreiphasige Abschaltung ungeeignet; außerdem wäre der Wegfall von Phasen während der Ladung kein definierter Zustand.

Der Betreiber will eine möglichst robuste Lösung ohne Softwareabhängigkeit. go-e erlaubt die Trennung der Stromversorgung ausdrücklich jederzeit und nennt die Schützschaltung selbst als §14a-konforme Option; sie kann allerdings nur abschalten, nicht dimmen.

Entscheidung: Die Wallbox wird im §14a-Fall über ein **4-poliges Installationsschütz Hager ESC440** (4 Schließer, 40 A AC-1, Spule 230 V AC) allpolig abgeschaltet (L1, L2, L3, N). Die Spule wird im Normalbetrieb über den NC-Kontakt des Koppelrelais bestromt und fällt beim §14a-Signal ab. Die Vollabschaltung ist eine **freiwillige Kundentscheidung**; sie ist nicht die Dim mstufe des Netzbetreibers. Falls der Netzbetreiber die 4,2-kW-Dimmung verlangt, bleibt die Modbus-TCP-Ansteuerung (Register 211) als Option.

## Considered Options

- Phasenabwurf L2/L3 (ESC227): verworfen, Gerät ungeeignet und Betriebszustand undefiniert.
- Dimmen über EMS/evcc: verworfen als Primärlösung, weil Softwareabhängigkeit ausdrücklich nicht gewünscht ist.
- Vollabschaltung über 4-poliges Schütz: gewählt, einfach, robust, herstellerseitig erlaubt.
- Modbus-Dimmung als Reserve: bleibt dokumentiert.

## Consequences

- Im §14a-Fall lädt die Wallbox nicht; das ist gewollt.
- Das Schütz ist im Normalbetrieb dauerhaft bestromt (AC-1, 40 A) — Geräusch und Erwärmung sind zu prüfen.
- Der LS B16 A bleibt die Trennstelle für Wartung, nicht das Schütz.
- 4,2-kW-Dimmung ist ohne Zusatzaufwand nicht möglich; Option Modbus ist vorbereitet.
