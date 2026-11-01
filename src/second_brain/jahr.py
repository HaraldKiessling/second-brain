"""Zu welchem Jahr ein Dokument gehoert und ob es dauerhaft aufzuheben ist.

Harald legt nach Zugehoerigkeit ab, nicht nach Empfang:

- Mit Geldfluss zaehlt das Jahr der Zahlung (steuerliche Relevanz): eine
  Beitragsrechnung, die im Dezember 2026 kommt und im Januar 2027 abgebucht
  wird, gehoert nach 2027; eine Abrechnung fuer 2026 mit Nachzahlung 2027
  ebenfalls nach 2027.
- Ohne Geldfluss (Bescheid, Infoschreiben) zaehlt das Jahr, das der Inhalt
  betrifft ("Jahresabrechnung 2026", "Beitragsjahr 2027").
- Ist nichts erkennbar, gilt das Datum der Mail.

Der Zahltag steht selten im Dokument; die Faelligkeit oder der angekuendigte
Abbuchungstermin vertreten ihn, bis Kontoumsaetze den echten Tag liefern.

Dokumente, die viele Jahre betreffen (Kaufvertrag, Darlehen, Grundbuch,
Versicherungsschein ...), kommen zusaetzlich als Kopie in 0000-dauerhaft. Das
System schlaegt das nur vor; Harald bestaetigt es.
"""

import datetime
import re

# Datum in deutscher oder ISO-Schreibweise
_DATUM = r'(\d{1,2})\.\s?(\d{1,2})\.\s?(\d{4}|\d{2})(?!\d)|(\d{4})-(\d{2})-(\d{2})'
# Worte vor einem Datum, die einen Geldfluss ankuendigen
_ZAHLUNG = (r'f(?:ä|ae)llig(?:keit)?(?:\s*(?:datum|am|zum|ab|bis))?|zahlbar\s*(?:bis|zum|am)?|'
            r'abbuchung(?:sdatum)?(?:\s*(?:am|zum|ab))?|'
            r'(?:wird|werden)\s+(?:der\s+betrag\s+|den\s+betrag\s+|ihn\s+|diesen\s+)?'
            r'(?:am|zum|ab)|bucht?en?\s+(?:wir\s+)?(?:am|zum|ab)|abgebucht\s*(?:am|zum)?|'
            r'lastschrift(?:einzug)?\s*(?:am|zum|ab)?|einzug\s*(?:am|zum|ab)|'
            r'(?:ü|ue)berweis\w*\s*(?:bis|zum|am)|zahlung\s*(?:bis|zum|am)|'
            r'gutschrift\s*(?:am|zum)?|erstatt\w*\s*(?:am|zum|bis)')
ZAHLUNG = re.compile(r'(?:%s)[\s:]{0,4}(?:den\s+|dem\s+)?(?:%s)' % (_ZAHLUNG, _DATUM), re.I)
# "fuer das Jahr 2027", "Beitragsjahr 2027", "Jahresabrechnung 2026", "Abrechnung 2026"
_BEZUG = (r'(?:f(?:ü|ue)r\s+(?:das\s+)?(?:(?:kalender|beitrags|abrechnungs|steuer)?jahr\s+)?|'
          r'beitragsjahr|kalenderjahr|abrechnungsjahr|steuerjahr|wirtschaftsjahr|'
          r'(?:jahres|neben|betriebs|heiz|kosten|verbrauchs)?abrechnung(?:\s+f(?:ü|ue)r)?(?:\s+das\s+jahr)?|'
          r'jahresbescheinigung|lohnsteuerbescheinigung|steuerbescheid|bescheid\s+f(?:ü|ue)r|'
          r'beitrag(?:srechnung)?(?:\s+f(?:ü|ue)r)?|versicherungsjahr|zeitraum)')
BEZUG = re.compile(r'(?:%s)[\s:]{0,3}(20\d{2})(?!\d)' % _BEZUG, re.I)
# Zeitraum "01.01.2027 - 31.12.2027" oder "01.07.2026 bis 30.06.2027"
ZEITRAUM = re.compile(r'(?:%s)\s*(?:-|–|bis)\s*(?:%s)' % (_DATUM, _DATUM), re.I)

DAUERHAFT = [
    (re.compile(r'kaufvertrag|notarvertrag|kaufurkunde|notarielle?', re.I), 'Kaufvertrag'),
    (re.compile(r'darlehensvertrag|kreditvertrag|darlehensurkunde|grundschuld', re.I), 'Darlehensvertrag'),
    (re.compile(r'grundbuch', re.I), 'Grundbuch'),
    (re.compile(r'versicherungsschein|police\b|nachtrag zum versicherungsschein', re.I), 'Versicherungsschein'),
    (re.compile(r'rentenvertrag|rentenversicherung.*vertrag|riester.*vertrag', re.I), 'Rentenvertrag'),
    (re.compile(r'f(?:ö|oe)rderbescheid|zuwendungsbescheid|bewilligungsbescheid', re.I), 'Förderbescheid'),
    (re.compile(r'mietvertrag', re.I), 'Mietvertrag'),
    (re.compile(r'teilungserkl(?:ä|ae)rung|baugenehmigung|energieausweis', re.I), 'Urkunde zum Haus'),
]


def _datum(teile):
    tag, monat, jahr, ij, im, it = teile
    try:
        if ij:
            return datetime.date(int(ij), int(im), int(it))
        j = int(jahr)
        return datetime.date(j + 2000 if j < 100 else j, int(monat), int(tag))
    except ValueError:
        return None


def zugehoerigkeit(betreff, text, anhaenge=(), datum=None):
    """(jahr, grund). jahr ist None, wenn nichts erkennbar ist (dann gilt das Mail-Datum)."""
    datum = datum or datetime.date.today()
    alles = '\n'.join([betreff or '', ' '.join(anhaenge or ()), (text or '')[:6000]])
    plausibel = lambda j: abs(j - datum.year) <= 2
    for m in ZAHLUNG.finditer(alles):
        d = _datum(m.groups())
        if d and plausibel(d.year):
            return d.year, 'Zahlung am %s' % d.strftime('%d.%m.%Y')
    for m in BEZUG.finditer(alles):
        j = int(m.group(1))
        if plausibel(j):
            return j, '„%s“' % ' '.join(m.group(0).split())
    for m in ZEITRAUM.finditer(alles):
        von, bis = _datum(m.groups()[:6]), _datum(m.groups()[6:])
        if von and bis and plausibel(von.year):
            return von.year, 'Zeitraum ab %s' % von.strftime('%d.%m.%Y')
    return None, ''


def dauerhaft_vermutet(betreff, text='', anhaenge=()):
    """Grund, warum das Dokument viele Jahre betrifft, oder ''."""
    kopf = ' '.join([betreff or '', ' '.join(anhaenge or ())])
    for muster, grund in DAUERHAFT:
        if muster.search(kopf):
            return grund
    rumpf = (text or '')[:2000]
    for muster, grund in DAUERHAFT[:3]:
        if muster.search(rumpf):
            return grund
    return ''


def ordner_jahr(schluessel):
    """'0-2026' -> 2026, '2025' -> 2025, sonst None."""
    m = re.fullmatch(r'(?:0-)?(\d{4})', str(schluessel or ''))
    return int(m.group(1)) if m else None


def jahr_ordner(jahr, heute=None):
    """Name des Jahresordners in Drive: das laufende Jahr heisst 0-<jahr>."""
    heute = heute or datetime.date.today()
    return '0-%d' % jahr if jahr == heute.year else str(jahr)


def drive_id(ids, jahr):
    """Ordner-ID fuer ein Jahr aus {'0-2026': id, '2025': id}; Schluessel mit
    oder ohne 0- passen beide, damit die Daten den Jahreswechsel ueberstehen."""
    for k, v in (ids or {}).items():
        if ordner_jahr(k) == jahr:
            return v
    return None
