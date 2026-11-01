"""Zugriff auf ein Daten-Repo (Aufbau siehe beispiel-daten/)."""

import json
import os

import yaml

from . import notiz as nz


def _yaml(pfad):
    with open(pfad, encoding='utf-8') as fh:
        return yaml.safe_load(fh) or {}


def _optional(wurzel, name):
    pfad = os.path.join(wurzel, 'config', name)
    return _yaml(pfad) if os.path.exists(pfad) else {}


def kontext(wurzel):
    """Bekannte Personen, Themen, Objekte und Steuerbezuege aus config/."""
    personen = _yaml(os.path.join(wurzel, 'config', 'personen.yaml'))
    themen = _yaml(os.path.join(wurzel, 'config', 'themen.yaml'))
    b = bezuege(wurzel)
    return nz.Kontext(personen=set(personen.get('personen', {})),
                      themen=set(themen.get('themen', {})),
                      objekte=set(b['objekte']), steuer=set(b['steuer']))


def bezuege(wurzel):
    """Objekte und Steuerbezuege aus config/bezuege.yaml (optional)."""
    d = _optional(wurzel, 'bezuege.yaml')
    return {'objekte': d.get('objekte') or {}, 'steuer': d.get('steuer') or {}}


def vertraege(wurzel):
    """Bekannte Vertraege aus config/vertraege.yaml (optional)."""
    return _optional(wurzel, 'vertraege.yaml').get('vertraege') or []


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


def ablagewissen(wurzel):
    """Bekannte Gegenparteien aus config/ablagewissen.yaml (optional)."""
    pfad = os.path.join(wurzel, 'config', 'ablagewissen.yaml')
    return _yaml(pfad).get('eintraege', []) if os.path.exists(pfad) else []


def lerner(wurzel, quelle='mail'):
    from . import einordnen
    th = themen(wurzel)
    return einordnen.Lerner(einordnen.beispiele_aus_notizen(notiz_pfade(wurzel), th), th,
                            regelwerk(wurzel, quelle).get('standard_personen', []),
                            ablagewissen(wurzel), einstellungen(wurzel)['eigene_adressen'],
                            bekannte_unterordner(wurzel))


def bekannte_unterordner(wurzel):
    """Thema -> Unterordner, die es schon gibt (Notizen und Ablagewissen)."""
    from . import einordnen
    th = themen(wurzel)
    bekannt = {}
    for b in einordnen.beispiele_aus_notizen(notiz_pfade(wurzel), th):
        if b.unterordner:
            bekannt.setdefault(b.thema, set()).add(b.unterordner)
    for w in ablagewissen(wurzel):
        if w.get('unterordner'):
            bekannt.setdefault(w['thema'], set()).add(w['unterordner'])
    for t, liste in ordnerliste(wurzel).items():
        bekannt.setdefault(t, set()).update(liste)
    for v in vertraege(wurzel):
        if v.get('unterordner'):
            bekannt.setdefault(v.get('thema'), set()).add(str(v['unterordner']))
    return bekannt


def regelvorschlaege_schreiben(wurzel, quelle='mail'):
    """regeln/<quelle>-vorschlaege.json neu berechnen; abgelehnte bleiben gemerkt."""
    from . import einordnen
    pfad = os.path.join(wurzel, 'regeln', quelle + '-vorschlaege.json')
    alt = {}
    if os.path.exists(pfad):
        with open(pfad, encoding='utf-8') as fh:
            alt = json.load(fh)
    th = themen(wurzel)
    neu = {'abgelehnt': alt.get('abgelehnt', []),
           'vorschlaege': einordnen.regelvorschlaege(
               einordnen.beispiele_aus_notizen(notiz_pfade(wurzel), th),
               regelwerk(wurzel, quelle), einstellungen(wurzel)['eigene_adressen'],
               alt.get('abgelehnt', []))}
    if neu != alt:
        with open(pfad, 'w', encoding='utf-8') as fh:
            json.dump(neu, fh, ensure_ascii=False, indent=2)
            fh.write('\n')
    return neu['vorschlaege']


def regelwerk(wurzel, quelle='mail'):
    with open(os.path.join(wurzel, 'regeln', quelle + '.json'), encoding='utf-8') as fh:
        return json.load(fh)


def _bezuege_pruefen(eintrag, ktx):
    fehler = []
    for feld, art, bekannt in (('weitere_themen', 'Thema', ktx.themen),
                               ('objekte', 'Objekt', ktx.objekte),
                               ('steuer', 'Steuerbezug', ktx.steuer)):
        for w in eintrag.get(feld) or []:
            if w not in bekannt:
                fehler.append('%s unbekannt: %s' % (art, w))
    return fehler


def notiz_pfade(wurzel):
    basis = os.path.join(wurzel, 'notizen')
    for verz, _, dateien in os.walk(basis):
        for d in sorted(dateien):
            if d.endswith('.md') and d != 'README.md':
                yield os.path.join(verz, d)


def pruefen(wurzel):
    """Notizen, Regelwerk und Einstellungen pruefen. Liefert Liste (pfad, meldung)."""
    from . import einordnen
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
        for r in regelwerk(wurzel).get('regeln', []):
            if r.get('thema') not in ktx.themen:
                fehler.append((rel, 'Regel %s: Thema unbekannt: %s'
                               % (r.get('name'), r.get('thema'))))
            for p in r.get('personen', []):
                if p not in ktx.personen:
                    fehler.append((rel, 'Regel %s: Person unbekannt: %s'
                                   % (r.get('name'), p)))
            if not einordnen.unterordner_gueltig(r.get('unterordner', '')):
                fehler.append((rel, 'Regel %s: Unterordner ungueltig: %s'
                               % (r.get('name'), r.get('unterordner'))))
            fehler.extend((rel, 'Regel %s: %s' % (r.get('name'), f))
                          for f in _bezuege_pruefen(r, ktx))

    for i, v in enumerate(vertraege(wurzel), 1):
        rel = 'config/vertraege.yaml'
        if not v.get('nummer'):
            fehler.append((rel, 'Vertrag %d: nummer fehlt' % i))
        elif einordnen._nummer_muster(v['nummer']) is None:
            fehler.append((rel, 'Vertrag %d: nummer zu kurz (mind. 5 Zeichen)' % i))
        if v.get('thema') not in ktx.themen:
            fehler.append((rel, 'Vertrag %d: Thema unbekannt: %s' % (i, v.get('thema'))))
        if not einordnen.unterordner_gueltig(str(v.get('unterordner') or '')):
            fehler.append((rel, 'Vertrag %d: Unterordner ungueltig' % i))
        for p in v.get('personen') or []:
            if p not in ktx.personen:
                fehler.append((rel, 'Vertrag %d: Person unbekannt: %s' % (i, p)))
        fehler.extend((rel, 'Vertrag %d: %s' % (i, f)) for f in _bezuege_pruefen(v, ktx))

    for i, w in enumerate(ablagewissen(wurzel), 1):
        rel = 'config/ablagewissen.yaml'
        if not w.get('muster'):
            fehler.append((rel, 'Eintrag %d: muster fehlt' % i))
        if w.get('thema') not in ktx.themen:
            fehler.append((rel, 'Eintrag %d: Thema unbekannt: %s' % (i, w.get('thema'))))
        for p in w.get('personen', []):
            if p not in ktx.personen:
                fehler.append((rel, 'Eintrag %d: Person unbekannt: %s' % (i, p)))
        if not einordnen.unterordner_gueltig(w.get('unterordner', '')):
            fehler.append((rel, 'Eintrag %d: Unterordner ungueltig' % i))

    e = einstellungen(wurzel)
    for k in ('schwelle', 'spam_schwelle'):
        if not isinstance(e[k], (int, float)) or not 0 <= e[k] <= 1:
            fehler.append(('config/einordnen.yaml', '%s muss zwischen 0 und 1 liegen' % k))
    if e['ki']['aktiv'] and not e['ki']['modell']:
        fehler.append(('config/einordnen.yaml', 'ki.modell fehlt'))
    return fehler
