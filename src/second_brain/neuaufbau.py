"""Neuaufbau der Regeln aus dem Bestand (ADR 0004).

Fuer jeden bekannten Drive-Ordner (config/ordner.yaml) entsteht ein
Regelvorschlag, dessen Bedingung aus dem Ordnernamen und dem Bestand
ableitbar ist:

  1. Steht im Ordnernamen eine Nummer (Vertrags-, Kunden-, Kassenzeichen,
     mind. 5 Ziffern), wird sie die Bedingung: "Mail oder Anhang enthaelt
     die Nummer". Trennzeichen sind egal.
  2. Sonst: ein Name aus dem Ordnernamen (z. B. "ionos", "Telekom"), der in
     der Absender-Domain bisheriger Mails vorkommt; Bedingung "Absender
     enthaelt <domain>".
  3. Ohne beides kein Vorschlag (die KI schlaegt spaeter vor, sobald Mails
     dafuer kommen).

Danach wird nachgeschaerft: Passen zwei Vorschlaege auf dieselben Mails (z. B.
eine HUK-Nummer, die auch in einer laengeren HUK-Nummer steckt, oder dieselbe
Absender-Domain fuer zwei Ordner), bekommt jeder ein Unterscheidungswort aus
seinem Ordnernamen ("Hausrat", "BMW") als weitere Bedingung. Was dann noch
kollidiert, zeigt die Web-App als Konflikt; Harald entscheidet.

Die Vorschlaege gehen nach regeln/mail-vorschlaege.json (herkunft: bestand)
und gelten erst, wenn Harald sie uebernimmt.
"""

import collections
import email.utils
import re

from . import daten, regeln

# Woerter in Ordnernamen, die nichts ueber die Gegenpartei sagen
GENERISCH = set('''
und der die das mit fuer von harald samantha uschi rainer caleb privat weitere kosten sonstiges
neu alt ag gmbh se kg de com www http https rechnung rechnungen vertrag vertraege info anlage
versicherung versicherungen versicherungsschein unterlagen einstellung anmeldung wartung foerderung
entschaedigung heizlast restforderung schadensregulierung schreiner energieausweis eg og
miete garage nk grundabgabe grundabgaben grdabg kieler karlstr karl gesetzlich
rentenversicherung abo theater garten finanzen karten ideen entwicklung agent multi vps led ki
ha ebus samen terrasse wallbox netzwerk smarthome lueftung kfz kfz-steuer steuer anhaenger
kaskadenschaltung beg zahnarzt hausarzt hautarzt schwindel ost west
'''.split())

SEGMENT = re.compile(r'[A-Za-zÄÖÜäöüß0-9]+')


def _nummernteil(seg):
    """'624', 'KV00100211610', 'SAL1T0065061', 'A1014' (-> '1014'); nicht
    'Kieler35' (Strasse mit Hausnummer) und nicht '1140Miete' (Betrag)."""
    m = re.fullmatch(r'([A-Za-zÄÖÜäöüß]*)(\d[A-Za-z0-9]*)', seg)
    if not m or re.search(r'[a-zäöüß]{3,}|[A-Za-z]{2,}$', m.group(2)):
        return None
    vor, rest = m.groups()
    if len(vor) <= 1:
        return rest
    if vor.isupper():
        return seg
    # 'Privathaftpflicht702213446': Wort direkt vor einer langen Nummer
    return rest if sum(c.isdigit() for c in rest) >= 5 else None


def nummern_im_namen(name):
    """Nummern mit mind. 5 Ziffern aus dem Ordnernamen, laengste zuerst.
    Teile werden verbunden, solange Nummernteile folgen; Grossbuchstaben
    dazwischen gehoeren dazu ('702_213446-Y-16', '1142801_GRDABG_3'),
    davor und danach nicht ('HDI_40-011840459-2' -> '40-011840459-2',
    '624_220429-P' -> '624_220429'). Fuehrende Ordnernummern ('07HUK') zaehlen nicht."""
    rein = re.sub(r'^\d{1,2}(?=[_\s.-]?[A-Za-zÄÖÜäöü])', '', name)
    laeufe, lauf = [], []
    for m in SEGMENT.finditer(rein):
        seg = m.group(0)
        teil = _nummernteil(seg)
        if teil is not None:
            start = m.end() - len(teil)
            lauf.append((start, m.end(), True))
        elif lauf and seg.isalpha() and seg.isupper() and len(seg) <= 6:
            lauf.append((m.start(), m.end(), False))
        else:
            laeufe.append(lauf)
            lauf = []
    laeufe.append(lauf)
    gefunden = []
    for lauf in laeufe:
        while lauf and not lauf[-1][2]:
            lauf.pop()
        if not lauf:
            continue
        z = rein[lauf[0][0]:lauf[-1][1]]
        if sum(c.isdigit() for c in z) >= 5 and z not in gefunden:
            gefunden.append(z)
    return sorted(gefunden, key=lambda z: -sum(c.isdigit() for c in z))


def woerter_im_namen(name):
    """'05TelekomHarald' -> ['telekom']; 'Huk-Coburg_BMW' -> ['huk', 'coburg', 'bmw']"""
    t = re.sub(r'([a-zäöü])([A-ZÄÖÜ])', r'\1 \2', name)
    teile = re.split(r'[^A-Za-zÄÖÜäöüß]+', t)
    aus = []
    for w in teile:
        f = regeln.falten(w)
        if len(f) >= 3 and f not in GENERISCH and f not in aus:
            aus.append(f)
    return aus


def _domain_passt(domain, name):
    """Der Domainname (ohne Endung, ohne Bindestriche) ist ein Wort des
    Ordnernamens oder mehrere aufeinanderfolgende: 'huk-coburg.de' passt zu
    'Huk-Coburg_BMW', 'smart-hosts.co' nicht zu 'SmartHome'."""
    label = re.sub(r'[^a-z0-9]', '', regeln.falten(domain.rsplit('.', 1)[0]))
    t = re.sub(r'([a-zäöü])([A-ZÄÖÜ])', r'\1 \2', name)
    w = [regeln.falten(x) for x in re.split(r'[^A-Za-zÄÖÜäöüß]+', t) if x]
    for i in range(len(w)):
        for j in range(i + 1, len(w) + 1):
            k = ''.join(w[i:j])
            if k == label and len(k) >= 4 and k not in GENERISCH:
                return True
    return False


def _domain(absender):
    a = email.utils.parseaddr(absender or '')[1].lower()
    return a.split('@', 1)[1] if '@' in a else ''


def _basis(domain):
    """'rechnungsstelle.ionos.de' -> 'ionos.de', 'mail.huk-coburg.de' -> 'huk-coburg.de'"""
    teile = domain.split('.')
    return '.'.join(teile[-2:]) if len(teile) >= 2 else domain


def _person(thema, uo):
    pfad = regeln.falten(thema + '/' + uo)
    if 'uschi' in pfad:
        return ['uschi']
    if 'samantha' in pfad:
        return ['samantha']
    return []


def _name(thema, uo):
    n = re.sub(r'[^a-z0-9]+', '-', regeln.falten(uo.split('/')[-1] or thema)).strip('-')
    return n or thema


def personennamen(wurzel):
    """Person -> Namen, unter denen sie in Mails steht (personen.yaml: name, namen)."""
    import os
    import yaml
    pfad = os.path.join(wurzel, 'config', 'personen.yaml')
    if not os.path.exists(pfad):
        return {}
    with open(pfad, encoding='utf-8') as fh:
        p = (yaml.safe_load(fh) or {}).get('personen') or {}
    return {k: [str(x) for x in [(v or {}).get('name', k)] + list((v or {}).get('namen') or [])]
            for k, v in p.items()}


def vorschlaege(wurzel):
    """Regelvorschlaege aus Ordnerliste und Bestand. Liefert (vorschlaege, ohne)."""
    bestand = daten.bestand(wurzel)
    namen_der_personen = personennamen(wurzel)
    domains = collections.Counter(_basis(_domain(e.get('absender'))) for e in bestand)
    domains.pop('', None)
    liste, ohne = [], []
    namen = set()
    for thema, ordner in daten.ordnerliste(wurzel).items():
        for uo in ordner:
            letzter = uo.split('/')[-1]
            nums = nummern_im_namen(letzter)
            woerter = woerter_im_namen(letzter)
            if nums:
                wenn = [{'teil': 'ueberall', 'vergleich': 'nummer', 'werte': [nums[0]]}]
                grund = 'Nummer %s aus dem Ordnernamen' % nums[0]
            else:
                treffer = sorted((d for d in domains if _domain_passt(d, letzter)),
                                 key=lambda d: -domains[d])
                if not treffer:
                    ohne.append('%s/%s' % (thema, uo))
                    continue
                wenn = [{'teil': 'absender', 'vergleich': 'wort', 'werte': treffer[:3]}]
                grund = 'Absender %s (%d Mails) passt zum Ordnernamen' % (
                    ', '.join(treffer[:3]), sum(domains[d] for d in treffer[:3]))
            name = _name(thema, uo)
            i = 2
            while name in namen:
                name, i = '%s-%d' % (_name(thema, uo), i), i + 1
            namen.add(name)
            dann = {'thema': thema, 'unterordner': uo}
            if _person(thema, uo):
                dann['personen'] = _person(thema, uo)
            liste.append({'name': name, 'art': 'ordner', 'wenn': wenn, 'dann': dann,
                          'grund': grund, 'herkunft': 'bestand', '_woerter': woerter})
    _nachschaerfen(liste, namen_der_personen)
    for a in liste:
        gleich = [b['name'] for b in liste if b is not a and regeln.regel_trifft(a, _probe(b)) is not None]
        if gleich:
            a['ueberschneidung'] = gleich
            a['grund'] += '; passt auch auf den Ordner von %s, bitte nachschärfen' % ', '.join(gleich)
    rw = {'regeln': [{k: v[k] for k in ('name', 'art', 'wenn', 'dann')} for v in liste]}
    from .einordnen import bestand_pruefung
    for v in liste:
        v.pop('_woerter', None)
        regel = {k: v[k] for k in ('name', 'art', 'wenn', 'dann')}
        v.update(bestand_pruefung(regel, rw, bestand))
    return liste, ohne


def _probe(v):
    """Ein kuenstlicher Eingang, der genau zu diesem Ordner gehoert: Ordnername
    und die Werte seiner Bedingungen (fuer den Vergleich der Vorschlaege untereinander)."""
    werte = ' '.join(w for b in v['wenn'] for w in b['werte'])
    return regeln.Teile(absender='x@' + (v['wenn'][0]['werte'][0] if v['wenn'][0]['teil'] == 'absender' else 'x.de'),
                        betreff=v['dann']['unterordner'].split('/')[-1] + ' ' + werte)


def _nachschaerfen(liste, personennamen=None):
    """Vorschlaege, die sich gegenseitig ueberdecken, bekommen ein eigenes Wort
    aus dem Ordnernamen als weitere Bedingung; gehoeren die Ordner zu
    verschiedenen Personen, den Namen der Person ('Guten Tag Samantha ...')."""
    personennamen = personennamen or {}
    for _ in range(2):
        for a in liste:
            for b in liste:
                if a is b or regeln.regel_trifft(a, _probe(b)) is None:
                    continue
                eigene = [w for w in a['_woerter'] if w not in b['_woerter']
                          and not any(w in regeln.falten(x) for x in a['wenn'][0]['werte'])]
                pa, pb = a['dann'].get('personen') or [], b['dann'].get('personen') or []
                if eigene:
                    werte, warum = [eigene[0]], '„%s“' % eigene[0]
                elif pa and pa != pb and pa[0] in personennamen:
                    werte = personennamen[pa[0]]
                    warum = 'dem Namen %s' % ' oder '.join(werte)
                else:
                    continue
                if any(c.get('werte') == werte for c in a['wenn']):
                    continue
                a['wenn'].append({'teil': 'ueberall', 'vergleich': 'wort', 'werte': werte})
                a['grund'] += '; nachgeschärft mit %s (sonst gleich wie %s)' % (warum, b['name'])


def schreiben(wurzel):
    """regeln/mail-vorschlaege.json: Vorschlaege aus dem Neuaufbau; laufende
    Vorschlaege und abgelehnte bleiben erhalten."""
    import json
    import os
    pfad = os.path.join(wurzel, 'regeln', 'mail-vorschlaege.json')
    alt = {}
    if os.path.exists(pfad):
        with open(pfad, encoding='utf-8') as fh:
            alt = json.load(fh)
    neu, ohne = vorschlaege(wurzel)
    abgelehnt = set(alt.get('abgelehnt') or [])
    neu = [v for v in neu if v['name'] not in abgelehnt]
    namen = {v['name'] for v in neu}
    rest = [v for v in alt.get('vorschlaege') or [] if v.get('herkunft') != 'bestand'
            and v.get('name') not in namen]
    with open(pfad, 'w', encoding='utf-8') as fh:
        json.dump({'abgelehnt': sorted(abgelehnt), 'vorschlaege': neu + rest}, fh,
                  ensure_ascii=False, indent=2)
        fh.write('\n')
    return neu, ohne
