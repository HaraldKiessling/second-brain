# Wallbox-Dimmung über Ladestrom statt Phasenabwurf

Die ursprüngliche Planung warf im §14a-Dimmfall die Phasen L2 und L3 der Wallbox über ein Installationsschütz Hager ESC227 ab, sodass der go-e Charger Gemini einphasig mit 16 A (3,68 kW) weiterladen sollte.

Drei Gründe sprechen dagegen: Der Gemini 11 kW ist ein fest dreiphasiges Gerät ohne interne Phasenumschaltung; der Wegfall von L2/L3 während der Ladung ist kein definierter Betriebszustand (Phasenfehler, Lichtbogen am Schütz, Ladungsabbruch). Einphasig 16 A ergeben 3,68 kW und liegen unter der Mindestleistung von 4,2 kW, die § 14a EnWG und die BNetzA-Festlegung BK6-22-300 verlangen. Ein Schütz ist außerdem kein Lasttrennschalter für wiederkehrende Schaltspiele unter 16 A.

Entscheidung: Die Wallbox wird über ihren Ladestrom-Sollwert gedimmt, dreiphasig und mit mindestens 7 A je Phase (≈ 4,8 kW). Drei Wege sind zulässig: (W1) ein EMS/evcc setzt den Sollwert über die lokale go-e-API, (W2) ein vom Hersteller freigegebener potentialfreier Steuereingang am Charger, (W3) ein zertifizierter Lastmanager des Netzbetreibers. Das Installationsschütz ESC227 entfällt; die Plätze 8–9 bleiben Reserve.

## Considered Options

- Phasenabwurf über Schütz (ursprünglicher Plan): verworfen, technisch undefiniert und normative Unterdimmung.
- Dimmung über Ladestrom mit EMS (W1): bevorzugt, keine Änderung der Leistungsverdrahtung, nutzt die vorhandene go-e-Integration.
- Feste Dimmung über potentialfreien Eingang (W2): nur mit Herstellerfreigabe.
- Lastmanager des Netzbetreibers (W3): zulässig, aber zusätzliche Komponente und Abstimmung nötig.

## Consequences

- Die Wallbox bleibt dreiphasig angeschlossen; FI und LS B16A bleiben unverändert.
- Die §14a-Dimmung der Wallbox ist softwaregestützt; fällt das EMS aus, muss die Dimmung anderweitig sichergestellt oder die Störung gemeldet werden (offener Punkt E2).
- Es entsteht keine Schieflast und kein Schaltverschleiß durch Phasentrennung.
