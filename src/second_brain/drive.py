"""Mail-Anhaenge in die freigegebenen Google-Drive-Ordner legen.

Der Abruf speichert Anhaenge lokal unter <anhaenge>/<notiz-id>/ und traegt
ihre Namen als `anhaenge` in die Notiz ein. Dieses Modul bringt sie an den
Ort, den die Notiz beschreibt:

- Notiz mit `ablage` (z. B. 0-2026/01Gebäude/atu): in den Drive-Ordner des
  Themas (ID aus config/themen.yaml, Schluessel = Jahresordner) und darin in
  den Unterordner.
- Eingang oder Thema ohne Drive-ID: in einen Sammelordner im Drive des
  Agentenkontos, bis die Mail eingeordnet ist.

Wo die Dateien gerade liegen, steht als `drive` in der Notiz ("<ordner-id>:
<pfad>", leere ID = Wurzel des Agentenkontos). Weicht das vom Ziel ab, weil die
Mail im Eingang eingeordnet oder in der Web-App korrigiert wurde, verschiebt der
naechste Lauf die Dateien. Hochgeladen wird mit rclone; der Remote heisst
`drive` und wird ueber RCLONE_CONFIG_DRIVE_* im Workflow konfiguriert.
"""

import os
import subprocess

import yaml

from . import notiz as nz

SAMMELORDNER = 'Second Brain Eingang'


class DriveFehler(Exception):
    pass


def _rclone(*args):
    subprocess.run(['rclone', *args], check=True)


def dateiname(meta, name):
    """Datum voran, damit gleichnamige Anhaenge verschiedener Mails nicht kollidieren."""
    return '%s %s' % (meta.get('erstellt'), os.path.basename(name))


def remote(ort, name=''):
    """rclone-Pfad zu einem Ort "<ordner-id>:<pfad>", optional mit Dateiname."""
    ordner, _, pfad = ort.partition(':')
    pfad = '/'.join(t for t in (pfad, name) if t)
    return ('drive,root_folder_id=%s:%s' % (ordner, pfad)) if ordner else 'drive:' + pfad


def ziel(meta, themen):
    """Soll-Ort der Anhaenge einer Notiz als "<ordner-id>:<pfad>"."""
    thema = themen.get((meta.get('themen') or [None])[0]) or {}
    teile = str(meta.get('ablage') or '').split('/')
    ids = thema.get('drive') or {}
    if len(teile) >= 2 and teile[1] == thema.get('ablage') and ids.get(teile[0]):
        return '%s:%s' % (ids[teile[0]], '/'.join(teile[2:]))
    return ':%s/%s' % (SAMMELORDNER, meta['id'])


def abgleichen(wurzel, anhaenge=None, rclone=_rclone):
    """Neue Anhaenge hochladen und verschobene Notizen nachziehen. Liefert (hoch, verschoben)."""
    with open(os.path.join(wurzel, 'config', 'themen.yaml'), encoding='utf-8') as fh:
        themen = (yaml.safe_load(fh) or {}).get('themen', {})
    hoch = verschoben = 0
    fehler = []
    for basis in ('notizen', 'eingang'):
        for verz, _, dateien in os.walk(os.path.join(wurzel, basis)):
            for d in sorted(dateien):
                if not d.endswith('.md') or d == 'README.md':
                    continue
                pfad = os.path.join(verz, d)
                with open(pfad, encoding='utf-8') as fh:
                    try:
                        n = nz.lesen(fh.read())
                    except nz.FormatFehler:
                        continue
                namen = n.meta.get('anhaenge') or []
                if not namen:
                    continue
                soll, ist = ziel(n.meta, themen), n.meta.get('drive')
                if ist == soll:
                    continue
                try:
                    if ist is None:
                        lokal = os.path.join(anhaenge or '', n.meta['id'])
                        if not (anhaenge and os.path.isdir(lokal)):
                            continue
                        for name in namen:
                            rclone('copyto', os.path.join(lokal, os.path.basename(name)),
                                   remote(soll, dateiname(n.meta, name)))
                        hoch += 1
                    else:
                        for name in namen:
                            rclone('moveto', remote(ist, dateiname(n.meta, name)),
                                   remote(soll, dateiname(n.meta, name)))
                        if ist.startswith(':%s/' % SAMMELORDNER):
                            rclone('rmdir', remote(ist))
                        verschoben += 1
                except subprocess.CalledProcessError as e:
                    fehler.append('%s: %s' % (n.meta['id'], e))
                    continue
                n.meta['drive'] = soll
                with open(pfad, 'w', encoding='utf-8') as fh:
                    fh.write(nz.schreiben(n))
    if fehler:
        raise DriveFehler('%d Notizen nicht abgeglichen:\n%s' % (len(fehler), '\n'.join(fehler)))
    return hoch, verschoben
