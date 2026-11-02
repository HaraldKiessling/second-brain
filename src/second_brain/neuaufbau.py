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

Dazu kommen die Kennungen aus den Dokumenten, die schon im Ordner liegen
(index/drive-kennungen.json, einmalig aus dem Drive gelesen, und der Text der
Anhaenge abgelegter Notizen, mit Texterkennung): Sie bestaetigen die Nummer
aus dem Ordnernamen, liefern die Schreibweise in den Briefen ('526-41384' zu
'526-041384', '702/213446-Y-63' zu '702_213446-Y-00') und, wenn der Ordnername
keine Nummer hat, die Nummer selbst ('Vertragsnummer 0906...' in drei
Dokumenten) oder die Domain der Gegenpartei.

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

from . import daten, kennungen, regeln

KENNUNGEN = 'index/drive-kennungen.json'

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


def _gruppen(w):
    """'526-041384' -> ['526', '41384']; Buchstaben bleiben eigene Gruppen."""
    return [g.lstrip('0') or '0' if g.isdigit() else g.upper()
            for g in re.findall(r'\d+|[A-Za-z]+', w)]


def variante(name_nummer, doc_nummer):
    """Ist doc_nummer dieselbe Nummer anders geschrieben (fuehrende Nullen) oder
    mit anderer Endung ('702_213446-Y-00' / '702/213446-Y-63')?"""
    a, b = _gruppen(name_nummer), _gruppen(doc_nummer)
    if a == b:
        return True
    if len(a) == len(b) and len(a) >= 3 and a[:-1] == b[:-1] and a[-1] == '0':
        # Platzhalter im Ordnernamen ('-Y-00'), im Brief die echte Endung
        return sum(len(g) for g in a[:-1] if g.isdigit()) >= 6
    # 'FitX_1054125-1039311' / 'Mitgliedsnr 76-1054125': die lange Nummer steckt im Dokument
    # (nur bei reinen Ziffernfolgen; '1142801_GRDABG_1' und '..._3' sind verschiedene Objekte)
    lang = [g for g in a if g.isdigit() and len(g) >= 7]
    return bool(lang) and all(g.isdigit() for g in a) and any(g in b for g in lang)


def _notiz_dokumente(wurzel):
    """Abgelegte Notizen als Dokumente ihres Ordners (Anhangtext und Mailtext)."""
    from . import mail
    from . import notiz as nz
    th = daten.themen(wurzel)
    from .einordnen import unterordner_aus_ablage
    for pfad in daten.notiz_pfade(wurzel):
        with open(pfad, encoding='utf-8') as fh:
            try:
                n = nz.lesen(fh.read())
            except nz.FormatFehler:
                continue
        m = n.meta
        if not m.get('themen') or not m.get('ablage'):
            continue
        thema = m['themen'][0]
        uo = unterordner_aus_ablage(m.get('ablage'), (th.get(thema) or {}).get('ablage', ''))
        if uo:
            yield {'ordner': '%s/%s' % (thema, uo), 'titel': n.titel,
                   'text': n.text + '\n' + mail.anhangtext_lesen(wurzel, m.get('id'))}


def ordner_kennungen(wurzel):
    """Ordner -> Kennungen: aus index/drive-kennungen.json und abgelegten Notizen."""
    import json
    import os
    aus = {}
    pfad = os.path.join(wurzel, KENNUNGEN)
    if os.path.exists(pfad):
        with open(pfad, encoding='utf-8') as fh:
            aus = (json.load(fh) or {}).get('ordner') or {}
    for o, e in kennungen.ordner_kennungen(list(_notiz_dokumente(wurzel))).items():
        ziel = aus.setdefault(o, {'dokumente': 0, 'nummern': [], 'domains': []})
        ziel['dokumente'] += e['dokumente']
        for feld in ('nummern', 'domains'):
            schon = {kennungen.normal(x['wert']): x for x in ziel[feld]}
            for x in e[feld]:
                y = schon.get(kennungen.normal(x['wert']))
                if y:
                    y['dokumente'] += x['dokumente']
                    y['beschriftet'] = y.get('beschriftet') or x.get('beschriftet')
                else:
                    ziel[feld].append(dict(x))
    return aus


def _dokumente(n):
    return '%d Dokument%s' % (n, '' if n == 1 else 'en')


def _starke(info):
    """Kennungen, die als Bedingung taugen: beschriftet und in mind. zwei
    Dokumenten, oder mit typischer Vertragsform ('602/718680-P') schon in einem."""
    return [x for x in info.get('nummern') or []
            if x.get('beschriftet') and x['dokumente'] >= 2
            or kennungen.VERTRAG.search(x['wert']) and (x.get('beschriftet') or x['dokumente'] >= 2
                                                       or not re.match(r'[A-Z]\d{9}$', x['wert']))]


def _aus_nummer_im_namen(nummer, info):
    werte = [nummer]
    alle = info.get('nummern') or []
    bestaetigt = [x for x in alle if kennungen.normal(x['wert']) == kennungen.normal(nummer)]
    for x in alle:
        if x in bestaetigt or not variante(nummer, x['wert']):
            continue
        if kennungen.normal(x['wert']) not in {kennungen.normal(w) for w in werte}:
            werte.append(x['wert'])
    grund = 'Nummer %s aus dem Ordnernamen' % nummer
    if bestaetigt:
        grund += ', steht in %s im Ordner' % _dokumente(bestaetigt[0]['dokumente'])
    if len(werte) > 1:
        grund += '; in den Dokumenten geschrieben als %s' % ', '.join(werte[1:])
    return werte, grund


def _aus_dokumenten(info, letzter):
    """Bedingung aus den Dokumenten, wenn der Ordnername keine Nummer hat."""
    starke = _starke(info)
    if starke:
        werte = [x['wert'] for x in starke[:3]]
        n = max(x['dokumente'] for x in starke[:3])
        return ([{'teil': 'ueberall', 'vergleich': 'nummer', 'werte': werte}],
                'Nummer %s steht in %d von %s im Ordner (nicht im Ordnernamen)'
                % (' oder '.join(werte), n, _dokumente(info.get('dokumente', 0))))
    doms = [x for x in info.get('domains') or [] if _domain_passt(x['wert'], letzter)
            or (x['dokumente'] >= 2 and x['dokumente'] * 2 >= info.get('dokumente', 0))]
    if doms:
        werte = [x['wert'] for x in doms[:2]]
        return ([{'teil': 'ueberall', 'vergleich': 'wort', 'werte': werte}],
                'Gegenpartei %s steht in %d von %s im Ordner'
                % (', '.join(werte), doms[0]['dokumente'], _dokumente(info.get('dokumente', 0))))
    return None, None


def vorschlaege(wurzel):
    """Regelvorschlaege aus Ordnerliste, Ordnerinhalten und Bestand. Liefert (vorschlaege, ohne)."""
    bestand = daten.bestand(wurzel)
    inhalte = ordner_kennungen(wurzel)
    namen_der_personen = personennamen(wurzel)
    domains = collections.Counter(_basis(_domain(e.get('absender'))) for e in bestand)
    domains.pop('', None)
    liste, ohne = [], []
    namen = set()
    domain_ordner = collections.Counter(
        d for ordner in daten.ordnerliste(wurzel).values() for uo in ordner
        for d in domains if _domain_passt(d, uo.split('/')[-1]))
    for thema, ordner in daten.ordnerliste(wurzel).items():
        for uo in ordner:
            letzter = uo.split('/')[-1]
            nums = nummern_im_namen(letzter)
            woerter = woerter_im_namen(letzter)
            info = inhalte.get('%s/%s' % (thema, uo)) or {}
            treffer = sorted((d for d in domains if _domain_passt(d, letzter)),
                             key=lambda d: -domains[d])
            if nums:
                werte, grund = _aus_nummer_im_namen(nums[0], info)
                wenn = [{'teil': 'ueberall', 'vergleich': 'nummer', 'werte': werte}]
            elif treffer and (not _starke(info) or domain_ordner[treffer[0]] == 1):
                # eine Absender-Domain, die nur zu diesem Ordner passt, reicht;
                # teilen sich Ordner die Domain (huk-coburg.de), entscheidet die Nummer
                wenn = [{'teil': 'absender', 'vergleich': 'wort', 'werte': treffer[:3]}]
                grund = 'Absender %s (%d Mails) passt zum Ordnernamen' % (
                    ', '.join(treffer[:3]), sum(domains[d] for d in treffer[:3]))
            else:
                wenn, grund = _aus_dokumenten(info, letzter)
                if not wenn:
                    ohne.append('%s/%s' % (thema, uo))
                    continue
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
    vorkommen = _vorkommen(wurzel)
    for a in liste:
        ziel = '%s/%s' % (a['dann']['thema'], a['dann']['unterordner'])
        fremd = {}
        for w in a['wenn'][0]['werte']:
            for o, n in (vorkommen.get(kennungen.normal(w)) or {}).items():
                if o != ziel:
                    fremd[o] = max(fremd.get(o, 0), n)
        if fremd and len(a['wenn']) == 1:
            a['grund'] += '; %s steht auch in Dokumenten von %s, bitte nachschärfen' % (
                ' / '.join(a['wenn'][0]['werte']),
                ', '.join('%s (%s)' % (o, _dokumente(n)) for o, n in sorted(fremd.items())))
            a['ueberschneidung'] = sorted(fremd)
    for a in liste:
        gleich = [b['name'] for b in liste if b is not a and regeln.regel_trifft(a, _probe(b)) is not None]
        if gleich:
            a['ueberschneidung'] = sorted(set(a.get('ueberschneidung') or []) | set(gleich))
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
                    # Wortteil: 'wohngebaeude' steckt in 'Wohngebäudeversicherung'
                    werte, warum, vgl = [eigene[0]], '„%s“' % eigene[0], 'wortteil'
                elif pa and pa != pb and pa[0] in personennamen:
                    werte, vgl = personennamen[pa[0]], 'wort'
                    warum = 'dem Namen %s' % ' oder '.join(werte)
                else:
                    continue
                if any(c.get('werte') == werte for c in a['wenn']):
                    continue
                a['wenn'].append({'teil': 'ueberall', 'vergleich': vgl, 'werte': werte})
                a['grund'] += '; nachgeschärft mit %s (sonst gleich wie %s)' % (warum, b['name'])


def _vorkommen(wurzel):
    import json
    import os
    pfad = os.path.join(wurzel, KENNUNGEN)
    if not os.path.exists(pfad):
        return {}
    with open(pfad, encoding='utf-8') as fh:
        return (json.load(fh) or {}).get('vorkommen') or {}


def vorkommen(dokumente, werte):
    """Fuer jede Nummer (aus Ordnernamen und Kennungen): in welchen Ordnern sie
    in wie vielen Dokumenten steht. Damit sieht der Neuaufbau, wenn die Nummer
    eines Ordners auch in Dokumenten eines anderen Ordners steht."""
    texte = [(d['ordner'], regeln.falten(d.get('titel', '') + '\n' + d.get('text', '')))
             for d in dokumente if not kennungen.GEHEIM.search(d.get('text', '') + ' ' + d.get('titel', ''))]
    aus = {}
    for w in sorted(set(werte)):
        m = regeln.nummer_muster(w)
        if m is None:
            continue
        c = collections.Counter(o for o, t in texte if m.search(t))
        if c:
            aus[kennungen.normal(w)] = dict(sorted(c.items()))
    return aus


def kennungen_schreiben(wurzel, dokumente, quelle):
    """index/drive-kennungen.json aus gelesenen Dokumenten [{ordner, titel, text}]
    (nur das Ergebnis, kein Dokumenttext)."""
    import datetime
    import json
    import os
    erg = kennungen.ordner_kennungen(dokumente)
    werte = [x['wert'] for e in erg.values() for x in e['nummern']]
    for ordner in daten.ordnerliste(wurzel).values():
        for uo in ordner:
            werte += nummern_im_namen(uo.split('/')[-1])
    pfad = os.path.join(wurzel, KENNUNGEN)
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    with open(pfad, 'w', encoding='utf-8') as fh:
        json.dump({'stand': datetime.date.today().isoformat(), 'quelle': quelle,
                   'ordner': erg, 'vorkommen': vorkommen(dokumente, werte)},
                  fh, ensure_ascii=False, indent=1)
        fh.write('\n')
    return erg


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
