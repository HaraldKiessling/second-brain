"""Zugriff auf ein Daten-Repo (Aufbau siehe beispiel-daten/)."""

import json
import os

import yaml

from . import notiz as nz


def _yaml(pfad):
    with open(pfad, encoding='utf-8') as fh:
        return yaml.safe_load(fh) or {}


def kontext(wurzel):
    """Bekannte Personen und Themen aus config/personen.yaml und config/themen.yaml."""
    personen = _yaml(os.path.join(wurzel, 'config', 'personen.yaml'))
    themen = _yaml(os.path.join(wurzel, 'config', 'themen.yaml'))
    return nz.Kontext(personen=set(personen.get('personen', {})),
                      themen=set(themen.get('themen', {})))


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
                            ablagewissen(wurzel))


def regelwerk(wurzel, quelle='mail'):
    with open(os.path.join(wurzel, 'regeln', quelle + '.json'), encoding='utf-8') as fh:
        return json.load(fh)


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
    for k in ('schwelle', 'vorschlag_ab', 'spam_schwelle'):
        if not isinstance(e[k], (int, float)) or not 0 <= e[k] <= 1:
            fehler.append(('config/einordnen.yaml', '%s muss zwischen 0 und 1 liegen' % k))
    if e['ki']['aktiv'] and not e['ki']['modell']:
        fehler.append(('config/einordnen.yaml', 'ki.modell fehlt'))
    return fehler
