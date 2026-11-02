"""Zugriff auf ein Daten-Repo (Aufbau siehe beispiel-daten/)."""

import json
import os
import re

import yaml

from . import notiz as nz


def _yaml(pfad):
    with open(pfad, encoding='utf-8') as fh:
        return yaml.safe_load(fh) or {}


def _optional(wurzel, name):
    pfad = os.path.join(wurzel, 'config', name)
    return _yaml(pfad) if os.path.exists(pfad) else {}


def kontext(wurzel):
    """Bekannte Personen, Themen, Objekte und Steuerposten aus config/."""
    personen = _yaml(os.path.join(wurzel, 'config', 'personen.yaml'))
    themen = _yaml(os.path.join(wurzel, 'config', 'themen.yaml'))
    b = bezuege(wurzel)
    return nz.Kontext(personen=set(personen.get('personen', {})),
                      themen=set(themen.get('themen', {})),
                      objekte=set(b['objekte']), steuer=set(b['steuer']))


def bezuege(wurzel):
    """Objekte aus config/bezuege.yaml und Steuerposten aus config/steuerposten.yaml."""
    d = _optional(wurzel, 'bezuege.yaml')
    return {'objekte': d.get('objekte') or {}, 'steuer': steuerposten(wurzel)}


def steuer_config(wurzel):
    """config/steuerposten.yaml (posten, ordner, vorschlaege), optional."""
    return _optional(wurzel, 'steuerposten.yaml')


def steuerposten(wurzel):
    from . import steuer
    return steuer.posten_laden(steuer_config(wurzel))


def ordnerliste(wurzel):
    """Thema -> bekannte Unterordner aus config/ordner.yaml (optional)."""
    return {t: [str(u) for u in (liste or [])]
            for t, liste in (_optional(wurzel, 'ordner.yaml').get('ordner') or {}).items()}


def themen(wurzel):
    return _yaml(os.path.join(wurzel, 'config', 'themen.yaml')).get('themen', {})


def einstellungen(wurzel):
    """config/einordnen.yaml mit Standardwerten (Datei ist optional)."""
    from . import einordnen
    pfad = os.path.join(wurzel, 'config', 'einordnen.yaml')
    return einordnen.einstellungen(_yaml(pfad) if os.path.exists(pfad) else {})


def bekannte_unterordner(wurzel):
    """Thema -> Unterordner, die es schon gibt: die Ordnerliste (echter Drive-Baum)
    und Ordner, in die schon Notizen abgelegt wurden."""
    from . import einordnen
    th = themen(wurzel)
    bekannt = {}
    for b in einordnen.beispiele_aus_notizen(notiz_pfade(wurzel), th):
        if b.unterordner:
            bekannt.setdefault(b.thema, set()).add(b.unterordner)
    for t, liste in ordnerliste(wurzel).items():
        bekannt.setdefault(t, set()).update(str(x) for x in liste or [])
    return bekannt


def regelwerk(wurzel, quelle='mail'):
    """regeln/<quelle>.json; fehlt die Datei, ein leeres Regelwerk."""
    from . import regeln
    pfad = os.path.join(wurzel, 'regeln', quelle + '.json')
    if not os.path.exists(pfad):
        return regeln.leeres_regelwerk()
    with open(pfad, encoding='utf-8') as fh:
        return json.load(fh)


def notiz_pfade(wurzel):
    basis = os.path.join(wurzel, 'notizen')
    for verz, _, dateien in os.walk(basis):
        for d in sorted(dateien):
            if d.endswith('.md') and d != 'README.md':
                yield os.path.join(verz, d)


def _notizen_und_eingang(wurzel):
    for sub in ('notizen', 'eingang'):
        for verz, _, dateien in os.walk(os.path.join(wurzel, sub)):
            if '.status' in verz:
                continue
            for d in sorted(dateien):
                if d.endswith('.md') and d != 'README.md':
                    yield sub, os.path.join(verz, d)


# --- Bestand: alle bisherigen Eingaenge mit ihren Bestandteilen -------------

def bestand(wurzel):
    """Notizen, offene Eingaenge und Indexeintraege mit den Bestandteilen, die
    Regeln pruefen (regeln.TEILE), dazu id, datum und ziel (wo es heute liegt).
    Grundlage fuer Regelvorschlaege, Beispiele und Regelkonflikte."""
    from . import mail
    eintraege = []
    for sub, pfad in _notizen_und_eingang(wurzel):
        with open(pfad, encoding='utf-8') as fh:
            try:
                n = nz.lesen(fh.read())
            except nz.FormatFehler:
                continue
        m = n.meta
        rumpf = re.sub(r'^# .*\n+', '', n.text)
        rumpf = re.sub(r'(?m)^(Von|Datum|Anhänge): .*$', '', rumpf).strip()
        eintraege.append({
            'id': str(m.get('id') or ''), 'datum': str(m.get('erstellt') or ''),
            'ziel': str(m.get('ablage') or '') if sub == 'notizen' else 'Zu erledigen',
            'absender': str(m.get('absender') or ''), 'empfaenger': str(m.get('empfaenger') or ''),
            'betreff': n.titel, 'text': rumpf[:1500],
            'anhangname': ' '.join(str(a) for a in m.get('anhaenge') or []),
            'anhangtext': mail.anhangtext_lesen(wurzel, m.get('id'))[:3000]})
    verz = os.path.join(wurzel, 'index', 'mail')
    for d in sorted(os.listdir(verz)) if os.path.isdir(verz) else []:
        if not d.endswith('.jsonl'):
            continue
        with open(os.path.join(verz, d), encoding='utf-8') as fh:
            for zeile in fh:
                try:
                    z = json.loads(zeile)
                except ValueError:
                    continue
                eintraege.append({
                    'id': z.get('message_id') or '', 'datum': z.get('datum', ''),
                    'ziel': 'aussortiert' if z.get('verworfen') else 'nur gemerkt',
                    'absender': z.get('absender', ''), 'empfaenger': '',
                    'betreff': z.get('betreff', ''), 'text': z.get('kurz', ''),
                    'anhangname': '', 'anhangtext': ''})
    return eintraege


BESTAND_DATEI = os.path.join('index', 'bestand.jsonl')


def bestand_schreiben(wurzel):
    """index/bestand.jsonl fuer die Web-App (Beispiele und Regelkonflikte beim
    Anlegen einer Regel). Liefert die Zahl der Eintraege."""
    alle = bestand(wurzel)
    text = ''.join(json.dumps(e, ensure_ascii=False) + '\n' for e in alle)
    pfad = os.path.join(wurzel, BESTAND_DATEI)
    alt = ''
    if os.path.exists(pfad):
        with open(pfad, encoding='utf-8') as fh:
            alt = fh.read()
    if alt != text:
        os.makedirs(os.path.dirname(pfad), exist_ok=True)
        with open(pfad, 'w', encoding='utf-8') as fh:
            fh.write(text)
    return len(alle)


def regelvorschlaege_schreiben(wurzel, quelle='mail'):
    """regeln/<quelle>-vorschlaege.json aktualisieren.

    Vorschlaege aus dem Neuaufbau (herkunft: bestand) bleiben stehen, bis Harald
    sie uebernimmt oder ablehnt; laufende (herkunft: abgelegt, zweimal Gleiches
    abgelegt) werden neu berechnet. Beispiele und Regelkonflikte werden fuer
    alle gegen den aktuellen Bestand geprueft."""
    from . import einordnen
    pfad = os.path.join(wurzel, 'regeln', quelle + '-vorschlaege.json')
    alt = {}
    if os.path.exists(pfad):
        with open(pfad, encoding='utf-8') as fh:
            alt = json.load(fh)
    rw = regelwerk(wurzel, quelle)
    alle = bestand(wurzel)
    abgelehnt = alt.get('abgelehnt', [])
    namen = {r.get('name') for r in rw.get('regeln') or []}
    fest = []
    for v in alt.get('vorschlaege', []):
        if v.get('herkunft') == 'abgelegt' or v.get('name') in namen or v.get('name') in abgelehnt:
            continue
        regel = {k: v[k] for k in ('name', 'art', 'wenn', 'dann') if k in v}
        fest.append(dict(v, **einordnen.bestand_pruefung(regel, rw, alle)))
    belegt = {v['name'] for v in fest}
    laufend = einordnen.regelvorschlaege(
        einordnen.beispiele_aus_notizen(notiz_pfade(wurzel), themen(wurzel)), rw,
        einstellungen(wurzel)['eigene_adressen'], abgelehnt, bestand=alle)
    neu = {'abgelehnt': abgelehnt,
           'vorschlaege': fest + [v for v in laufend if v['name'] not in belegt]}
    if neu != alt:
        os.makedirs(os.path.dirname(pfad), exist_ok=True)
        with open(pfad, 'w', encoding='utf-8') as fh:
            json.dump(neu, fh, ensure_ascii=False, indent=2)
            fh.write('\n')
    return neu['vorschlaege']


# --- Pruefen ---------------------------------------------------------------

def pruefen(wurzel):
    """Notizen, Regelwerk, Steuerposten und Einstellungen pruefen.
    Liefert Liste (pfad, meldung)."""
    from . import regeln
    ktx = kontext(wurzel)
    fehler = []
    gesehen = {}
    for pfad in notiz_pfade(wurzel):
        rel = os.path.relpath(pfad, wurzel)
        with open(pfad, encoding='utf-8') as fh:
            inhalt = fh.read()
        try:
            n = nz.lesen(inhalt, rel)
        except nz.FormatFehler as exc:
            fehler.append((rel, str(exc)))
            continue
        fehler.extend((rel, f) for f in nz.pruefen(n, ktx))
        nid = n.meta.get('id')
        if nid in gesehen:
            fehler.append((rel, 'id doppelt, auch in %s' % gesehen[nid]))
        elif nid:
            gesehen[nid] = rel

    regel_pfad = os.path.join(wurzel, 'regeln', 'mail.json')
    if os.path.exists(regel_pfad):
        rel = os.path.relpath(regel_pfad, wurzel)
        rw = regelwerk(wurzel)
        if rw.get('version') != regeln.VERSION:
            fehler.append((rel, 'Regelwerk Version %s, erwartet %d (ADR 0004)'
                           % (rw.get('version'), regeln.VERSION)))
        for p in rw.get('standard_personen') or []:
            if p not in ktx.personen:
                fehler.append((rel, 'Standardperson unbekannt: %s' % p))
        namen = set()
        for r in rw.get('regeln', []):
            fehler.extend((rel, 'Regel %s: %s' % (r.get('name'), f)) for f in regeln.regel_fehler(
                r, ktx.themen, ktx.personen, ktx.objekte, ktx.steuer, namen))
            namen.add(r.get('name'))

    rel = 'config/steuerposten.yaml'
    for k, p in steuerposten(wurzel).items():
        if p.get('person') and p['person'] not in ktx.personen:
            fehler.append((rel, 'Posten %s: Person unbekannt: %s' % (k, p['person'])))
        if p.get('objekt') and ktx.objekte and p['objekt'] not in ktx.objekte:
            fehler.append((rel, 'Posten %s: Objekt unbekannt: %s' % (k, p['objekt'])))
    for k, liste in (steuer_config(wurzel).get('ordner') or {}).items():
        if str(k).split('/')[0] not in ktx.themen:
            fehler.append((rel, 'Ordner %s: Thema unbekannt' % k))
        for x in liste or []:
            if x not in ktx.steuer:
                fehler.append((rel, 'Ordner %s: Posten unbekannt: %s' % (k, x)))

    e = einstellungen(wurzel)
    for k in ('schwelle', 'spam_schwelle'):
        if not isinstance(e[k], (int, float)) or not 0 <= e[k] <= 1:
            fehler.append(('config/einordnen.yaml', '%s muss zwischen 0 und 1 liegen' % k))
    if e['ki']['aktiv'] and not e['ki']['modell']:
        fehler.append(('config/einordnen.yaml', 'ki.modell fehlt'))
    return fehler
