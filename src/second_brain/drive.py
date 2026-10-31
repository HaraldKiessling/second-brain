"""Mail-Anhaenge in die freigegebenen Google-Drive-Ordner legen.

Der Abruf speichert Anhaenge lokal unter <anhaenge>/<notiz-id>/ und traegt
ihre Namen als `anhaenge` in die Notiz ein. Dieses Modul bringt sie an den
Ort, den die Notiz beschreibt:

- Notiz mit `ablage` (z. B. 0-2026/01Gebäude/atu): in den Drive-Ordner des
  Themas (ID aus config/themen.yaml, Schluessel = Jahresordner) und darin in
  den Unterordner.
- Eingang oder Thema ohne Drive-ID: in einen Sammelordner im Drive des
  Agentenkontos, bis die Mail eingeordnet ist.

Ist `mail_drive` gesetzt (Web-App: "Mail als PDF in Drive"), kommt die Mail
selbst als PDF dazu: der Abruf oder der Nachholen-Schritt legt sie als
HTML-Seite in den Anhang-Ordner, die Bruecke wandelt sie um. Ihr Ort steht als
`mail_pdf`; wird `mail_drive` abgewaehlt, kommt das PDF in den Papierkorb.

Wo die Dateien gerade liegen, steht als `drive` in der Notiz ("<ordner-id>:
<pfad>", leere ID = Wurzel des Agentenkontos). Weicht das vom Ziel ab, weil die
Mail im Eingang eingeordnet oder in der Web-App korrigiert wurde, verschiebt der
naechste Lauf die Dateien.

Geschrieben wird ueber die Drive-Bruecke (drive-bruecke/Code.gs), ein
Apps-Script im Agentenkonto, das die Web-App beim Einrichten erzeugt. So
braucht es weder Konsole noch OAuth-Client.
"""

import base64
import json
import mimetypes
import os
import re
import urllib.error
import urllib.request

import yaml

from . import mail
from . import notiz as nz

SAMMELORDNER = 'Second Brain Eingang'
BRUECKE_ALT = ('Die Drive-Bruecke kennt noch keine PDFs. In der Web-App unter Zugangsdaten '
               'den Code neu kopieren, im Skript einfuegen und unter Bereitstellen -> '
               'Bereitstellungen verwalten eine neue Version bereitstellen.')


class DriveFehler(Exception):
    pass


class Bruecke:
    """Client fuer das Apps-Script. senden ist fuer Tests austauschbar."""

    def __init__(self, url, schluessel, senden=None):
        self.url, self.schluessel = url, schluessel
        self._senden = senden or self._http

    def _http(self, daten):
        req = urllib.request.Request(self.url, data=json.dumps(daten).encode('utf-8'),
                                     headers={'Content-Type': 'text/plain;charset=utf-8'})
        # Apps-Script leitet auf googleusercontent.com um; urllib folgt per GET.
        with urllib.request.urlopen(req, timeout=120) as antwort:
            return json.loads(antwort.read().decode('utf-8'))

    def aufruf(self, aktion, **felder):
        try:
            antwort = self._senden(dict(felder, aktion=aktion, schluessel=self.schluessel))
        except (urllib.error.URLError, ValueError) as e:
            raise DriveFehler('Drive-Bruecke nicht erreichbar: %s' % e)
        if not antwort.get('ok'):
            raise DriveFehler(antwort.get('fehler') or 'unbekannter Fehler')
        return antwort

    def hochladen(self, ort, name, lokal):
        ordner_id, pfad = teilen(ort)
        with open(lokal, 'rb') as fh:
            inhalt = base64.b64encode(fh.read()).decode('ascii')
        self.aufruf('hochladen', ordner_id=ordner_id, pfad=pfad, name=name, inhalt=inhalt,
                    typ=mimetypes.guess_type(name)[0] or 'application/octet-stream')

    def pdf(self, ort, name, lokal_html):
        """HTML-Seite als PDF ablegen (Umwandlung im Apps-Script)."""
        ordner_id, pfad = teilen(ort)
        with open(lokal_html, 'rb') as fh:
            inhalt = base64.b64encode(fh.read()).decode('ascii')
        try:
            self.aufruf('pdf', ordner_id=ordner_id, pfad=pfad, name=name, inhalt=inhalt)
        except DriveFehler as e:
            raise DriveFehler(BRUECKE_ALT) if 'Unbekannte Aktion' in str(e) else e

    def loeschen(self, ort, name):
        """Datei in den Papierkorb (dort 30 Tage wiederherstellbar)."""
        ordner_id, pfad = teilen(ort)
        try:
            self.aufruf('loeschen', ordner_id=ordner_id, pfad=pfad, name=name)
        except DriveFehler as e:
            raise DriveFehler(BRUECKE_ALT) if 'Unbekannte Aktion' in str(e) else e

    def verschieben(self, von, nach, name, leeren=False):
        von_id, von_pfad = teilen(von)
        ordner_id, pfad = teilen(nach)
        self.aufruf('verschieben', von_id=von_id, von_pfad=von_pfad, ordner_id=ordner_id,
                    pfad=pfad, name=name, leeren=leeren)


def dateiname(meta, name):
    """Datum voran, damit gleichnamige Anhaenge verschiedener Mails nicht kollidieren."""
    return '%s %s' % (meta.get('erstellt'), os.path.basename(name))


def mail_pdf_name(meta, titel):
    """Dateiname der Mail als PDF, z. B. "2026-10-28 Mail Ihre Buchung.pdf"."""
    titel = re.sub(r'[\\/:*?"<>|\s]+', ' ', titel or '').strip()[:80].rstrip() or 'ohne Betreff'
    return dateiname(meta, 'Mail %s.pdf' % titel)


def teilen(ort):
    """"<ordner-id>:<pfad>" -> (ordner_id, pfad)."""
    ordner_id, _, pfad = ort.partition(':')
    return ordner_id, pfad


def ziel(meta, themen):
    """Soll-Ort der Anhaenge einer Notiz als "<ordner-id>:<pfad>"."""
    thema = themen.get((meta.get('themen') or [None])[0]) or {}
    teile = str(meta.get('ablage') or '').split('/')
    ids = thema.get('drive') or {}
    if len(teile) >= 2 and teile[1] == thema.get('ablage') and ids.get(teile[0]):
        return '%s:%s' % (ids[teile[0]], '/'.join(teile[2:]))
    return ':%s/%s' % (SAMMELORDNER, meta['id'])


def _lokale_dokumente(verz):
    """Dateien eines Anhang-Ordners ohne kleine Bilder, wie Mail.dokumente."""
    return [d for d in sorted(os.listdir(verz)) if not d.startswith('.')
            and not (os.path.splitext(d)[1].lower() in mail.BILD_ENDUNGEN
                     and os.path.getsize(os.path.join(verz, d)) < mail.BILD_MINDESTGROESSE)]


def _anhaenge_abgleichen(n, soll, lokal, bruecke):
    """Anhaenge an den Soll-Ort bringen. Liefert 'hoch', 'verschoben' oder None."""
    namen, ist = n.meta.get('anhaenge') or [], n.meta.get('drive')
    if not namen or ist == soll:
        return None
    if ist is None:
        if not os.path.isdir(lokal):
            return None
        for name in namen:
            bruecke.hochladen(soll, dateiname(n.meta, name), os.path.join(lokal, os.path.basename(name)))
        n.meta['drive'] = soll
        return 'hoch'
    sammel = ist.startswith(':%s/' % SAMMELORDNER)
    for i, name in enumerate(namen):
        bruecke.verschieben(ist, soll, dateiname(n.meta, name), leeren=sammel and i == len(namen) - 1)
    n.meta['drive'] = soll
    return 'verschoben'


def _mail_abgleichen(n, soll, lokal, bruecke):
    """Mail als PDF ablegen oder nachziehen, wenn mail_drive gesetzt ist;
    in der Web-App abgewaehlt, kommt das PDF in den Papierkorb."""
    ist = n.meta.get('mail_pdf')
    name = mail_pdf_name(n.meta, n.titel)
    if not n.meta.get('mail_drive'):
        if ist is None:
            return None
        bruecke.loeschen(ist, name)
        del n.meta['mail_pdf']
        return 'verschoben'
    if ist == soll:
        return None
    if ist is None:
        seite = os.path.join(lokal, mail.MAIL_SEITE)
        if not os.path.isfile(seite):
            return None
        bruecke.pdf(soll, name, seite)
        n.meta['mail_pdf'] = soll
        return 'hoch'
    # Die Bruecke loescht den Sammelordner nur, wenn er danach leer ist.
    bruecke.verschieben(ist, soll, name, leeren=ist.startswith(':%s/' % SAMMELORDNER))
    n.meta['mail_pdf'] = soll
    return 'verschoben'


def abgleichen(wurzel, bruecke, anhaenge=None, nachtragen=False):
    """Neue Anhaenge hochladen und verschobene Notizen nachziehen. Liefert (hoch, verschoben).

    nachtragen: Notizen aus der Zeit vor `anhaenge` bekommen die Liste aus dem
    Anhang-Ordner (z. B. ein Artefakt eines frueheren Abrufs).
    """
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
                lokal = os.path.join(anhaenge or '', n.meta['id'])
                if not n.meta.get('anhaenge') and nachtragen and anhaenge and os.path.isdir(lokal):
                    n.meta['anhaenge'] = _lokale_dokumente(lokal)
                soll = ziel(n.meta, themen)
                ergebnisse = []
                for schritt in (_anhaenge_abgleichen, _mail_abgleichen):
                    try:
                        ergebnisse.append(schritt(n, soll, lokal, bruecke))
                    except (DriveFehler, OSError) as e:
                        fehler.append('%s: %s' % (n.meta['id'], e))
                if 'hoch' in ergebnisse:
                    hoch += 1
                elif 'verschoben' in ergebnisse:
                    verschoben += 1
                if any(ergebnisse):
                    with open(pfad, 'w', encoding='utf-8') as fh:
                        fh.write(nz.schreiben(n))
    if fehler:
        raise DriveFehler('%d Notizen nicht abgeglichen:\n%s' % (len(fehler), '\n'.join(fehler)))
    return hoch, verschoben
