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
HTML-Seite in den Anhang-Ordner, Chrome im Ablauf druckt sie als PDF, die
Bruecke laedt es hoch. Ihr Ort steht als `mail_pdf`; wird `mail_drive`
abgewaehlt, kommt das PDF in den Ordner "Second Brain Papierkorb" des
Agentenkontos. So kommt die Bruecke mit hochladen und verschieben aus und muss
fuer neue Funktionen nicht neu bereitgestellt werden.

Wo die Dateien gerade liegen, steht als `drive` in der Notiz ("<ordner-id>:
<pfad>", leere ID = Wurzel des Agentenkontos). Weicht das vom Ziel ab, weil die
Mail im Eingang eingeordnet oder in der Web-App korrigiert wurde, verschiebt der
naechste Lauf die Dateien.

Hochgeladene Dateien bekommen ihre Drive-ID in `dateien` (Name -> ID), das
Mail-PDF in `mail_pdf_id`; die Web-App und der Abschnitt "Ablage in Drive" im
Notiztext verlinken damit direkt auf Datei und Ordner.

Der Jahresordner ist das Zugehoerigkeitsjahr (jahr.py). Hat ein Thema in einem
Jahr keinen eigenen Ordner mit ID, wird er im Jahresordner (config/themen.yaml:
jahre) angelegt. Mit `dauerhaft: <Unterordner>` kommt zusaetzlich eine Kopie
nach 0000-dauerhaft (themen.yaml: dauerhaft); ihr Ort steht als `drive_dauerhaft`.

Geschrieben wird ueber die Drive-Bruecke (drive-bruecke/Code.gs), ein
Apps-Script im Agentenkonto, das die Web-App beim Einrichten erzeugt. So
braucht es weder Konsole noch OAuth-Client.
"""

import base64
import json
import mimetypes
import os
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request

import yaml

from . import jahr as jz
from . import mail
from . import notiz as nz

SAMMELORDNER = 'Second Brain Eingang'
PAPIERKORB = 'Second Brain Papierkorb'


class DriveFehler(Exception):
    pass


class Bruecke:
    """Client fuer das Apps-Script. senden ist fuer Tests austauschbar."""

    def __init__(self, url, schluessel, senden=None, pdf_drucken=None):
        self.url, self.schluessel = url, schluessel
        self._senden = senden or self._http
        self._pdf_drucken = pdf_drucken or html_als_pdf

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
        """Datei hochladen; liefert ihre Drive-ID (oder None)."""
        ordner_id, pfad = teilen(ort)
        with open(lokal, 'rb') as fh:
            inhalt = base64.b64encode(fh.read()).decode('ascii')
        return self.aufruf('hochladen', ordner_id=ordner_id, pfad=pfad, name=name, inhalt=inhalt,
                           typ=mimetypes.guess_type(name)[0] or 'application/octet-stream').get('id')

    def pdf(self, ort, name, lokal_html):
        """HTML-Seite hier als PDF drucken und hochladen; liefert die Drive-ID."""
        with tempfile.TemporaryDirectory() as tmp:
            ziel = os.path.join(tmp, 'mail.pdf')
            self._pdf_drucken(lokal_html, ziel)
            return self.hochladen(ort, name, ziel)

    def wegraeumen(self, ort, name):
        """Datei in den Sammelordner Papierkorb des Agentenkontos verschieben."""
        self.verschieben(ort, ':' + PAPIERKORB, name)

    def verschieben(self, von, nach, name, leeren=False):
        von_id, von_pfad = teilen(von)
        ordner_id, pfad = teilen(nach)
        return self.aufruf('verschieben', von_id=von_id, von_pfad=von_pfad, ordner_id=ordner_id,
                           pfad=pfad, name=name, leeren=leeren).get('id')


def dateiname(meta, name):
    """Datum voran, damit gleichnamige Anhaenge verschiedener Mails nicht kollidieren."""
    return '%s %s' % (meta.get('erstellt'), os.path.basename(name))


def html_als_pdf(html, pdf):
    """HTML-Datei mit Chrome/Chromium als PDF drucken (auf GitHub-Runnern vorhanden)."""
    programm = os.environ.get('CHROME') or next(
        (p for p in ('google-chrome', 'chromium', 'chromium-browser') if shutil.which(p)), None)
    if not programm:
        raise DriveFehler('Kein Chrome/Chromium fuer das Mail-PDF gefunden')
    try:
        subprocess.run([programm, '--headless', '--no-sandbox', '--disable-gpu',
                        '--no-pdf-header-footer', '--print-to-pdf=' + pdf,
                        'file://' + os.path.abspath(html)],
                       check=True, capture_output=True, timeout=120)
    except (subprocess.SubprocessError, OSError) as e:
        raise DriveFehler('Mail-PDF nicht erzeugt: %s' % e)
    if not os.path.isfile(pdf):
        raise DriveFehler('Mail-PDF nicht erzeugt')


def mail_pdf_name(meta, titel):
    """Dateiname der Mail als PDF, z. B. "2026-10-28 Mail Ihre Buchung.pdf"."""
    titel = re.sub(r'[\\/:*?"<>|\s]+', ' ', titel or '').strip()[:80].rstrip() or 'ohne Betreff'
    return dateiname(meta, 'Mail %s.pdf' % titel)


def teilen(ort):
    """"<ordner-id>:<pfad>" -> (ordner_id, pfad)."""
    ordner_id, _, pfad = ort.partition(':')
    return ordner_id, pfad


def ziel(meta, themen, jahre=None):
    """Soll-Ort der Anhaenge einer Notiz als "<ordner-id>:<pfad>".

    Der Jahresordner in `ablage` darf "0-2026" oder "2026" heissen. Fehlt dem
    Thema eine ID fuer das Jahr, wird der Themenordner im Jahresordner angelegt."""
    thema = themen.get((meta.get('themen') or [None])[0]) or {}
    teile = str(meta.get('ablage') or '').split('/')
    jahr = jz.ordner_jahr(teile[0])
    if len(teile) >= 2 and jahr and teile[1] == thema.get('ablage'):
        tid = jz.drive_id(thema.get('drive'), jahr)
        if tid:
            return '%s:%s' % (tid, '/'.join(teile[2:]))
        jid = jz.drive_id(jahre, jahr)
        if jid:
            return '%s:%s' % (jid, '/'.join(teile[1:]))
    return ':%s/%s' % (SAMMELORDNER, meta['id'])


def dauerhaft_ziel(meta, dauerhaft):
    """Ort der Kopie in 0000-dauerhaft oder None."""
    wert = meta.get('dauerhaft')
    if not wert or not (dauerhaft or {}).get('id'):
        return None
    return '%s:%s' % (dauerhaft['id'], '' if wert is True else str(wert).strip('/'))


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
        ids = {}
        for name in namen:
            ids[os.path.basename(name)] = bruecke.hochladen(
                soll, dateiname(n.meta, name), os.path.join(lokal, os.path.basename(name)))
        n.meta['drive'] = soll
        _ids_merken(n.meta, ids)
        return 'hoch'
    sammel = ist.startswith(':%s/' % SAMMELORDNER)
    ids = {}
    for i, name in enumerate(namen):
        ids[os.path.basename(name)] = bruecke.verschieben(
            ist, soll, dateiname(n.meta, name), leeren=sammel and i == len(namen) - 1)
    n.meta['drive'] = soll
    _ids_merken(n.meta, ids)
    return 'verschoben'


def _ids_merken(meta, ids):
    """Drive-IDs der Anhaenge in `dateien` (Name -> ID); verschieben behaelt die ID."""
    ids = {k: v for k, v in ids.items() if v}
    if ids:
        meta['dateien'] = dict(meta.get('dateien') or {}, **ids)


def _mail_abgleichen(n, soll, lokal, bruecke):
    """Mail als PDF ablegen oder nachziehen, wenn mail_drive gesetzt ist;
    in der Web-App abgewaehlt, kommt das PDF in den Ordner Papierkorb."""
    ist = n.meta.get('mail_pdf')
    name = mail_pdf_name(n.meta, n.titel)
    if not n.meta.get('mail_drive'):
        if ist is None:
            return None
        bruecke.wegraeumen(ist, name)
        del n.meta['mail_pdf']
        return 'verschoben'
    if ist == soll:
        return None
    if ist is None:
        seite = os.path.join(lokal, mail.MAIL_SEITE)
        if not os.path.isfile(seite):
            return None
        fid = bruecke.pdf(soll, name, seite)
        n.meta['mail_pdf'] = soll
        if fid:
            n.meta['mail_pdf_id'] = fid
        return 'hoch'
    # Die Bruecke loescht den Sammelordner nur, wenn er danach leer ist.
    fid = bruecke.verschieben(ist, soll, name, leeren=ist.startswith(':%s/' % SAMMELORDNER))
    n.meta['mail_pdf'] = soll
    if fid:
        n.meta['mail_pdf_id'] = fid
    return 'verschoben'


def _dauerhaft_abgleichen(n, soll_d, lokal, bruecke):
    """Kopie der Anhaenge (und des Mail-PDFs) in 0000-dauerhaft. Abgewaehlt kommt
    die Kopie in den Papierkorb, geaendert wird sie verschoben. Fehlen die Dateien
    lokal, holt `second-brain nachholen` sie beim naechsten Abruf."""
    ist = n.meta.get('drive_dauerhaft')
    namen = [dateiname(n.meta, a) for a in n.meta.get('anhaenge') or []]
    pdf = mail_pdf_name(n.meta, n.titel)
    if soll_d == ist:
        return None
    if ist and not soll_d:
        for name in namen + ([pdf] if n.meta.get('mail_pdf') else []):
            bruecke.wegraeumen(ist, name)
        del n.meta['drive_dauerhaft']
        return 'verschoben'
    if ist:
        for name in namen + ([pdf] if n.meta.get('mail_pdf') else []):
            bruecke.verschieben(ist, soll_d, name)
        n.meta['drive_dauerhaft'] = soll_d
        return 'verschoben'
    seite = os.path.join(lokal, mail.MAIL_SEITE)
    dateien = [(dateiname(n.meta, a), os.path.join(lokal, os.path.basename(a)))
               for a in n.meta.get('anhaenge') or []]
    if not all(os.path.isfile(p) for _, p in dateien) or (
            n.meta.get('mail_drive') and not dateien and not os.path.isfile(seite)):
        return None  # nachholen holt die Dateien aus dem Postfach
    for name, pfad in dateien:
        bruecke.hochladen(soll_d, name, pfad)
    if n.meta.get('mail_drive') and os.path.isfile(seite):
        bruecke.pdf(soll_d, pdf, seite)
    if not dateien and not n.meta.get('mail_drive'):
        return None
    n.meta['drive_dauerhaft'] = soll_d
    return 'hoch'


# --- Links im Notiztext -----------------------------------------------------

LINKS_ANFANG = '<!-- ablage -->'
LINKS_ENDE = '<!-- /ablage -->'


def ordner_link(ort, meta, ordner_ids=None, themen=None):
    """Link auf den Drive-Ordner eines Orts "<id>:<pfad>": der genaue Ordner, wenn
    seine ID bekannt ist (config/ordner.yaml: ids, laufendes Jahr), sonst der
    naechste bekannte Ordner darueber."""
    oid, pfad = teilen(ort or '')
    if not oid:
        return None
    thema = (meta.get('themen') or [''])[0]
    teile = [t for t in pfad.split('/') if t]
    jahr = jz.ordner_jahr(str(meta.get('ablage') or '').split('/')[0])
    ids = ((themen or {}).get(thema) or {}).get('drive') or {}
    # ordner.yaml kennt die Unterordner des laufenden Jahres (Schluessel 0-<jahr>)
    laufend = ('0-%s' % jahr) in ids
    if laufend and oid == ids['0-%s' % jahr]:
        for i in range(len(teile), 0, -1):
            gefunden = (ordner_ids or {}).get('%s/%s' % (thema, '/'.join(teile[:i])))
            if gefunden:
                return 'https://drive.google.com/drive/folders/%s' % gefunden
    return 'https://drive.google.com/drive/folders/%s' % oid


def pfad_text(ablage):
    """'0-2026/01Gebäude/atu' -> '2026 › 01Gebäude › atu' (wie in der Web-App)."""
    teile = [t for t in str(ablage or '').split('/') if t]
    if teile and jz.ordner_jahr(teile[0]):
        teile[0] = str(jz.ordner_jahr(teile[0]))
    return ' › '.join(teile)


def links_block(meta, ordner_ids=None, themen=None, dauerhaft=None):
    """Abschnitt "Ablage in Drive" fuer den Notiztext (Markdown) oder ''."""
    zeilen = []
    if meta.get('drive') or meta.get('mail_pdf'):
        ort = meta.get('drive') or meta.get('mail_pdf')
        link = ordner_link(ort, meta, ordner_ids, themen)
        if link:
            zeilen.append('Ordner: [%s](%s)' % (pfad_text(meta.get('ablage')) or 'Drive', link))
    ids = meta.get('dateien') or {}
    for a in meta.get('anhaenge') or []:
        fid = ids.get(os.path.basename(str(a)))
        if fid and meta.get('drive'):
            zeilen.append('- Anhang [%s](https://drive.google.com/file/d/%s/view)' % (a, fid))
    if meta.get('mail_pdf_id') and meta.get('mail_pdf'):
        zeilen.append('- Mail als PDF: [öffnen](https://drive.google.com/file/d/%s/view)'
                      % meta['mail_pdf_id'])
    if meta.get('drive_dauerhaft'):
        did, dpfad = teilen(meta['drive_dauerhaft'])
        name = ((dauerhaft or {}).get('name') or '0000-dauerhaft')
        zeilen.append('Kopie: [%s](https://drive.google.com/drive/folders/%s)'
                      % (' › '.join([name] + [t for t in dpfad.split('/') if t]), did))
    if not zeilen:
        return ''
    return '%s\n## Ablage in Drive\n\n%s\n%s' % (LINKS_ANFANG, '\n'.join(zeilen), LINKS_ENDE)


def links_einsetzen(text, block):
    """Block im Notiztext ersetzen, anhaengen oder entfernen. Liefert den neuen Text."""
    a, e = text.find(LINKS_ANFANG), text.find(LINKS_ENDE)
    if a >= 0 and e > a:
        rest = (text[:a].rstrip('\n') + ('\n\n' + block if block else '')
                + text[e + len(LINKS_ENDE):].rstrip('\n'))
        return rest
    return text.rstrip('\n') + ('\n\n' + block if block else '')


def abgleichen(wurzel, bruecke, anhaenge=None, nachtragen=False):
    """Neue Anhaenge hochladen und verschobene Notizen nachziehen. Liefert (hoch, verschoben).

    nachtragen: Notizen aus der Zeit vor `anhaenge` bekommen die Liste aus dem
    Anhang-Ordner (z. B. ein Artefakt eines frueheren Abrufs).
    """
    with open(os.path.join(wurzel, 'config', 'themen.yaml'), encoding='utf-8') as fh:
        roh = yaml.safe_load(fh) or {}
    themen, jahre, dauerhaft = roh.get('themen', {}), roh.get('jahre', {}), roh.get('dauerhaft')
    ordner_ids = {}
    if os.path.isfile(os.path.join(wurzel, 'config', 'ordner.yaml')):
        with open(os.path.join(wurzel, 'config', 'ordner.yaml'), encoding='utf-8') as fh:
            ordner_ids = (yaml.safe_load(fh) or {}).get('ids') or {}
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
                soll = ziel(n.meta, themen, jahre)
                ergebnisse = []
                for schritt in (_anhaenge_abgleichen, _mail_abgleichen):
                    try:
                        ergebnisse.append(schritt(n, soll, lokal, bruecke))
                    except (DriveFehler, OSError) as e:
                        fehler.append('%s: %s' % (n.meta['id'], e))
                if basis == 'notizen':
                    try:
                        ergebnisse.append(_dauerhaft_abgleichen(
                            n, dauerhaft_ziel(n.meta, dauerhaft), lokal, bruecke))
                    except (DriveFehler, OSError) as e:
                        fehler.append('%s: %s' % (n.meta['id'], e))
                    text = links_einsetzen(n.text, links_block(n.meta, ordner_ids, themen, dauerhaft))
                    if text != n.text:
                        n.text = text
                        ergebnisse.append('links')
                if 'hoch' in ergebnisse:
                    hoch += 1
                elif 'verschoben' in ergebnisse:
                    verschoben += 1
                ergebnisse = [x for x in ergebnisse if x]
                if any(ergebnisse):
                    with open(pfad, 'w', encoding='utf-8') as fh:
                        fh.write(nz.schreiben(n))
    if fehler:
        raise DriveFehler('%d Notizen nicht abgeglichen:\n%s' % (len(fehler), '\n'.join(fehler)))
    return hoch, verschoben
