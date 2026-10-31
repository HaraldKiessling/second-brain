"""Regel-Engine: ordnet einen Mail-Eingang ohne KI ein.

Reihenfolge (siehe Anforderung F7/F8):
  1. verwerfen   - Spam/Newsletter-Muster in Absender oder Betreff
  2. notiz       - eine Regel passt (Absender- und/oder Betreff-Muster) und
                   die Mail hat ein Dokument; ohne Dokument nur mit
                   "ohne_anhang": true in der Regel, sonst Indexeintrag
  3. offen       - Versicherer mit Dokument-Anhang (Sparte aus dem Betreff),
                   oder unbekannt mit Dokument-Anhang -> KI ordnet spaeter ein
  4. index       - alles andere wird nur als Indexeintrag erfasst

Muster sind kleingeschriebene Teilstrings, wie in der bisherigen
gmx-routing.json.
"""

from dataclasses import dataclass, field

VERWERFEN = 'verwerfen'
NOTIZ = 'notiz'
OFFEN = 'offen'
INDEX = 'index'


@dataclass
class Ergebnis:
    aktion: str
    grund: str
    regel: str = ''
    thema: str = ''
    unterordner: str = ''
    personen: list = field(default_factory=list)
    konfidenz: float = 1.0
    durch: str = ''          # wer entschieden hat: regel/<name>, heuristik/..., ki/<modell>
    vorschlag: object = None  # einordnen.Vorschlag bei offen
    spam: float = 0.0
    mail_drive: bool = False  # Mail selbst als PDF in die Drive-Ablage


def _trifft(muster, text):
    return any(m.lower() in text for m in muster)


def _sparte(betreff, sparten):
    for sparte, woerter in sparten.items():
        if _trifft(woerter, betreff):
            return sparte
    return ''


def einordnen(absender, betreff, hat_dokument, regelwerk, empfaenger=''):
    """Ergebnis fuer einen Mail-Eingang nach dem Regelwerk (regeln/mail.json).

    Eine Regel kann Muster fuer absender, empfaenger (An/Cc) und betreff haben;
    alle angegebenen muessen passen.
    """
    ab = (absender or '').lower()
    be = (betreff or '').lower()
    an = (empfaenger or '').lower()

    for m in regelwerk.get('verwerfen', []):
        if m.lower() in ab or m.lower() in be:
            return Ergebnis(VERWERFEN, 'Spam/Newsletter: ' + m)

    for r in regelwerk.get('regeln', []):
        if not (r.get('absender') or r.get('betreff') or r.get('empfaenger')):
            continue
        if r.get('absender') and not _trifft(r['absender'], ab):
            continue
        if r.get('empfaenger') and not _trifft(r['empfaenger'], an):
            continue
        if r.get('betreff') and not _trifft(r['betreff'], be):
            continue
        if not hat_dokument and not r.get('ohne_anhang'):
            return Ergebnis(INDEX, 'Regel %s, aber kein Dokument' % r['name'],
                            regel=r['name'], thema=r['thema'])
        return Ergebnis(NOTIZ, 'Regel ' + r['name'], regel=r['name'],
                        thema=r['thema'], unterordner=r.get('unterordner', ''),
                        personen=list(r.get('personen') or
                                      regelwerk.get('standard_personen', [])),
                        mail_drive=bool(r.get('mail_drive')))

    if not hat_dokument:
        return Ergebnis(INDEX, 'keine Regel, kein Dokument-Anhang')

    pruefen = regelwerk.get('pruefen', {})
    if _trifft(pruefen.get('absender', []), ab):
        sparte = _sparte(be, pruefen.get('sparten', {}))
        return Ergebnis(OFFEN, 'Versicherung pruefen' +
                        (': ' + sparte if sparte else ''))

    return Ergebnis(OFFEN, 'unbekannter Absender mit Dokument')
