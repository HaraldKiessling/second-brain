"""Notiz: Markdown-Datei mit YAML-Frontmatter.

Format siehe docs/notiz-format.md. Dieses Modul liest, schreibt und prueft
Notizen; es weiss nichts ueber Quellen oder Adapter.
"""

import datetime
import re
from dataclasses import dataclass, field

import yaml

PFLICHTFELDER = ('id', 'erstellt', 'quelle', 'personen', 'themen')
ID_MUSTER = re.compile(r'^[a-z0-9][a-z0-9-]*$')
EINGEORDNET_PRAEFIXE = ('regel/', 'ki/', 'manuell')


@dataclass
class Notiz:
    meta: dict
    text: str = ''
    pfad: str = ''

    @property
    def titel(self):
        for zeile in self.text.splitlines():
            if zeile.startswith('# '):
                return zeile[2:].strip()
        return ''


@dataclass
class Kontext:
    """Bekannte Personen und Themen aus dem Daten-Repo (config/)."""
    personen: set = field(default_factory=set)
    themen: set = field(default_factory=set)


class FormatFehler(ValueError):
    pass


def lesen(inhalt, pfad=''):
    """Notiz aus Dateiinhalt lesen. Wirft FormatFehler ohne Frontmatter."""
    if not inhalt.startswith('---\n'):
        raise FormatFehler('kein Frontmatter (Datei muss mit --- beginnen)')
    ende = inhalt.find('\n---', 4)
    if ende < 0:
        raise FormatFehler('Frontmatter nicht abgeschlossen')
    try:
        meta = yaml.safe_load(inhalt[4:ende]) or {}
    except yaml.YAMLError as exc:
        raise FormatFehler('Frontmatter ist kein gueltiges YAML: %s' % exc)
    if not isinstance(meta, dict):
        raise FormatFehler('Frontmatter muss eine Zuordnung sein')
    text = inhalt[ende + 4:].lstrip('\n')
    return Notiz(meta=meta, text=text, pfad=pfad)


def schreiben(notiz):
    """Notiz als Dateiinhalt (Frontmatter in fester Feldreihenfolge)."""
    reihenfolge = list(PFLICHTFELDER) + sorted(
        k for k in notiz.meta if k not in PFLICHTFELDER)
    meta = {k: notiz.meta[k] for k in reihenfolge if k in notiz.meta}
    kopf = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False,
                          default_flow_style=None).strip()
    return '---\n%s\n---\n\n%s' % (kopf, notiz.text.rstrip('\n') + '\n')


def pruefen(notiz, kontext):
    """Liste von Fehlermeldungen; leer = Notiz ist gueltig."""
    fehler = []
    m = notiz.meta
    for feld in PFLICHTFELDER:
        if feld not in m or m[feld] in (None, '', []):
            fehler.append('Pflichtfeld fehlt: %s' % feld)

    if 'id' in m and not ID_MUSTER.match(str(m['id'])):
        fehler.append('id nur aus a-z, 0-9 und - : %r' % m['id'])

    if 'erstellt' in m and not isinstance(m['erstellt'], datetime.date):
        fehler.append('erstellt muss ein Datum JJJJ-MM-TT sein')

    for feld, art, bekannt in (('personen', 'Person', kontext.personen),
                               ('themen', 'Thema', kontext.themen)):
        werte = m.get(feld)
        if werte is None:
            continue
        if not isinstance(werte, list):
            fehler.append('%s muss eine Liste sein' % feld)
            continue
        for w in werte:
            if bekannt and w not in bekannt:
                fehler.append('%s unbekannt: %s' % (art, w))

    durch = m.get('eingeordnet_durch')
    if durch is not None and not str(durch).startswith(EINGEORDNET_PRAEFIXE):
        fehler.append('eingeordnet_durch muss mit regel/, ki/ oder manuell beginnen')

    if not notiz.titel:
        fehler.append('Ueberschrift "# ..." fehlt')
    return fehler
