"""Kennungen aus Dokumenttexten (ADR 0004, Neuaufbau aus Drive-Inhalten).

Eine Kennung ist ein Wert, der die Gegenpartei oder den Vertrag in jedem
Schreiben wiedererkennbar macht: Vertrags-, Kunden-, Mitglieds-,
Versicherten-, Policennummer, Kassenzeichen, Personennummer. Rechnungs-,
Telefon-, Bank- und Belegnummern, Betraege und Daten sind keine Kennung.

kennungen(text) liest sie aus einem Text (PDF-Text oder Texterkennung).
ordner_kennungen(dokumente) fasst sie pro Ordner zusammen: Eine Kennung zaehlt
fuer einen Ordner, wenn sie dort beschriftet vorkommt (z. B. "Vertragsnummer
40-012450403-8") oder in mind. zwei Dokumenten steht, und in keinem anderen
Ordner. So fallen eigene Daten (Steuer-ID, Geburtsdatum, eigene IBAN) heraus,
weil sie in vielen Ordnern stehen.

Gespeichert wird nur das Ergebnis (Ordner -> Kennungen mit Anzahl
Dokumente), nie der Dokumenttext.
"""

import collections
import re

from . import regeln

# Beschriftungen, nach denen eine Kennung steht
BESCHRIFTUNG = re.compile(r'''(?ix)
  (?:vertrags?\s*-?\s*(?:nummer|nr\.?)|versicherungs\s*-?\s*(?:schein\s*-?\s*)?(?:nummer|nr\.?)
   |vers\.?\s*-?\s*nr\.?|kunden\s*-?\s*(?:nummer|nr\.?)|kd\.?\s*-?\s*nr\.?|mitglieds?\s*-?\s*(?:nummer|nr\.?)
   |versicherten\s*-?\s*(?:nummer|nr\.?)|kassenzeichen|personennummer|vertragskonto|polic(?:en|e)\s*-?\s*(?:nummer|nr\.?)?
   |darlehens\s*-?\s*(?:nummer|nr\.?|konto)|aktenzeichen|vorgangsnummer|objekt\s*-?\s*nr\.?
   |steuer\s*-?\s*(?:nummer|nr\.?)|bei\s+r[uü]ckfragen\s+(?:geben\s+sie\s+)?bitte(?:\s+an)?
   |mitgliedschafts\s*-?\s*(?:nummer|nr\.?)|mitgliedsnr|referenz|kundennr|vertragsnr)
  \s*[:.\#]?\s*''')

# Ein Wert: Ziffern mit Trennzeichen / - . und Grossbuchstaben-Bloecken,
# innerhalb einer Beschriftung auch mit einfachen Leerzeichen ("58 130667 K 006")
WERT = r'[A-Z]{0,3}\d[\dA-Z]*(?:[/.\-][\dA-Z]+)*'
FREI = re.compile(r'(?<![\w/.\-])' + WERT + r'(?![\w])')
TEIL = re.compile(WERT + r'|[A-Z]{1,2}')

KEINE = re.compile(r'''(?x)
   ^\d{1,2}\.\d{1,2}\.\d{2,4}         # Datum
  |^(19|20)\d{2}([-/.]?\d{2}){0,2}$    # Jahr, Monat, Datum (2025-02, 20250619)
  |^\d{1,2}/(19|20)\d{2}$              # 09/2024
  |^(19|20)\d{2}/(19|20)\d{2}$         # 2025/2026
  |^DE\d{2}                           # IBAN, USt-IdNr
  |^\d{1,3}(\.\d{3})+$                # Betrag mit Tausenderpunkt
  |^\d{1,3}(\.\d{1,3}){3}$            # IP-Adresse
  |^\d{1,5}[-/]9\d{4}$                # Hausnummer/Postfach-Postleitzahl
  |^\+?49
''')
# nur ohne Beschriftung ausgeschlossen: Telefon-/Faxnummern und Durchwahlen
TELEFON = re.compile(r'^0\d{2,5}([/\- ]\d+)*$|^\d{3,5}-\d{3,4}$|^\d{1,3}\.\d+\.\d+')

# Formen, die auch in nur einem Dokument als Kennung gelten
FORM = re.compile(r'''(?x)
   ^\d{3}/\d{6}-[A-Z](-\d{1,2})?$      # HUK 702/213446-Y-16
  |^\d{2}-\d{6,9}-\d{1,2}(-\d)?$     # HDI 40-012450403-8
  |^[A-Z]\d{9}$                        # Krankenversichertennummer
  |^\d{7}/[A-Z]+/\d+$                  # Kassenzeichen 1142801/GRDABG/1
  |^\d{1,3}/\d{3,}/\d{3,}$             # 6/600775/21363, 218/236/00744
''')
# davon die Vertragsformen (ohne Steuernummer), die schon in einem Dokument reichen
VERTRAG = re.compile(r'^\d{3}/\d{6}-[A-Z](-\d{1,2})?$|^\d{2}-\d{6,9}-\d{1,2}(-\d)?$|^[A-Z]\d{9}$'
                     r'|^\d{7}/[A-Z]+/\d+$')


def _ziffern(w):
    return sum(c.isdigit() for c in w)


def normal(w):
    """Vergleichsform: nur Buchstaben und Ziffern, gross."""
    return re.sub(r'[^0-9A-Za-z]', '', w).upper()


def _gueltig(w, beschriftet):
    w = w.strip(' .-/')
    if _ziffern(w) < (4 if beschriftet else 6) or len(w) > 30:
        return None
    if KEINE.search(w):
        return None
    if not beschriftet and (TELEFON.search(w) or not FORM.search(w) and not re.search(r'[/-]', w)):
        return None  # ohne Beschriftung nur Nummern mit Gliederung ('602/718680-P')
    return w


def _nach_beschriftung(rest):
    """Wert direkt nach einer Beschriftung; Leerzeichen gehoeren dazu, solange
    die Teile kurz sind ('58 130667 K 006', '1014 772 751-01'), nicht bei
    '110757412 90766' (Nummer und Postleitzahl)."""
    rest = rest.lstrip(' :"\'\n')
    teile = []
    pos = 0
    while True:
        m = TEIL.match(rest, pos)
        if not m or (m.end() < len(rest) and (rest[m.end()].isalnum())):
            break
        t = m.group(0)
        if teile and not (len(teile[-1]) <= 4 or len(t) <= 3):
            break
        if not teile and not any(c.isdigit() for c in t):
            break
        teile.append(t)
        pos = m.end()
        if rest[pos:pos + 1] != ' ' or len(teile) >= 4:
            break
        pos += 1
    while teile and not any(c.isdigit() for c in teile[-1]):
        teile.pop()
    if teile and KEINE.search(teile[0]):
        return None
    if len(teile) >= 2 and teile[0] == teile[1]:
        return None  # doppelt gelesener Text ('56 56 947 947')
    return ' '.join(teile) or None


def kennungen(text):
    """{normalform: (anzeige, beschriftet)} aus einem Dokumenttext."""
    t = str(text or '').replace('\\', '')
    aus = {}
    for m in BESCHRIFTUNG.finditer(t):
        n = _nach_beschriftung(t[m.end():m.end() + 60])
        if not n:
            continue
        w = _gueltig(n, True)
        if w:
            aus[normal(w)] = (w, True)
    for m in FREI.finditer(t):
        w = _gueltig(m.group(0), False)
        if w and normal(w) not in aus:
            aus[normal(w)] = (w, False)
    return aus


def domains(text):
    """Absender-Domains aus E-Mail-Adressen und Webadressen im Text."""
    t = regeln.falten(text)
    gef = set()
    for m in re.finditer(r'(?:[a-z0-9._-]+@([a-z0-9-]+(?:\.[a-z0-9-]+)+)|(?:www\.)([a-z0-9-]+(?:\.[a-z0-9-]+)+))(?![a-z0-9-])', t):
        d = (m.group(1) or m.group(2)).strip('.')
        teile = d.split('.')
        if len(teile) >= 2 and 2 <= len(teile[-1]) <= 4:
            gef.add('.'.join(teile[-2:]))
    return gef


ALLGEMEINE_DOMAINS = {'gmail.com', 'gmx.de', 'gmx.net', 'web.de', 't-online.de', 'googlemail.com',
                      'outlook.com', 'hotmail.com', 'yahoo.de', 'yahoo.com', 'icloud.com', 'online.de',
                      'google.com', 'adobe.com', 'apple.com', 'microsoft.com'}


# Dokumente mit Zugangsdaten werden nicht ausgewertet (keine Nummer daraus gespeichert)
GEHEIM = re.compile(r'(?i)passw|kennwort|\bpin\b|\bpuk\b|recovery|wiederherstellung|api[\s_-]?key|'
                    r'token|zugangsdaten|sicherheits-?\s*schl|ger[aä]teschl|secret|2fa|tan-?liste')


def ordner_kennungen(dokumente):
    """dokumente: [{'ordner': 'thema/unterordner', 'text': ...}] ->
    {ordner: {'dokumente': n, 'nummern': [{'wert','dokumente','beschriftet'}], 'domains': [...]}}"""
    je = collections.defaultdict(lambda: {'n': 0, 'num': collections.Counter(), 'besch': set(),
                                          'anz': {}, 'dom': collections.Counter()})
    wo_num = collections.defaultdict(set)
    wo_dom = collections.defaultdict(set)
    for d in dokumente:
        if GEHEIM.search(d.get('text', '') + ' ' + d.get('titel', '')):
            continue
        o = d['ordner']
        e = je[o]
        e['n'] += 1
        for k, (anz, b) in kennungen(d.get('text', '') + '\n' + d.get('titel', '')).items():
            e['num'][k] += 1
            e['anz'].setdefault(k, anz)
            if b:
                e['besch'].add(k)
            wo_num[k].add(o)
        for dom in domains(d.get('text', '')):
            if dom not in ALLGEMEINE_DOMAINS:
                e['dom'][dom] += 1
                wo_dom[dom].add(o)
    aus = {}
    for o, e in sorted(je.items()):
        nummern = []
        for k, c in e['num'].items():
            # gehoert zu diesem Ordner: mind. 2/3 der Dokumente mit der Nummer liegen hier
            gesamt = sum(je[x]['num'][k] for x in wo_num[k])
            if len(wo_num[k]) > 2 or c * 3 < gesamt * 2:
                continue
            if k in e['besch'] or c >= 2 or FORM.search(e['anz'][k]):
                nummern.append({'wert': e['anz'][k], 'dokumente': c, 'beschriftet': k in e['besch']})
        nummern.sort(key=lambda x: (-x['beschriftet'], -x['dokumente'], x['wert']))
        doms = [{'wert': dom, 'dokumente': c} for dom, c in e['dom'].most_common()
                if len(wo_dom[dom]) == 1]
        aus[o] = {'dokumente': e['n'], 'nummern': nummern[:8], 'domains': doms[:5]}
    return aus
