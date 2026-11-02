"""Steuerposten und Steueruebersicht (ADR 0004).

Ein Steuerposten ist Person · Anlage · Objekt · Posten, z. B.
"harald.v.kieler37.schuldzinsen" = Harald, Anlage V, Kieler 37, Schuldzinsen.
Die Liste steht in config/steuerposten.yaml und entstand aus den
Steuererklaerungen 2024/2025; neue Posten schlaegt die KI vor
(vorschlaege), sie gelten erst, wenn Harald sie uebernimmt.

Woher eine Notiz ihre Posten bekommt:
  - fest aus dem Ordner (steuerposten.yaml: ordner, "thema/unterordner" oder
    nur "thema"; der laengste passende Eintrag gilt, Unterebenen erben)
  - aus Regeln (dann.steuer), auch Merkmalregeln fuer inhaltliche Faelle
  - von Harald in der Web-App

Das Steuerjahr ist das Zugehoerigkeitsjahr (Feld jahr, sonst erstellt).
uebersicht() fasst je Jahr und Person nach Anlage und Posten zusammen, mit
Summe, Belegen und fehlenden Belegen (Posten mit Beleg im Vorjahr, aber
keinem in diesem Jahr). csv() ist dieselbe Liste fuer WISO.
"""

import csv as csvmod
import datetime
import io
import json
import os
import re

from . import notiz as nz

ANLAGEN = {
    'N': 'Anlage N (Arbeitnehmer)',
    'V': 'Anlage V (Vermietung)',
    'KAP': 'Anlage KAP (Kapitalerträge)',
    'R': 'Anlage R (Renten)',
    'SA': 'Sonderausgaben',
    'VOR': 'Vorsorgeaufwand',
    'AB': 'Außergewöhnliche Belastungen',
    '35a': 'Haushaltsnahe Dienstleistungen, Handwerker (§35a)',
    'USt': 'Umsatzsteuer (Solaranlage)',
    'EÜR': 'Gewinnermittlung (Solaranlage)',
}


def posten_laden(cfg):
    """{schluessel: {person, anlage, objekt, posten, name}} mit Anzeigenamen."""
    alle = {}
    for k, p in ((cfg or {}).get('posten') or {}).items():
        p = dict(p or {})
        p.setdefault('name', ' · '.join(str(x) for x in (
            p.get('person', ''), p.get('anlage', ''), p.get('objekt', ''), p.get('posten', '')) if x))
        alle[str(k)] = p
    return alle


def ordner_posten(cfg, thema, unterordner=''):
    """Fester Steuerbezug des Ordners: laengster passender Eintrag in cfg['ordner']."""
    zuordnung = (cfg or {}).get('ordner') or {}
    pfad = '/'.join(t for t in [thema] + str(unterordner or '').strip('/').split('/') if t)
    teile = pfad.split('/')
    for n in range(len(teile), 0, -1):
        k = '/'.join(teile[:n])
        if k in zuordnung:
            return list(zuordnung[k] or [])
    return []


def _jahr(meta):
    """Steuerjahr = Zugehoerigkeitsjahr: jahr, sonst Jahr der Zahlung, sonst erstellt."""
    j = meta.get('jahr')
    if isinstance(j, int):
        return j
    z = meta.get('zahlung')
    if hasattr(z, 'year'):
        return z.year
    e = meta.get('erstellt')
    return getattr(e, 'year', None) or (int(str(e)[:4]) if str(e)[:4].isdigit() else None)


def belege(wurzel):
    """Alle Notizen mit Steuerbezug: [(meta, titel, pfad)]."""
    from . import daten
    for pfad in daten.notiz_pfade(wurzel):
        with open(pfad, encoding='utf-8') as fh:
            try:
                n = nz.lesen(fh.read())
            except nz.FormatFehler:
                continue
        if n.meta.get('steuer'):
            yield n.meta, n.titel, os.path.relpath(pfad, wurzel)


def _link(meta):
    if meta.get('original'):
        return str(meta['original'])
    dateien = meta.get('dateien') or {}
    if isinstance(dateien, dict) and dateien:
        return 'https://drive.google.com/file/d/%s' % next(iter(dateien.values()))
    if meta.get('mail_pdf_id'):
        return 'https://drive.google.com/file/d/%s' % meta['mail_pdf_id']
    return ''


def uebersicht(wurzel, posten, jahre=None):
    """{jahr: {person: {anlage: {posten_schluessel: {name, summe, belege: [...]}}}},
    plus 'fehlend': {jahr: {person: [posten_schluessel]}}}."""
    daten = {}
    for meta, titel, pfad in belege(wurzel):
        j = _jahr(meta)
        if j is None or (jahre and j not in jahre):
            continue
        for k in meta.get('steuer') or []:
            p = posten.get(k) or {'person': '?', 'anlage': '?', 'name': k + ' (unbekannt)'}
            person, anlage = str(p.get('person') or '?'), str(p.get('anlage') or '?')
            eintrag = (daten.setdefault(j, {}).setdefault(person, {}).setdefault(anlage, {})
                       .setdefault(k, {'name': p.get('name', k), 'summe': 0.0, 'belege': []}))
            b = meta.get('betrag')
            beleg = {'id': meta.get('id'), 'titel': titel, 'pfad': pfad,
                     'datum': str(meta.get('zahlung') or meta.get('erstellt') or ''),
                     'betrag': b if isinstance(b, (int, float)) else None,
                     'lohnanteil': meta.get('lohnanteil'), 'link': _link(meta),
                     'ablage': meta.get('ablage', '')}
            eintrag['belege'].append(beleg)
            if isinstance(b, (int, float)):
                eintrag['summe'] = round(eintrag['summe'] + b, 2)
    for j in daten.values():
        for person in j.values():
            for anlage in person.values():
                for e in anlage.values():
                    e['belege'].sort(key=lambda b: b['datum'])
    fehlend = {}
    for j in sorted(daten):
        vorjahr = daten.get(j - 1, {})
        for person, anlagen in vorjahr.items():
            vorher = {k for a in anlagen.values() for k in a}
            jetzt = {k for a in daten[j].get(person, {}).values() for k in a}
            offen = sorted(vorher - jetzt)
            if offen:
                fehlend.setdefault(j, {})[person] = offen
    return {'jahre': daten, 'fehlend': fehlend}


def csv(ueb, jahr, posten):
    """CSV (Semikolon, deutsches Zahlenformat) fuer WISO: eine Zeile je Beleg."""
    out = io.StringIO()
    w = csvmod.writer(out, delimiter=';')
    w.writerow(['Jahr', 'Person', 'Anlage', 'Objekt', 'Posten', 'Datum', 'Betrag',
                'Lohnanteil', 'Beleg', 'Link'])
    fmt = lambda x: ('%.2f' % x).replace('.', ',') if isinstance(x, (int, float)) else ''
    for person, anlagen in sorted((ueb['jahre'].get(jahr) or {}).items()):
        for anlage, eintraege in sorted(anlagen.items()):
            for k, e in sorted(eintraege.items()):
                p = posten.get(k, {})
                for b in e['belege']:
                    w.writerow([jahr, person, anlage, p.get('objekt', ''), p.get('posten', k),
                                b['datum'], fmt(b['betrag']), fmt(b['lohnanteil']),
                                b['titel'], b['link']])
    return out.getvalue()


def schreiben(wurzel, posten, heute=None):
    """steuer/<jahr>.json und steuer/<jahr>.csv fuer die Web-App neu schreiben.
    Liefert die Jahre."""
    heute = heute or datetime.date.today()
    ueb = uebersicht(wurzel, posten)
    ziel = os.path.join(wurzel, 'steuer')
    os.makedirs(ziel, exist_ok=True)
    for j in sorted(ueb['jahre']):
        inhalt = {'jahr': j, 'stand': heute.isoformat(), 'personen': ueb['jahre'][j],
                  'fehlend': ueb['fehlend'].get(j, {}),
                  'posten': {k: posten[k] for a in ueb['jahre'][j].values() for e in a.values()
                             for k in e if k in posten}}
        _schreibe(os.path.join(ziel, '%d.json' % j),
                  json.dumps(inhalt, ensure_ascii=False, indent=1, default=str) + '\n', heute)
        _schreibe(os.path.join(ziel, '%d.csv' % j), csv(ueb, j, posten), heute)
    return sorted(ueb['jahre'])


def _schreibe(pfad, text, heute):
    """Nur schreiben, wenn sich mehr als das Stand-Datum aendert (keine leeren Commits)."""
    if os.path.exists(pfad):
        with open(pfad, encoding='utf-8') as fh:
            alt = fh.read()
        if re.sub(r'"stand": "[^"]*"', '', alt) == re.sub(r'"stand": "[^"]*"', '', text):
            return
    with open(pfad, 'w', encoding='utf-8') as fh:
        fh.write(text)
