"""Betrag, Zahlungsdatum und Lohnanteil aus Mail- und Anhangtext (fuer die Steuer).

Gesucht wird zuerst ein beschrifteter Endbetrag (Rechnungsbetrag, Gesamtbetrag,
zu zahlen, Beitrag ...), sonst der groesste Euro-Betrag. Der Lohnanteil (fuer
§35a) steht auf Handwerkerrechnungen als Arbeitskosten, Lohnkosten oder
Arbeitslohn. Das Zahlungsdatum ist die angekuendigte Zahlung, Faelligkeit oder
Abbuchung (wie in jahr.py); den echten Tag liefern spaeter die Kontoumsaetze.
Alles sind Vermutungen: die Web-App zeigt sie, Harald kann sie aendern.
"""

import re

from . import jahr as jz

_ZAHL = r'(\d{1,3}(?:[.\s]\d{3})*,\d{2}|\d+,\d{2}|\d{1,3}(?:,\d{3})*\.\d{2})'
_EURO = r'(?:€|eur(?:o)?\b)'
EURO_BETRAG = re.compile(r'(?:%s\s*%s|%s\s*%s)' % (_ZAHL, _EURO, _EURO, _ZAHL), re.I)
ENDBETRAG = re.compile(
    r'(?:rechnungsbetrag|gesamtbetrag|endbetrag|gesamtsumme|bruttobetrag|summe\s+brutto|'
    r'brutto(?:summe)?|zu\s+zahlen(?:der\s+betrag)?|zahlbetrag|zahlungsbetrag|'
    r'(?:jahres|gesamt)?beitrag|abbuchungsbetrag|lastschriftbetrag|betrag|summe|total)'
    r'[^\d\n]{0,40}?%s' % _ZAHL, re.I)
LOHN = re.compile(
    r'(?:arbeitskosten|lohnkosten|arbeitslohn|lohnanteil|arbeitsleistung|montagekosten|'
    r'(?:davon\s+)?(?:arbeits|lohn)anteil|personalkosten)[^\d\n]{0,40}?%s' % _ZAHL, re.I)


def zahl(text):
    """'1.234,56' -> 1234.56; '1,234.56' -> 1234.56"""
    t = str(text).replace(' ', '')
    if ',' in t and (t.rfind(',') > t.rfind('.')):
        t = t.replace('.', '').replace(',', '.')
    else:
        t = t.replace(',', '')
    try:
        return round(float(t), 2)
    except ValueError:
        return None


def betrag(*texte):
    """Endbetrag in Euro oder None."""
    alles = '\n'.join(t or '' for t in texte)
    beschriftet = [zahl(m.group(1)) for m in ENDBETRAG.finditer(alles)]
    beschriftet = [b for b in beschriftet if b]
    if beschriftet:
        return max(beschriftet)  # Gesamt steht meist neben Teilbetraegen
    alle = [zahl(next(g for g in m.groups() if g)) for m in EURO_BETRAG.finditer(alles)]
    alle = [b for b in alle if b]
    return max(alle) if alle else None


def lohnanteil(*texte):
    alles = '\n'.join(t or '' for t in texte)
    werte = [zahl(m.group(1)) for m in LOHN.finditer(alles)]
    werte = [w for w in werte if w]
    return max(werte) if werte else None


def zahlung(*texte):
    """Datum der angekuendigten Zahlung, Faelligkeit oder Abbuchung, oder None."""
    alles = '\n'.join(t or '' for t in texte)
    for m in jz.ZAHLUNG.finditer(alles):
        d = jz._datum(m.groups())
        if d:
            return d
    return None


def felder(*texte):
    """Felder fuer die Notiz: betrag, zahlung (Datum), lohnanteil (nur gefundene)."""
    f = {}
    b = betrag(*texte)
    if b:
        f['betrag'] = b
    z = zahlung(*texte)
    if z:
        f['zahlung'] = z
    l = lohnanteil(*texte)
    if l:
        f['lohnanteil'] = l
    return f
