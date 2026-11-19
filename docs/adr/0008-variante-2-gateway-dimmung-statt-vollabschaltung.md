# §14a: Variante 2 (Gateway-Dimmung) statt Variante 1 (verdrahtete Vollabschaltung)

Status: **entschieden** — Option A (Eingabe des Anschlussnehmers, 2026-11-16)

## Kontext

Bisher wurde die §14a-Umsetzung als **Variante 1** geplant: kabelgebundene Steuerung über Rundsteuerempfänger (TRE) → Koppelrelais -Q0 → -K1 → -K2, mit **Vollabschaltung der Wallbox** (0 kW), S21-Sperre des Heizstabs und fail-closed-Auslegung (ADR 0006, ADR 0007).

Die tatsächlich bei infra Fürth eingereichte Anmeldung (E-Mail vom 16.01.2026) beschreibt dagegen eine **Gateway-basierte Steuerung**:

- Steuerungsart: „Direktansteuerung über Gateway (myVAILLANT connect)"
- Fernwirktechnik: Vaillant myVAILLANT connect (VR 940/940f)
- Drosselung auf 4,2 kW statt Vollabschaltung
- Messkonzept Modul 1 (gemeinsame Messung)
- Gemeldet ist nur die Wärmepumpe (VWL 75/6, 3,5 kW + Heizstab 6 kW = 9,5 kW)

Diese Anmeldung ist laut Entscheidung der maßgebliche Ist-Zustand.

## Entscheidung

**Variante 2 (Option A):** Die §14a-Steuerung erfolgt über den Vaillant-Gateway (myVAILLANT connect / VR 940/940f) mit **Dimmung auf 4,2 kW**. Die verdrahtete Variante 1 (TRE + Koppelrelais + Vollabschaltung) wird **archiviert** und ist nicht der Bauweg.

**Präzisierung (2026-11-16):** Es wird **auf der eingereichten Anmeldung aufgebaut**, nicht auf einer korrigierten Fassung. Die Anmeldung ging direkt an infra Fürth; die Klärung der technischen Umsetzbarkeit (Gateway vs. potentialfreier Kontakt, 4,2-kW-Drosselung vs. Sperre) erfolgt **in der Antwort von infra**, nicht durch einseitige Korrektur. Die fehlende Deckung durch die Vaillant-Unterlagen ist ein **offener Punkt für die Abstimmung mit infra/Vaillant**, kein Grund zur Vorab-Korrektur.

## Considered Options

- **Option A (gewählt):** Die eingereichte Anmeldung ist der Ist-Zustand → Variante 2 (Gateway, Dimmung).
- **Option B (verworfen):** Die Anmeldung ist ein veralteter Entwurf und wird durch die verdrahtete Variante 1 ersetzt.

## Consequences

- Variante 1 (ADR 0006, ADR 0007, TRE/Koppelrelais/fail-closed) wird archiviert, nicht gebaut.
- Die Softwareabhängigkeit kehrt zurück (Gateway/Cloud) — im Widerspruch zu ADR 0007 („softwareunabhängig").
- Die Wallbox (11 kW) ist in der Anmeldung nicht enthalten → eigene Regelung/Anmeldung offen.
- Offenes Risiko: TAB infra Fürth, Kap. 10.2, verlangt „ausschließlich kabelgebundene Rundsteuerempfänger" — die Gateway-Lösung muss mit infra abgestimmt werden.
- Die Angaben „Drosselbarkeit auf 4,2 kW" und „Fernwirktechnik myVAILLANT connect" sind Herstellerangaben, die noch belegt werden müssen.