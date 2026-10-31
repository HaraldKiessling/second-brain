"""Mail-Adapter: holt Mails per IMAP (oder aus .eml-Dateien) und legt sie ab.

Pro Mail entscheidet einordnen.py (Regel, Spam, Heuristik, optional KI):
  verwerfen -> Indexzeile mit Feld "verworfen" (Grund), damit nichts verloren geht
  index     -> eine Zeile in index/mail/<jahr>-<monat>.jsonl
  notiz     -> notizen/<jahr>/<thema>/<id>.md, Eintrag im Aenderungsprotokoll
  offen     -> eingang/<id>.md mit Vorschlag und Konfidenz, Harald entscheidet

Anhaenge werden nie ins Daten-Repo geschrieben, sondern in ein separates
Verzeichnis (--anhaenge), aus dem der Drive-Schritt sie hochlaedt.
Der Abruf merkt sich je Konto die zuletzt gesehene IMAP-UID
(eingang/.status/mail-<konto>.json) und ist dadurch wiederholbar.

Nachholen: In der Web-App kann Harald eine Indexmail nachtraeglich als Notiz
ablegen (`nachholen: true`) oder eine Notiz als PDF nach Drive geben lassen
(`mail_drive: true`). Dafuer holt nachholen() die Mail per Message-ID noch
einmal aus dem Postfach.
"""

import datetime
import email
import email.policy
import email.utils
import imaplib
import json
import os
import re
import unicodedata
from dataclasses import dataclass, field
from html import escape

import yaml

from . import einordnen as eo
from . import notiz as nz
from . import regeln

DOK_ENDUNGEN = ('.pdf', '.png', '.jpg', '.jpeg', '.csv', '.xls', '.xlsx',
                '.doc', '.docx', '.txt', '.gif', '.webp', '.tif', '.tiff')
BILD_ENDUNGEN = ('.png', '.jpg', '.jpeg', '.gif', '.webp')
BILD_MINDESTGROESSE = 50_000  # kleinere Bilder sind Logos oder Signaturen
KURZ_LAENGE = 300
TEXT_LAENGE = 2000
MAIL_SEITE = '.mail.html'  # Mail als HTML-Seite im Anhang-Ordner, fuer die PDF-Ablage
KOEPFE = ('list-unsubscribe', 'list-id', 'precedence', 'auto-submitted') + eo.SPAM_KOEPFE


@dataclass
class Mail:
    message_id: str
    datum: datetime.date
    absender: str
    betreff: str
    text: str
    anhaenge: list = field(default_factory=list)  # [(dateiname, bytes)]
    kopf: dict = field(default_factory=dict)      # ausgewaehlte Kopfzeilen, Namen klein
    kategorie: str = ''                           # Gmail: werbung, sozial
    empfaenger: str = ''                          # An und Cc
    html: str = ''                                # HTML-Fassung, falls vorhanden

    @property
    def dokumente(self):
        """Anhaenge ohne kleine Bilder (Logos, Signaturen)."""
        return [(n, inhalt) for n, inhalt in self.anhaenge
                if not (os.path.splitext(n)[1].lower() in BILD_ENDUNGEN
                        and len(inhalt) < BILD_MINDESTGROESSE)]

    @property
    def hat_dokument(self):
        return any(os.path.splitext(n)[1].lower() in DOK_ENDUNGEN for n, _ in self.dokumente)


@dataclass
class Bilanz:
    verwerfen: int = 0
    index: int = 0
    notiz: int = 0
    offen: int = 0
    doppelt: int = 0
    eintraege: list = field(default_factory=list)  # neue Notizen und Eingaenge

    def __str__(self):
        return ('%d Notizen, %d offen, %d Index, %d verworfen, %d schon bekannt'
                % (self.notiz, self.offen, self.index, self.verwerfen, self.doppelt))


# --- Mails lesen -----------------------------------------------------------

def _text_von(msg):
    teil = msg.get_body(preferencelist=('plain', 'html'))
    if teil is None:
        return ''
    try:
        inhalt = teil.get_content()
    except (LookupError, ValueError):
        return ''
    if teil.get_content_subtype() == 'html':
        inhalt = re.sub(r'(?is)<(script|style).*?</\1>', ' ', inhalt)
        inhalt = re.sub(r'<[^>]+>', ' ', inhalt)
    return re.sub(r'[ \t]+', ' ', re.sub(r'\n\s*\n+', '\n\n', inhalt)).strip()


def _html_von(msg):
    teil = msg.get_body(preferencelist=('html',))
    try:
        return teil.get_content() if teil is not None else ''
    except (LookupError, ValueError):
        return ''


def mail_aus_bytes(roh):
    msg = email.message_from_bytes(roh, policy=email.policy.default)
    try:
        datum = email.utils.parsedate_to_datetime(msg['Date']).date()
    except (TypeError, ValueError):
        datum = datetime.date.today()
    anhaenge = []
    for teil in msg.iter_attachments():
        name = teil.get_filename()
        inhalt = teil.get_payload(decode=True)
        if name and inhalt is not None:
            anhaenge.append((name, inhalt))
    return Mail(message_id=str(msg['Message-ID'] or '').strip(),
                datum=datum,
                absender=str(msg['From'] or ''),
                betreff=str(msg['Subject'] or ''),
                text=_text_von(msg),
                anhaenge=anhaenge,
                kopf={k: str(msg[k]) for k in KOEPFE if msg[k] is not None},
                empfaenger=', '.join(str(msg[k]) for k in ('To', 'Cc') if msg[k] is not None),
                html=_html_von(msg))


def _gmail_kategorien(imap, uids):
    """UIDs je Gmail-Kategorie (nur mit Gmail-Erweiterung X-GM-EXT-1)."""
    if 'X-GM-EXT-1' not in imap.capabilities or not uids:
        return {}
    kategorien = {}
    for kategorie, suche in (('werbung', 'category:promotions'),
                             ('sozial', 'category:social')):
        try:
            _, treffer = imap.uid('SEARCH', None, 'X-GM-RAW', '"%s"' % suche)
        except imaplib.IMAP4.error:
            continue
        for u in treffer[0].split():
            if int(u) in uids:
                kategorien[int(u)] = kategorie
    return kategorien


def imap_abruf(host, benutzer, passwort, status, postfach='INBOX', start_tage=30):
    """Neue Mails seit der letzten UID. Liefert (mails, neuer_status)."""
    imap = imaplib.IMAP4_SSL(host, 993)
    try:
        imap.login(benutzer, passwort)
        typ, daten = imap.select(postfach, readonly=True)
        if typ != 'OK':
            raise RuntimeError('Postfach %s nicht lesbar' % postfach)
        validity = imap.response('UIDVALIDITY')[1][0].decode()
        if status.get('uidvalidity') == validity and status.get('letzte_uid'):
            kriterium = 'UID %d:*' % (int(status['letzte_uid']) + 1)
        else:
            seit = datetime.date.today() - datetime.timedelta(days=start_tage)
            kriterium = 'SINCE %s' % seit.strftime('%d-%b-%Y')
        _, treffer = imap.uid('SEARCH', None, kriterium)
        uids = [int(u) for u in treffer[0].split()]
        uids = [u for u in uids if u > int(status.get('letzte_uid') or 0)
                or status.get('uidvalidity') != validity]
        kategorien = _gmail_kategorien(imap, set(uids))
        mails = []
        for uid in uids:
            _, teile = imap.uid('FETCH', str(uid), '(BODY.PEEK[])')
            roh = next(t[1] for t in teile if isinstance(t, tuple))
            m = mail_aus_bytes(roh)
            m.kategorie = kategorien.get(uid, '')
            mails.append(m)
        letzte = max(uids) if uids else status.get('letzte_uid')
        return mails, {'uidvalidity': validity, 'letzte_uid': letzte}
    finally:
        try:
            imap.logout()
        except Exception:
            pass


def imap_holen(host, benutzer, passwort, message_ids, postfach='INBOX'):
    """Mails nach Message-ID holen. Liefert {message_id: rohbytes}, nicht gefundene fehlen."""
    imap = imaplib.IMAP4_SSL(host, 993)
    gefunden = {}
    try:
        imap.login(benutzer, passwort)
        typ, _ = imap.select(postfach, readonly=True)
        if typ != 'OK':
            raise RuntimeError('Postfach %s nicht lesbar' % postfach)
        for mid in message_ids:
            _, treffer = imap.uid('SEARCH', None, 'HEADER', 'Message-ID',
                                  '"%s"' % mid.replace('"', ''))
            uids = treffer[0].split()
            if not uids:
                continue
            _, teile = imap.uid('FETCH', uids[-1].decode(), '(BODY.PEEK[])')
            gefunden[mid] = next(t[1] for t in teile if isinstance(t, tuple))
        return gefunden
    finally:
        try:
            imap.logout()
        except Exception:
            pass


# --- Ablegen ---------------------------------------------------------------

def _slug(text, laenge=40):
    text = unicodedata.normalize('NFKD', text.lower())
    text = text.replace('ß', 'ss')
    text = ''.join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r'[^a-z0-9]+', '-', text).strip('-')
    return text[:laenge].rstrip('-') or 'ohne-titel'


def _absender_kurz(absender):
    name, adresse = email.utils.parseaddr(absender)
    if name and 'noreply' not in name.lower().replace('-', ''):
        return name
    domain = adresse.split('@')[-1]
    return domain.split('.')[-2] if domain.count('.') >= 1 else (adresse or 'unbekannt')


def jahr_ordner(datum, heute=None):
    heute = heute or datetime.date.today()
    return '0-%d' % datum.year if datum.year == heute.year else str(datum.year)


class Ablage:
    """Schreibt Ergebnisse in ein Daten-Repo."""

    def __init__(self, wurzel, konto, anhang_ziel=None, heute=None):
        self.wurzel = wurzel
        self.konto = konto
        self.anhang_ziel = anhang_ziel
        self.heute = heute or datetime.date.today()
        with open(os.path.join(wurzel, 'config', 'themen.yaml'), encoding='utf-8') as fh:
            self.themen = (yaml.safe_load(fh) or {}).get('themen', {})
        self.bekannt = self._bekannte_message_ids()

    def _pfad(self, *teile):
        return os.path.join(self.wurzel, *teile)

    def _bekannte_message_ids(self):
        ids = set()
        index = self._pfad('index', 'mail')
        if os.path.isdir(index):
            for d in os.listdir(index):
                if d.endswith('.jsonl'):
                    with open(os.path.join(index, d), encoding='utf-8') as fh:
                        ids.update(json.loads(z).get('message_id') for z in fh if z.strip())
        for basis in ('notizen', 'eingang'):
            for verz, _, dateien in os.walk(self._pfad(basis)):
                for d in dateien:
                    if d.endswith('.md') and d != 'README.md':
                        with open(os.path.join(verz, d), encoding='utf-8') as fh:
                            try:
                                ids.add(nz.lesen(fh.read()).meta.get('message_id'))
                            except nz.FormatFehler:
                                pass
        ids.discard(None)
        ids.discard('')
        return ids

    def _neue_id(self, mail):
        basis = '%s-%s-%s' % (mail.datum.isoformat(), _slug(_absender_kurz(mail.absender), 20),
                              _slug(mail.betreff, 40))
        nid, n = basis, 2
        while (os.path.exists(self._pfad('eingang', nid + '.md'))
               or any(os.path.exists(os.path.join(v, nid + '.md'))
                      for v, _, _ in os.walk(self._pfad('notizen')))):
            nid, n = '%s-%d' % (basis, n), n + 1
        return nid

    def _protokoll(self, wer, aenderung):
        pfad = self._pfad('protokoll', '%s.md' % self.heute.strftime('%Y-%m'))
        if not os.path.exists(pfad):
            os.makedirs(os.path.dirname(pfad), exist_ok=True)
            with open(pfad, 'w', encoding='utf-8') as fh:
                fh.write('# Änderungsprotokoll %s\n\n| Datum | Wer | Änderung |\n| --- | --- | --- |\n'
                         % self.heute.strftime('%Y-%m'))
        with open(pfad, 'a', encoding='utf-8') as fh:
            fh.write('| %s | %s | %s |\n' % (self.heute.isoformat(), wer, aenderung))

    def ablegen(self, mail, ergebnis):
        """Eine Mail nach dem Ergebnis von einordnen.py ablegen. Liefert den Pfad."""
        if ergebnis.aktion in (regeln.VERWERFEN, regeln.INDEX):
            pfad = self._pfad('index', 'mail', mail.datum.strftime('%Y-%m') + '.jsonl')
            os.makedirs(os.path.dirname(pfad), exist_ok=True)
            zeile = {'datum': mail.datum.isoformat(), 'konto': self.konto,
                     'absender': mail.absender, 'betreff': mail.betreff,
                     'kurz': ' '.join(mail.text.split())[:KURZ_LAENGE],
                     'message_id': mail.message_id}
            if ergebnis.aktion == regeln.VERWERFEN:
                zeile['verworfen'] = ergebnis.grund
            elif ergebnis.spam >= 0.3:
                zeile['spam'] = round(ergebnis.spam, 2)
            with open(pfad, 'a', encoding='utf-8') as fh:
                fh.write(json.dumps(zeile, ensure_ascii=False) + '\n')
            self.bekannt.add(mail.message_id)
            return pfad

        nid = self._neue_id(mail)
        meta = {'id': nid, 'erstellt': mail.datum, 'quelle': self.konto,
                'message_id': mail.message_id, 'absender': eo.adresse(mail.absender)}
        if mail.dokumente:
            meta['anhaenge'] = [os.path.basename(n) for n, _ in mail.dokumente]
        if not mail.hat_dokument:
            meta['ohne_anhang'] = True
        if ergebnis.aktion == regeln.NOTIZ:
            thema = self.themen.get(ergebnis.thema, {})
            ablage = '/'.join(t for t in (jahr_ordner(mail.datum, self.heute),
                                          thema.get('ablage', ''),
                                          unterordner_einsetzen(ergebnis.unterordner,
                                                                mail.datum)) if t)
            durch = ergebnis.durch or 'regel/' + ergebnis.regel
            meta.update(personen=ergebnis.personen, themen=[ergebnis.thema],
                        ablage=ablage, eingeordnet_durch=durch)
            if ergebnis.konfidenz < 1:
                meta['konfidenz'] = round(ergebnis.konfidenz, 2)
            if ergebnis.mail_drive:
                meta['mail_drive'] = True
            pfad = self._pfad('notizen', str(mail.datum.year), ergebnis.thema, nid + '.md')
            self._protokoll(durch, 'Notiz `%s` angelegt (%s)' % (nid, ergebnis.grund))
        else:
            meta.update(personen=[], themen=[], offen_grund=ergebnis.grund)
            if ergebnis.vorschlag is not None:
                meta['vorschlag'] = ergebnis.vorschlag.als_dict()
            pfad = self._pfad('eingang', nid + '.md')

        os.makedirs(os.path.dirname(pfad), exist_ok=True)
        with open(pfad, 'w', encoding='utf-8') as fh:
            fh.write(nz.schreiben(nz.Notiz(meta=meta, text=notiz_text(mail))))
        anhaenge_sichern(self.anhang_ziel, nid, mail)
        if meta.get('mail_drive'):
            seite_sichern(self.anhang_ziel, nid, mail_seite(
                mail.absender, mail.datum.isoformat(), mail.betreff, mail.text, mail.html,
                mail.empfaenger))
        self.bekannt.add(mail.message_id)
        return pfad


def notiz_text(mail):
    text = mail.text[:TEXT_LAENGE].rstrip()
    if len(mail.text) > TEXT_LAENGE:
        text += ' …'
    teile = ['# %s' % (mail.betreff.strip() or '(ohne Betreff)'), '',
             'Von: %s  ' % mail.absender, 'Datum: %s' % mail.datum.isoformat()]
    if mail.anhaenge:
        teile.append('Anhänge: %s' % ', '.join(n for n, _ in mail.anhaenge))
    return '\n'.join(teile) + '\n\n' + text + '\n'


def anhaenge_sichern(anhang_ziel, nid, mail):
    if not anhang_ziel or not mail.dokumente:
        return
    ziel = os.path.join(anhang_ziel, nid)
    os.makedirs(ziel, exist_ok=True)
    for name, inhalt in mail.dokumente:
        with open(os.path.join(ziel, os.path.basename(name)), 'wb') as fh:
            fh.write(inhalt)


def seite_sichern(anhang_ziel, nid, seite):
    if not anhang_ziel:
        return
    ziel = os.path.join(anhang_ziel, nid)
    os.makedirs(ziel, exist_ok=True)
    with open(os.path.join(ziel, MAIL_SEITE), 'w', encoding='utf-8') as fh:
        fh.write(seite)


def mail_seite(absender, datum, betreff, text, html='', empfaenger=''):
    """Die Mail als eigenstaendige HTML-Seite mit Kopf (Von, An, Datum, Betreff);
    die Drive-Bruecke macht daraus ein PDF. Ohne HTML-Fassung wird der Text gesetzt."""
    zeilen = ''.join('<tr><th style="text-align:left;padding-right:1em">%s</th><td>%s</td></tr>'
                     % (k, escape(str(v))) for k, v in (('Von', absender), ('An', empfaenger),
                                                        ('Datum', datum), ('Betreff', betreff)) if v)
    kopf = ('<table style="font-family:sans-serif;font-size:10pt;margin-bottom:1em">%s</table>'
            '<hr>' % zeilen)
    meta = '<meta charset="utf-8">'
    if not html:
        return ('<!doctype html><html><head>%s</head><body>%s<pre style="white-space:pre-wrap;'
                'font-family:sans-serif;font-size:10pt">%s</pre></body></html>'
                % (meta, kopf, escape(text)))
    html = re.sub(r'(?is)<script.*?</script>', '', html)
    html = re.sub(r'(?is)<meta[^>]*charset[^>]*>', '', html)
    html = re.sub(r'(?is)<img[^>]*src=["\']?cid:[^>]*>', '', html)  # eingebettete Bilder fehlen
    if re.search(r'(?i)<body[^>]*>', html):
        html = re.sub(r'(?i)<body[^>]*>', lambda m: m.group(0) + kopf, html, count=1)
    else:
        html = kopf + html
    if re.search(r'(?i)<head[^>]*>', html):
        return re.sub(r'(?i)<head[^>]*>', lambda m: m.group(0) + meta, html, count=1)
    return meta + html


def nachholen(wurzel, konto, holen, anhang_ziel=None):
    """Notizen dieses Kontos vervollstaendigen, die die Web-App angefordert hat.

    nachholen: true -> voller Mailtext statt Kurzinhalt, Anhaenge fuer Drive
    mail_drive ohne mail_pdf -> Mail als HTML-Seite fuer die PDF-Ablage; ist sie
      nicht mehr im Postfach, wird die Seite aus dem Notiztext gebaut.
    holen: Liste von Message-IDs -> {message_id: rohbytes} (z. B. imap_holen).
    Liefert (vervollstaendigt, nicht_gefunden).
    """
    auftraege = []
    for verz, _, dateien in os.walk(os.path.join(wurzel, 'notizen')):
        for d in sorted(dateien):
            if not d.endswith('.md') or d == 'README.md':
                continue
            pfad = os.path.join(verz, d)
            with open(pfad, encoding='utf-8') as fh:
                try:
                    n = nz.lesen(fh.read())
                except nz.FormatFehler:
                    continue
            m = n.meta
            if m.get('quelle') == konto and (
                    m.get('nachholen') or (m.get('mail_drive') and not m.get('mail_pdf'))):
                auftraege.append((pfad, n))
    if not auftraege:
        return 0, 0
    ids = [n.meta['message_id'] for _, n in auftraege if n.meta.get('message_id')]
    roh = holen(ids) if ids else {}
    fertig = fehlt = 0
    for pfad, n in auftraege:
        r = roh.get(n.meta.get('message_id'))
        m = mail_aus_bytes(r) if r else None
        if m is None:
            fehlt += 1
        if n.meta.pop('nachholen', None):
            if m is not None:
                n.text = notiz_text(m)
                if m.dokumente:
                    n.meta['anhaenge'] = [os.path.basename(a) for a, _ in m.dokumente]
                n.meta.pop('nachholen_fehler', None)
            else:
                n.meta['nachholen_fehler'] = 'Mail nicht mehr im Postfach, nur Kurzinhalt'
        if m is not None:
            anhaenge_sichern(anhang_ziel, n.meta['id'], m)
            fertig += 1
        if n.meta.get('mail_drive') and not n.meta.get('mail_pdf') and anhang_ziel:
            if m is not None:
                seite = mail_seite(m.absender, m.datum.isoformat(), m.betreff, m.text, m.html,
                                   m.empfaenger)
            else:
                text = re.sub(r'^# .*\n+', '', n.text)
                seite = mail_seite(n.meta.get('absender', ''), str(n.meta.get('erstellt')),
                                   n.titel, text)
            seite_sichern(anhang_ziel, n.meta['id'], seite)
        with open(pfad, 'w', encoding='utf-8') as fh:
            fh.write(nz.schreiben(n))
    return fertig, fehlt


def unterordner_einsetzen(unterordner, datum):
    """Platzhalter {jahr} und {monat} im (mehrstufigen) Unterordner ersetzen."""
    return (unterordner or '').replace('{jahr}', str(datum.year)).replace(
        '{monat}', '%02d' % datum.month).strip('/')


def verarbeiten(mails, ablage, regelwerk, lerner=None, einst=None, ki=None):
    bilanz = Bilanz()
    lerner = lerner or eo.Lerner([], ablage.themen)
    einst = einst or eo.einstellungen({})
    for mail in mails:
        if mail.message_id and mail.message_id in ablage.bekannt:
            bilanz.doppelt += 1
            continue
        e = eo.einordnen(mail, regelwerk, lerner, einst, ki)
        pfad = ablage.ablegen(mail, e)
        setattr(bilanz, e.aktion, getattr(bilanz, e.aktion) + 1)
        if e.aktion in (regeln.NOTIZ, regeln.OFFEN):
            bilanz.eintraege.append({
                'aktion': e.aktion, 'pfad': os.path.relpath(pfad, ablage.wurzel),
                'titel': mail.betreff.strip(), 'absender': eo.adresse(mail.absender),
                'thema': e.thema or (e.vorschlag.thema if e.vorschlag else ''),
                'durch': e.durch or (e.vorschlag.durch if e.vorschlag else ''),
                'konfidenz': round(e.konfidenz, 2), 'grund': e.grund})
    return bilanz


def lauf_protokollieren(wurzel, konto, bilanz, jetzt=None):
    """Ergebnis eines Abrufs fuer die Uebersicht der Web-App festhalten
    (protokoll/laeufe/<jahr>-<monat>.jsonl). Laeufe ohne neue Mails nicht."""
    zahlen = {k: getattr(bilanz, k) for k in ('notiz', 'offen', 'index', 'verwerfen')}
    if not any(zahlen.values()):
        return None
    jetzt = jetzt or datetime.datetime.now(datetime.timezone.utc)
    pfad = os.path.join(wurzel, 'protokoll', 'laeufe', jetzt.strftime('%Y-%m') + '.jsonl')
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    zeile = dict(zeit=jetzt.isoformat(timespec='seconds'), konto=konto, **zahlen,
                 eintraege=bilanz.eintraege)
    with open(pfad, 'a', encoding='utf-8') as fh:
        fh.write(json.dumps(zeile, ensure_ascii=False) + '\n')
    return pfad


def status_laden(wurzel, konto):
    pfad = os.path.join(wurzel, 'eingang', '.status', 'mail-%s.json' % konto)
    try:
        with open(pfad, encoding='utf-8') as fh:
            return json.load(fh)
    except FileNotFoundError:
        return {}


def status_speichern(wurzel, konto, status):
    pfad = os.path.join(wurzel, 'eingang', '.status', 'mail-%s.json' % konto)
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    with open(pfad, 'w', encoding='utf-8') as fh:
        json.dump(status, fh, indent=2)
        fh.write('\n')
