"""Einordnen in Stufen (ADR 0004): jeder Eingang bekommt eine Entscheidung.

  1. Spam      - Spam-Wert aus Mail-Kopf und Betreff; ab spam_schwelle
                 verworfen (bleibt als Indexeintrag mit Grund auffindbar).
                 Passt eine Regel, gilt die Regel.
  2. Regel     - genau eine Ordner- oder Aussortier-Regel passt (regeln.py):
                 Notiz bzw. verworfen, ohne Rueckfrage. Passen mehrere, ist
                 das ein Regelkonflikt: Eingang mit allen passenden Regeln.
  3. KI        - optional (config/einordnen.yaml ki.aktiv): Vorschlag mit
                 Ordner, Merkmalen und Steuerposten. Ohne Regel wird nie ohne
                 Haralds Freigabe abgelegt: der Eingang kommt mit Vorschlag
                 nach "Zu erledigen".

Merkmalregeln (Personen, Steuer ...) gelten fuer Regel- und KI-Ergebnis.

Notiz oder Eingang wird nur ein Eingang mit Dokument-Anhang; ohne Dokument
bleibt es beim Indexeintrag, es sei denn, eine Regel erlaubt es
(ohne_anhang), die Mail kommt von einer eigenen Adresse (eigene_adressen),
oder die KI haelt sie fuer wichtig (dann mit Vorschlag in den Eingang).

Gelernt wird nur ueber Regelvorschlaege (regelvorschlaege()): Hat Harald
mindestens zweimal Gleiches abgelegt, entsteht ein Regelentwurf, der in der
Web-App mit den passenden Eingaengen gezeigt wird.

Die Einstellungen stehen in config/einordnen.yaml (siehe STANDARD).
"""

import email.utils
import json
import re
import urllib.request
from dataclasses import dataclass, field

from . import notiz as nz
from . import regeln

STANDARD = {
    'schwelle': 0.8,       # ab dieser Konfidenz ohne Rueckfrage ablegen
    'spam_schwelle': 0.6,  # ab diesem Spam-Wert verwerfen (bleibt im Index sichtbar)
    'eigene_adressen': [],  # Mails von hier werden immer erfasst (an sich selbst gesendet)
    'ki': {'aktiv': False, 'modell': '', 'max_pro_lauf': 20,
           'hinweise': ''},  # Ablagelogik in Haralds Worten, geht in jede Anfrage
}

FREEMAIL = {'gmail.com', 'googlemail.com', 'gmx.de', 'gmx.net', 'gmx.at', 'web.de',
            't-online.de', 'outlook.com', 'outlook.de', 'hotmail.com', 'hotmail.de',
            'live.de', 'yahoo.com', 'yahoo.de', 'icloud.com', 'me.com', 'aol.com',
            'posteo.de', 'mailbox.org', 'freenet.de', 'arcor.de'}

WERBEWOERTER = ('newsletter', 'angebot', 'rabatt', 'gutschein', 'sale', 'deal',
                'gratis', 'gewinnspiel', 'exklusiv', 'nur heute', 'black friday',
                'sparen sie', '% auf', 'jetzt zugreifen', 'webinar', 'vorteil',
                'last chance', 'jetzt sichern', 'neuigkeiten', 'entdecken',
                'nicht verpassen', 'gratulieren sie')

# Absender, wie sie Versandsysteme fuer Werbung benutzen (Teil vor dem @
# oder Subdomain): news@, newsletter@, promotion@, info@mail.firma.de, ...
WERBE_ABSENDER = re.compile(
    r'(^|[.@-])(news|newsletter|promo|promotion|marketing|angebote|aktion|deals?|'
    r'mailing|kampagne|campaign|hello|hallo|e-?mails?|info|mail|m|em|email|e|t)[.@]')
EMOJI = re.compile('[\U0001F300-\U0001FAFF\u2600-\u27BF]')

SPAM_KOEPFE = ('x-spam-flag', 'x-spam', 'x-spam-status', 'x-ui-filterresults',
               'x-gmx-antispam')


@dataclass
class Vorschlag:
    thema: str
    konfidenz: float
    durch: str
    grund: str
    unterordner: str = ''
    personen: list = field(default_factory=list)
    alternativen: list = field(default_factory=list)  # weitere Vorschlaege (KI)
    mail_drive: bool = False
    weitere_themen: list = field(default_factory=list)
    objekte: list = field(default_factory=list)
    steuer: list = field(default_factory=list)
    jahr: int = 0          # Zugehoerigkeitsjahr laut KI (Geldfluss), 0 = nicht genannt
    jahr_grund: str = ''
    dauerhaft: str = ''    # KI: betrifft viele Jahre (Grund), Vorschlag fuer 0000-dauerhaft

    def als_dict(self):
        d = {'thema': self.thema, 'unterordner': self.unterordner,
             'personen': list(self.personen), 'konfidenz': round(self.konfidenz, 2),
             'durch': self.durch, 'grund': self.grund}
        if self.mail_drive:
            d['mail_drive'] = True
        for k in ('weitere_themen', 'objekte', 'steuer'):
            if getattr(self, k):
                d[k] = list(getattr(self, k))
        if self.jahr:
            d['jahr'] = self.jahr
            if self.jahr_grund:
                d['jahr_grund'] = self.jahr_grund
        if self.dauerhaft:
            d['dauerhaft'] = self.dauerhaft
        if self.alternativen:
            d['alternativen'] = [a.als_dict() for a in self.alternativen]
        return d


def einstellungen(roh):
    """Einstellungen aus config/einordnen.yaml mit Standardwerten ergaenzt."""
    e = dict(STANDARD, **{k: v for k, v in (roh or {}).items() if k != 'ki'})
    e['ki'] = dict(STANDARD['ki'], **((roh or {}).get('ki') or {}))
    return e


def adresse(absender):
    return email.utils.parseaddr(absender or '')[1].lower()


def domain(absender):
    a = adresse(absender)
    return a.split('@', 1)[1] if '@' in a else ''


# --- Spam ------------------------------------------------------------------

def spam_wert(kopf, absender, betreff, hat_dokument=False, bekannt=False,
              kategorie=''):
    """Spam-Wert 0..1 mit Begruendung aus Mail-Kopf, Betreff und Kontext."""
    gruende = []
    wert = 0.0
    for name in SPAM_KOEPFE:
        if re.match(r'\s*(yes|true|junk|spam)\b', kopf.get(name, ''), re.I):
            return 1.0, ['Provider markiert Spam (%s)' % name]
    if kategorie == 'werbung':
        wert += 0.5
        gruende.append('Gmail: Werbung')
    elif kategorie == 'sozial':
        wert += 0.4
        gruende.append('Gmail: Soziale Netzwerke')
    if kopf.get('list-unsubscribe'):
        wert += 0.35
        gruende.append('Abmeldelink')
    if kopf.get('precedence', '').strip().lower() in ('bulk', 'list', 'junk'):
        wert += 0.25
        gruende.append('Massenversand')
    if kopf.get('list-id'):
        wert += 0.1
        gruende.append('Verteiler')
    text = ('%s %s' % (absender, betreff)).lower()
    treffer = [w for w in WERBEWOERTER if w in text]
    if treffer:
        wert += 0.2
        gruende.append('Werbewort: ' + treffer[0])
    if WERBE_ABSENDER.search(adresse(absender)):
        wert += 0.15
        gruende.append('Werbe-Absender')
    if EMOJI.search(betreff or ''):
        wert += 0.1
        gruende.append('Emoji im Betreff')
    if hat_dokument:
        wert -= 0.3
        gruende.append('hat Dokument')
    if bekannt:
        wert -= 0.5
        gruende.append('Absender bekannt')
    return max(0.0, min(1.0, wert)), gruende


# --- Beispiele aus vorhandenen Notizen (fuer KI und Regelvorschlaege) ------

@dataclass
class Beispiel:
    adresse: str
    betreff: str
    thema: str
    unterordner: str
    personen: tuple
    durch: str = ''  # eingeordnet_durch der Notiz
    ohne_anhang: bool = False  # Mail ohne Dokument, trotzdem abgelegt
    mail_drive: bool = False   # Mail selbst als PDF in Drive
    id: str = ''
    text: str = ''
    anhaenge: tuple = ()
    steuer: tuple = ()
    objekte: tuple = ()


def _absender_aus_text(text):
    m = re.search(r'^Von: (.+?)\s*$', text, re.M)
    return m.group(1) if m else ''


def unterordner_aus_ablage(ablage, thema_ablage, jahr=None):
    """'0-2026/31 EDV/ionos/2026' -> 'ionos/{jahr}' (Jahreszahl verallgemeinert)."""
    teile = [t for t in (ablage or '').split('/') if t]
    if len(teile) < 2 or teile[1] != thema_ablage:
        return ''
    rest = teile[2:]
    if jahr:
        rest = ['{jahr}' if t == str(jahr) else t for t in rest]
    return '/'.join(rest)


def beispiele_aus_notizen(pfade, themen):
    """Beispiele aus Notizen mit bekanntem Absender."""
    beispiele = []
    for pfad in pfade:
        with open(pfad, encoding='utf-8') as fh:
            try:
                n = nz.lesen(fh.read())
            except nz.FormatFehler:
                continue
        m = n.meta
        a = adresse(m.get('absender') or _absender_aus_text(n.text))
        if not a or not m.get('themen'):
            continue
        thema = m['themen'][0]
        jahr = getattr(m.get('erstellt'), 'year', None)
        uo = unterordner_aus_ablage(m.get('ablage'),
                                    themen.get(thema, {}).get('ablage', ''), jahr)
        beispiele.append(Beispiel(a, n.titel, thema, uo, tuple(m.get('personen') or ()),
                                  str(m.get('eingeordnet_durch') or ''),
                                  bool(m.get('ohne_anhang')), bool(m.get('mail_drive')),
                                  str(m.get('id') or ''), n.text,
                                  tuple(str(x) for x in m.get('anhaenge') or ()),
                                  tuple(m.get('steuer') or ()), tuple(m.get('objekte') or ())))
    return beispiele


ZIFFERNFOLGE = re.compile(r'[a-z0-9]*\d[a-z0-9]*(?:[\s/._-]+[a-z0-9]*\d[a-z0-9]*)*', re.I)


def nummern(text):
    """Nummern ab 6 Ziffern, so wie sie dastehen (624/220429-P, 702213446-Y-16)."""
    gefunden = set()
    for m in ZIFFERNFOLGE.finditer(str(text or '')):
        z = m.group(0).strip(' /._-')
        if sum(ch.isdigit() for ch in z) >= 6:
            gefunden.add(z)
    return gefunden


def _gemeinsame_nummer(gruppe, uo):
    """Eine Nummer, die in allen Beispielen der Gruppe steht, bevorzugt eine aus
    dem Unterordner (Vertragsnummer im Ordnernamen)."""
    def norm(z):
        return re.sub(r'[^a-z0-9]', '', z.lower())
    je = [{norm(z): z for z in nummern(' '.join([b.betreff, b.text] + list(b.anhaenge)))}
          for b in gruppe]
    if not je:
        return ''
    gemeinsam = set(je[0]).intersection(*je[1:])
    im_ordner = [z for z in gemeinsam if z in norm(uo)]
    wahl = sorted(im_ordner or gemeinsam, key=len, reverse=True)
    return je[0][wahl[0]] if wahl else ''


def regelvorschlaege(beispiele, regelwerk, eigene=(), abgelehnt=(), mindestens=2, bestand=()):
    """Regelentwuerfe (Format regeln.py) fuer Gruppen, die schon mindestens
    zweimal gleich eingeordnet wurden, aber von keiner Regel erfasst sind.
    Bedingung: eine gemeinsame Nummer (bevorzugt), sonst die Absender-Domain.
    Jeder Entwurf traegt die Eingaenge des Bestands, auf die er passt, und
    Regelkonflikte mit vorhandenen Regeln."""
    eigene = {e.lower() for e in eigene}
    gruppen = {}
    for b in beispiele:
        d = b.adresse.split('@', 1)[-1]
        if b.durch.startswith('regel/') or b.adresse in eigene:
            continue
        schluessel = (b.thema, b.unterordner)
        gruppen.setdefault(schluessel, []).append(b)
    vorschlaege = []
    namen = {r.get('name') for r in regelwerk.get('regeln') or []}
    for (thema, uo), gruppe in sorted(gruppen.items()):
        if len(gruppe) < mindestens:
            continue
        nummer = _gemeinsame_nummer(gruppe, uo)
        domains = {b.adresse.split('@', 1)[-1] for b in gruppe}
        if nummer and regeln.nummer_muster(nummer):
            wenn = [{'teil': 'ueberall', 'vergleich': 'nummer', 'werte': [nummer]}]
            grund = 'Nummer %s in %d abgelegten Mails' % (nummer, len(gruppe))
        elif len(domains) == 1 and not (domains & FREEMAIL):
            d = domains.pop()
            wenn = [{'teil': 'absender', 'vergleich': 'wort', 'werte': [d]}]
            grund = '%d Mails von %s, alle gleich abgelegt' % (len(gruppe), d)
        else:
            continue
        basis = re.sub(r'[^a-z0-9]+', '-', regeln.falten(uo.split('/')[-1] or thema)).strip('-')
        name = basis or thema
        i = 2
        while name in namen:
            name, i = '%s-%d' % (basis, i), i + 1
        if name in abgelehnt or any(a == wenn[0]['werte'][0] for a in abgelehnt):
            continue
        personen = sorted({p for b in gruppe for p in b.personen})
        dann = {'thema': thema, 'unterordner': uo, 'personen': personen}
        if all(b.ohne_anhang for b in gruppe):
            dann['ohne_anhang'] = True
        if all(b.mail_drive for b in gruppe):
            dann['mail_drive'] = True
        steuer = set.intersection(*[set(b.steuer) for b in gruppe])
        if steuer:
            dann['steuer'] = sorted(steuer)
        regel = {'name': name, 'art': 'ordner', 'wenn': wenn, 'dann': dann}
        # Schon von einer Regel erfasst? Dann kein Vorschlag.
        teile = regeln.Teile(absender=gruppe[0].adresse, betreff=gruppe[0].betreff,
                             text=gruppe[0].text, anhangname=' '.join(gruppe[0].anhaenge))
        if regeln.auswerten(teile, regelwerk).ziel:
            continue
        vorschlaege.append(dict(regel, grund=grund, herkunft='abgelegt',
                                **bestand_pruefung(regel, regelwerk, bestand)))
        namen.add(name)
    return vorschlaege


def bestand_pruefung(regel, regelwerk, bestand, wie_viele=8):
    """Beispiele und Regelkonflikte einer (neuen) Regel im Bestand."""
    passt, konflikte = regeln.pruefen_gegen_bestand(regel, regelwerk, bestand)
    kurz = lambda e: {k: e.get(k) for k in ('id', 'datum', 'absender', 'betreff', 'ziel')
                      if e.get(k)}
    return {'passt': len(passt), 'beispiele': [kurz(e) for e in passt[:wie_viele]],
            'konflikte': [dict(kurz(e), regeln=n) for e, n in konflikte[:wie_viele]],
            'wert_im_ordner': regeln.wert_im_ordner(regel)}


# --- KI (optional) ---------------------------------------------------------

class KI:
    """Fragt ein Sprachmodell ueber OpenRouter nach bis zu drei Vorschlaegen.

    Liegen zwei Vorschlaege nah beieinander (Abstand unter MEHRDEUTIG), ist
    die Ablage nicht eindeutig: die Konfidenz wird unter die Schwelle
    gedrueckt, die Mail landet mit allen Vorschlaegen im Eingang.
    """

    URL = 'https://openrouter.ai/api/v1/chat/completions'
    MEHRDEUTIG = 0.2

    BEISPIELE = 30  # so viele bisherige Ablagen gehen als Muster in die Anfrage

    def __init__(self, schluessel, modell, themen, personen, max_anfragen=20,
                 senden=None, hinweise='', unterordner=None, beispiele=(),
                 objekte=None, steuer=None):
        self.schluessel = schluessel
        self.modell = modell
        self.themen = themen
        self.personen = personen
        self.rest = max_anfragen
        self.rest_wichtig = max_anfragen  # eigenes Budget fuer Mails ohne Dokument
        self.hinweise = hinweise or ''
        self.unterordner = unterordner or {}  # thema -> bekannte Unterordner
        self.beispiele = self._auswahl(beispiele)
        self.objekte = objekte or {}    # schluessel -> {name: ...}
        self.steuer = steuer or {}      # schluessel -> {name: ...}
        self._senden = senden or self._http

    def _http(self, nutzlast):
        req = urllib.request.Request(
            self.URL, data=json.dumps(nutzlast).encode(),
            headers={'Authorization': 'Bearer ' + self.schluessel,
                     'Content-Type': 'application/json',
                     'X-Title': 'Second Brain'})
        with urllib.request.urlopen(req, timeout=60) as antwort:
            return json.load(antwort)

    @classmethod
    def _auswahl(cls, beispiele):
        """Je Domain und Ablage ein Beispiel, Haralds eigene Entscheidungen zuerst."""
        gesehen, auswahl = set(), []
        for b in sorted(beispiele, key=lambda b: b.durch != 'manuell'):
            k = (b.adresse.split('@')[-1], b.thema, b.unterordner)
            if k not in gesehen:
                gesehen.add(k)
                auswahl.append(b)
        return auswahl[:cls.BEISPIELE]

    def _prompt(self, absender, betreff, text, anhaenge, empfaenger='', ohne_dokument=False,
                hinweis='', anhangtext=''):
        zeilen = []
        for s, t in self.themen.items():
            z = '- %s (Ordner %s): %s' % (s, t.get('ablage', ''), t.get('zweck') or t.get('name', s))
            if self.unterordner.get(s):
                z += '; Unterordner: ' + ', '.join(sorted(self.unterordner[s])[:40])
            zeilen.append(z)
        hinweise = ('Ablageregeln des Haushalts:\n%s\n\n' % self.hinweise.strip()
                    if self.hinweise.strip() else '')
        if self.objekte or self.steuer:
            hinweise += (
                'Ein Beleg kann mehrere Bezuege haben. Nenne je Vorschlag zusaetzlich, falls '
                'passend: "weitere_themen" (andere Themen-Slugs, unter denen man die Mail auch '
                'sucht), "objekte" (worauf sie sich bezieht) und "steuer" (fuer welche Steuer-'
                'Angabe sie zaehlt; nur Schluessel aus der Liste der Steuerposten, Person beachten).'
                '\nObjekte: %s\nSteuerposten: %s\n\n' % (
                    ', '.join('%s (%s)' % (k, (o or {}).get('name', k)) for k, o in self.objekte.items()),
                    ', '.join('%s (%s)' % (k, (o or {}).get('name', k)) for k, o in self.steuer.items())))
        if hinweis:
            hinweise += 'Hinweis von Harald zu dieser Mail (hat Vorrang): %s\n\n' % hinweis
        if self.beispiele:
            hinweise += 'So wurde bisher abgelegt (Absender | Betreff -> Thema/Unterordner):\n%s\n\n' % (
                '\n'.join('- %s | %s -> %s%s%s%s' % (
                    b.adresse.split('@')[-1], b.betreff[:60], b.thema,
                    '/' + b.unterordner if b.unterordner else '',
                    ' (ohne Anhang)' if b.ohne_anhang else '',
                    ' (Mail als PDF)' if b.mail_drive else '') for b in self.beispiele))
        if ohne_dokument:
            hinweise += (
                'Diese Mail hat kein Dokument und landet sonst nur im Suchindex. Setze '
                '"wichtig": true nur, wenn sie aufbewahrt werden sollte, z. B. Buchungs-, '
                'Reservierungs- oder Auftragsbestaetigung, Vertrag, Kuendigung, Termin, '
                'Rechnung oder Beleg im Mailtext, Post von Behoerden, Bank oder Versicherung. '
                'Werbung, Newsletter, Versand- und Zustellmeldungen, Login-Codes und '
                'Bewertungsbitten sind nicht wichtig. Antworte zusaetzlich mit "wichtig": '
                'true/false.\n')
        hinweise += ('Setze "pdf": true, wenn die Mail selbst als Beleg in die Ablage '
                     'gehoert (z. B. Buchungsbestaetigung ohne Anhang), sonst false.\n')
        hinweise += (
            'Abgelegt wird im Jahresordner des Jahres, zu dem das Dokument gehoert, nicht '
            'des Empfangs: mit Geldfluss das Jahr der Zahlung bzw. Faelligkeit oder '
            'Abbuchung (Beitrag fuer 2027, faellig 01.01.2027 -> 2027; Abrechnung 2026 mit '
            'Nachzahlung 2027 -> 2027), ohne Geldfluss das Jahr, das es betrifft. Nenne es '
            'als "jahr" (Zahl) mit "jahr_grund" (kurz), oder 0, wenn nicht erkennbar. '
            'Betrifft das Dokument viele Jahre (Kauf-, Darlehens-, Miet-, Rentenvertrag, '
            'Grundbuch, Versicherungsschein, Foerderbescheid), setze "dauerhaft" auf eine '
            'kurze Begruendung, sonst "".\n\n')
        return (
            'Ordne diese Mail in ein persoenliches Archiv ein. Das Thema ist der '
            'Ordner der Ablage; ein Unterordner ist optional und darf mehrere Ebenen '
            'haben (mit / getrennt). Bevorzuge einen der genannten Unterordner; passt '
            'keiner, schlage einen neuen vor: Name der Gegenpartei und eine gleichbleibende '
            'Nummer aus der Mail (Vertrags-, Kunden- oder Mitgliedsnummer, nie eine '
            'Rechnungsnummer), z. B. "HUK_Kfz_624_220429-P", moeglichst unter einer '
            'passenden vorhandenen Ebene. '
            'Erfinde keine Themen.\n'
            'Themen:\n%s\nPersonen: %s\n\n%s'
            'Wenn mehrere Ordner in Frage kommen, nenne bis zu drei, den besten zuerst, '
            'jeweils mit eigener Konfidenz.\n'
            'Antworte nur mit JSON: {"spam": true/false, "wichtig": true/false, '
            '"pdf": true/false, "jahr": <Jahr oder 0>, "jahr_grund": "<kurz>", '
            '"dauerhaft": "<Grund oder leer>", "vorschlaege": [{"thema": "<slug>", '
            '"unterordner": "<Pfad oder leer>", "personen": ["<slug>"], '
            '"weitere_themen": ["<slug>"], "objekte": ["<slug>"], "steuer": ["<slug>"], '
            '"konfidenz": <0 bis 1>, "grund": "<ein Satz>"}]}\n\n'
            'Absender: %s\nEmpfaenger: %s\nBetreff: %s\nAnhaenge: %s\n\n%s%s'
            % ('\n'.join(zeilen), ', '.join(sorted(self.personen)), hinweise, absender,
               empfaenger, betreff, ', '.join(anhaenge) or 'keine', (text or '')[:1500],
               '\n\nText der Anhaenge:\n' + anhangtext[:2500] if anhangtext else ''))

    def _vorschlag(self, d, durch):
        thema = d.get('thema') or ''
        if thema not in self.themen:
            return None
        personen = [p for p in d.get('personen') or [] if p in self.personen]
        uo = str(d.get('unterordner') or '').strip('/')
        if not unterordner_gueltig(uo):
            uo = ''
        try:
            konf = max(0.0, min(1.0, float(d.get('konfidenz') or 0)))
        except (TypeError, ValueError):
            konf = 0.0
        auswahl = lambda feld, bekannt: [x for x in (d.get(feld) or [])
                                         if isinstance(x, str) and x in bekannt]
        return Vorschlag(thema=thema, unterordner=uo, personen=personen,
                         konfidenz=konf if personen else min(konf, 0.5),
                         durch=durch, grund=str(d.get('grund', '')),
                         weitere_themen=[t for t in auswahl('weitere_themen', self.themen)
                                         if t != thema],
                         objekte=auswahl('objekte', self.objekte),
                         steuer=auswahl('steuer', self.steuer))

    def frage(self, absender, betreff, text, anhaenge=(), empfaenger='', ohne_dokument=False,
              hinweis='', anhangtext=''):
        """Vorschlag oder None (Budget aufgebraucht, Fehler, unbrauchbare Antwort;
        ohne_dokument: auch wenn die KI die Mail nicht fuer wichtig haelt)."""
        rest = 'rest_wichtig' if ohne_dokument else 'rest'
        if getattr(self, rest) <= 0:
            return None
        setattr(self, rest, getattr(self, rest) - 1)
        try:
            antwort = self._senden({
                'model': self.modell,
                'messages': [{'role': 'user',
                              'content': self._prompt(absender, betreff, text, anhaenge,
                                                      empfaenger, ohne_dokument, hinweis,
                                                      anhangtext)}],
                'response_format': {'type': 'json_object'},
                'temperature': 0,
            })
            inhalt = antwort['choices'][0]['message']['content']
            daten = json.loads(inhalt[inhalt.find('{'):inhalt.rfind('}') + 1])
        except Exception as exc:  # KI ist optional: Fehler fuehren zur Rueckfrage
            print('KI nicht verfuegbar: %s' % exc)
            return None
        durch = 'ki/' + self.modell
        roh = daten.get('vorschlaege')
        if not isinstance(roh, list):  # aeltere Antwortform mit einem Vorschlag
            roh = [daten]
        if ohne_dokument and (daten.get('spam') or daten.get('wichtig') is not True):
            return None
        if daten.get('spam'):
            konf = max([float(d.get('konfidenz') or 0) for d in roh if isinstance(d, dict)] or [0])
            return Vorschlag(thema='', konfidenz=min(1.0, konf), durch=durch,
                             grund='Spam: ' + str((roh[0] if roh else {}).get('grund', '')))
        liste = [v for v in (self._vorschlag(d, durch) for d in roh[:3] if isinstance(d, dict))
                 if v is not None]
        if not liste:
            return None
        liste.sort(key=lambda v: -v.konfidenz)
        try:
            jahr = int(daten.get('jahr') or 0)
        except (TypeError, ValueError):
            jahr = 0
        for v in liste:
            v.mail_drive = daten.get('pdf') is True
            if 2000 <= jahr <= 2100:
                v.jahr, v.jahr_grund = jahr, str(daten.get('jahr_grund') or '')[:120]
            if isinstance(daten.get('dauerhaft'), str):
                v.dauerhaft = daten['dauerhaft'].strip()[:120]
        bester, rest = liste[0], liste[1:]
        bester.alternativen = rest
        if rest and bester.konfidenz - rest[0].konfidenz < self.MEHRDEUTIG:
            bester.grund += ' (mehrere Ordner moeglich)'
            bester.konfidenz = min(bester.konfidenz, 0.6)
        return bester


# --- Gesamtentscheidung ----------------------------------------------------

def unterordner_gueltig(uo):
    return regeln.unterordner_gueltig(uo)


KI_WICHTIG_SPAM = 0.3  # Mails ohne Dokument ab diesem Spam-Wert gar nicht erst der KI zeigen


def teile_aus_mail(mail):
    return regeln.Teile(absender=mail.absender or '', empfaenger=mail.empfaenger or '',
                        betreff=mail.betreff or '', text=mail.text or '',
                        anhangname=' '.join(n for n, _ in mail.dokumente),
                        anhangtext=getattr(mail, 'anhangtext', '') or '')


def _ordner_steuer(v, steuerposten):
    """Fester Steuerbezug des Ordners (config/steuerposten.yaml: ordner)."""
    if v is None or not getattr(v, 'thema', ''):
        return v
    from . import steuer
    for k in steuer.ordner_posten(steuerposten, v.thema, v.unterordner):
        if k not in v.steuer:
            v.steuer.append(k)
    return v


def _konflikt_vorschlag(r, treffer, standard_personen):
    d = r.get('dann') or {}
    return Vorschlag(thema=d.get('thema', ''), unterordner=str(d.get('unterordner') or ''),
                     personen=list(d.get('personen') or standard_personen), konfidenz=0.5,
                     durch='regel/' + r['name'],
                     grund='Regel %s (%s)' % (r['name'], regeln.treffer_text(treffer)),
                     weitere_themen=list(d.get('weitere_themen') or []),
                     objekte=list(d.get('objekte') or []), steuer=list(d.get('steuer') or []))


def einordnen(mail, regelwerk, einst, ki=None, steuerposten=None):
    """Ergebnis fuer eine Mail (mail.Mail) nach allen Stufen."""
    eigen = adresse(mail.absender) in {e.lower() for e in einst['eigene_adressen']}
    teile = teile_aus_mail(mail)
    std = regelwerk.get('standard_personen') or []
    auswertung = regeln.auswerten(teile, regelwerk)
    merkmal_treffer = [dict(t, regel=r['name']) for r, ts in auswertung.merkmal for t in ts]

    regel = regeln.einordnen(teile, mail.hat_dokument or eigen, regelwerk)
    if regel is not None and regel.aktion != regeln.OFFEN:
        return _ordner_steuer(regel, steuerposten)
    if regel is not None:  # Regelkonflikt: alle passenden Regeln als Vorschlaege
        liste = [_konflikt_vorschlag(r, t, std) for r, t in auswertung.ziel
                 if r.get('art', 'ordner') == 'ordner']
        v = liste[0] if liste else None
        if v is not None:
            v.alternativen = liste[1:]
            regeln.merkmale_anwenden(v, auswertung.merkmal, std)
            for x in liste:
                _ordner_steuer(x, steuerposten)
        regel.vorschlag = v
        return regel

    spam, gruende = spam_wert(mail.kopf, mail.absender, mail.betreff, mail.hat_dokument,
                              False, mail.kategorie)
    if spam >= einst['spam_schwelle'] and not eigen:
        return regeln.Ergebnis(regeln.VERWERFEN, 'Spam-Wert %.2f: %s'
                               % (spam, ', '.join(gruende)),
                               konfidenz=spam, durch='spam', treffer=merkmal_treffer)

    anhaenge = [n for n, _ in mail.dokumente]
    if not (mail.hat_dokument or eigen):
        if ki is not None and spam < KI_WICHTIG_SPAM:
            kv = ki.frage(mail.absender, mail.betreff, mail.text, [], mail.empfaenger,
                          ohne_dokument=True)
            if kv is not None and kv.thema:
                regeln.merkmale_anwenden(kv, auswertung.merkmal, std)
                _ordner_steuer(kv, steuerposten)
                return regeln.Ergebnis(regeln.OFFEN, 'KI hält die Mail für wichtig: ' + kv.grund,
                                       vorschlag=kv, konfidenz=kv.konfidenz, spam=spam,
                                       treffer=merkmal_treffer)
        return regeln.Ergebnis(regeln.INDEX, 'keine Regel, kein Dokument-Anhang', spam=spam)

    kv = None
    if ki is not None:
        kv = ki.frage(mail.absender, mail.betreff, mail.text, anhaenge, mail.empfaenger,
                      anhangtext=teile.anhangtext)
        if kv is not None and not kv.thema and kv.konfidenz >= einst['schwelle'] and not eigen:
            return regeln.Ergebnis(regeln.VERWERFEN, kv.grund, konfidenz=kv.konfidenz,
                                   durch=kv.durch)
        if kv is not None and not kv.thema:
            kv = None
    if kv is not None:
        regeln.merkmale_anwenden(kv, auswertung.merkmal, std)
        for x in [kv] + list(kv.alternativen):
            _ordner_steuer(x, steuerposten)
    grund = ('an dich selbst gesendet' if eigen and kv is None
             else 'keine Regel passt' + (', Vorschlag der KI' if kv is not None else ''))
    return regeln.Ergebnis(regeln.OFFEN, grund, vorschlag=kv,
                           konfidenz=kv.konfidenz if kv else 0.0, treffer=merkmal_treffer)
