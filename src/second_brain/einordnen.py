"""Einordnen in Stufen: jede Mail bekommt eine Entscheidung mit Konfidenz.

Stufen (die erste, die sicher genug ist, gewinnt):
  1. Regel        - feste Regel aus regeln/mail.json, Konfidenz 1,0
  2. Spam         - Spam-Wert aus Mail-Kopf und Betreff; ab spam_schwelle
                    verworfen (bleibt aber als Indexeintrag mit Grund erhalten)
  3. Heuristik    - Lernen aus vorhandenen Notizen (gleicher Absender, gleiche
                    Domain), Ablagewissen (bekannte Gegenparteien aus Drive-Ablage
                    und Steuererklaerungen, config/ablagewissen.yaml) und
                    Stichwoerter der Themen
  4. KI           - optional (config/einordnen.yaml ki.aktiv), nur wenn die
                    Heuristik nicht reicht
  5. Rueckfrage   - unter der Schwelle: Eingang mit Vorschlag, sonst Index

Die Einstellungen stehen in config/einordnen.yaml (siehe STANDARD).
"""

import email.utils
import json
import os
import re
import urllib.request
from collections import Counter
from dataclasses import dataclass, field

from . import notiz as nz
from . import regeln

STANDARD = {
    'schwelle': 0.8,       # ab dieser Konfidenz ohne Rueckfrage ablegen
    'vorschlag_ab': 0.5,   # darunter ohne Dokument nur Indexeintrag
    'spam_schwelle': 0.7,  # ab diesem Spam-Wert verwerfen
    'ki': {'aktiv': False, 'modell': '', 'max_pro_lauf': 20},
}

FREEMAIL = {'gmail.com', 'googlemail.com', 'gmx.de', 'gmx.net', 'gmx.at', 'web.de',
            't-online.de', 'outlook.com', 'outlook.de', 'hotmail.com', 'hotmail.de',
            'live.de', 'yahoo.com', 'yahoo.de', 'icloud.com', 'me.com', 'aol.com',
            'posteo.de', 'mailbox.org', 'freenet.de', 'arcor.de'}

WERBEWOERTER = ('newsletter', 'angebot', 'rabatt', 'gutschein', 'sale', 'deal',
                'gratis', 'gewinnspiel', 'exklusiv', 'nur heute', 'black friday',
                'sparen sie', '% auf', 'jetzt zugreifen', 'webinar')

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

    def als_dict(self):
        return {'thema': self.thema, 'unterordner': self.unterordner,
                'personen': list(self.personen), 'konfidenz': round(self.konfidenz, 2),
                'durch': self.durch, 'grund': self.grund}


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
    if hat_dokument:
        wert -= 0.3
        gruende.append('hat Dokument')
    if bekannt:
        wert -= 0.5
        gruende.append('Absender bekannt')
    return max(0.0, min(1.0, wert)), gruende


# --- Heuristik: Lernen aus vorhandenen Notizen -----------------------------

@dataclass
class Beispiel:
    adresse: str
    betreff: str
    thema: str
    unterordner: str
    personen: tuple


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
    """Lernbeispiele aus Notizen mit bekanntem Absender."""
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
        beispiele.append(Beispiel(a, n.titel, thema, uo, tuple(m.get('personen') or ())))
    return beispiele


class Lerner:
    """Schlaegt Thema, Unterordner und Personen aus frueheren Notizen vor.

    Konfidenz = Uebereinstimmungen / (Beispiele + 0,5): eine Notiz desselben
    Absenders ergibt 0,67, zwei gleiche 0,8, drei 0,86. Gleiche Domain zaehlt
    85 %. Ablagewissen (0,7) und Stichwoerter (0,45) bleiben unter der
    Standardschwelle: sie liefern einen guten Vorschlag, die erste Mail wird
    aber bestaetigt. Der spezifischste Hinweis gewinnt; stuetzt ein weiterer
    Hinweis dasselbe Thema, kommen 0,15 hinzu. So reicht eine Bestaetigung
    eines Ablagewissen-Vorschlags, sonst zwei gleiche Entscheidungen.
    """

    def __init__(self, beispiele, themen, standard_personen=(), wissen=()):
        self.themen = themen
        self.standard_personen = list(standard_personen)
        self.wissen = list(wissen)
        self.nach_adresse = {}
        self.nach_domain = {}
        for b in beispiele:
            self.nach_adresse.setdefault(b.adresse, []).append(b)
            d = b.adresse.split('@', 1)[-1]
            if d not in FREEMAIL:
                self.nach_domain.setdefault(d, []).append(b)

    def kennt(self, absender):
        return adresse(absender) in self.nach_adresse or domain(absender) in self.nach_domain

    @staticmethod
    def _mehrheit(gruppe, faktor, durch, wer):
        zaehler = Counter((b.thema, b.unterordner, b.personen) for b in gruppe)
        (thema, uo, personen), k = zaehler.most_common(1)[0]
        return Vorschlag(thema=thema, unterordner=uo, personen=list(personen),
                         konfidenz=faktor * k / (len(gruppe) + 0.5), durch=durch,
                         grund='%d von %d Notizen von %s' % (k, len(gruppe), wer))

    def vorschlag(self, absender, betreff, anhaenge=()):
        a, d = adresse(absender), domain(absender)
        gelernt = None  # aus eigenen Entscheidungen: Absender vor Domain
        if a in self.nach_adresse:
            gelernt = self._mehrheit(self.nach_adresse[a], 1.0, 'heuristik/absender', a)
        elif d in self.nach_domain:
            gelernt = self._mehrheit(self.nach_domain[d], 0.85, 'heuristik/domain', d)
        wissen = (self._ablagewissen(absender, betreff, anhaenge)
                  + self._stichwoerter(betreff))
        if gelernt is None:
            return max(wissen, key=lambda w: w.konfidenz) if wissen else None
        # Eigene Entscheidungen gehen vor; stuetzt das Wissen dasselbe Thema,
        # steigt die Konfidenz.
        stuetze = next((w for w in wissen if w.thema == gelernt.thema), None)
        if stuetze is not None:
            gelernt.konfidenz = min(0.95, gelernt.konfidenz + 0.15)
            gelernt.grund += '; passt zu ' + stuetze.grund
        return gelernt

    def _ablagewissen(self, absender, betreff, anhaenge):
        text = ' '.join([absender or '', betreff or ''] + list(anhaenge)).lower()
        treffer = []
        for w in self.wissen:
            gefunden = [str(m) for m in w.get('muster') or [] if str(m).lower() in text]
            if gefunden:
                treffer.append((len(gefunden), w, gefunden))
        if not treffer:
            return []
        treffer.sort(key=lambda t: -t[0])
        n, w, gefunden = treffer[0]
        label = lambda x: (x['thema'], x.get('unterordner', ''))
        mehrdeutig = any(m == n and label(x) != label(w) for m, x, _ in treffer[1:])
        return [Vorschlag(thema=w['thema'], unterordner=w.get('unterordner', ''),
                          personen=list(w.get('personen') or self.standard_personen),
                          konfidenz=0.4 if mehrdeutig else 0.7,
                          durch='heuristik/ablagewissen',
                          grund='bekannt aus %s: %s' % (w.get('quelle', 'Ablage'),
                                                        w.get('name') or ', '.join(gefunden)))]

    def _stichwoerter(self, betreff):
        be = (betreff or '').lower()
        treffer = []
        for slug, t in self.themen.items():
            woerter = [w for w in (t.get('stichwoerter') or []) if w.lower() in be]
            if woerter:
                treffer.append((len(woerter), slug, woerter))
        if not treffer:
            return []
        treffer.sort(reverse=True)
        n, slug, woerter = treffer[0]
        konf = 0.45 if len(treffer) == 1 else 0.3
        return [Vorschlag(thema=slug, personen=list(self.standard_personen),
                          konfidenz=konf, durch='heuristik/stichwort',
                          grund='Stichwort im Betreff: ' + ', '.join(woerter))]


# --- KI (optional) ---------------------------------------------------------

class KI:
    """Fragt ein Sprachmodell ueber OpenRouter nach einem Vorschlag."""

    URL = 'https://openrouter.ai/api/v1/chat/completions'

    def __init__(self, schluessel, modell, themen, personen, max_anfragen=20,
                 senden=None):
        self.schluessel = schluessel
        self.modell = modell
        self.themen = themen
        self.personen = personen
        self.rest = max_anfragen
        self._senden = senden or self._http

    def _http(self, nutzlast):
        req = urllib.request.Request(
            self.URL, data=json.dumps(nutzlast).encode(),
            headers={'Authorization': 'Bearer ' + self.schluessel,
                     'Content-Type': 'application/json',
                     'X-Title': 'Second Brain'})
        with urllib.request.urlopen(req, timeout=60) as antwort:
            return json.load(antwort)

    def _prompt(self, absender, betreff, text, anhaenge):
        themen = '\n'.join('- %s: %s' % (s, t.get('zweck') or t.get('name', s))
                           for s, t in self.themen.items())
        return (
            'Ordne diese Mail in ein persoenliches Archiv ein.\n'
            'Themen:\n%s\nPersonen: %s\n\n'
            'Antworte nur mit JSON: {"thema": "<slug oder leer>", '
            '"unterordner": "<kurzer Pfad, z. B. firma/rechnungen, oder leer>", '
            '"personen": ["<slug>"], "spam": true/false, '
            '"konfidenz": <0 bis 1>, "grund": "<ein Satz>"}\n\n'
            'Absender: %s\nBetreff: %s\nAnhaenge: %s\n\n%s'
            % (themen, ', '.join(sorted(self.personen)), absender, betreff,
               ', '.join(anhaenge) or 'keine', (text or '')[:1500]))

    def frage(self, absender, betreff, text, anhaenge=()):
        """Vorschlag oder None (Budget aufgebraucht, Fehler, unbrauchbare Antwort)."""
        if self.rest <= 0:
            return None
        self.rest -= 1
        try:
            antwort = self._senden({
                'model': self.modell,
                'messages': [{'role': 'user',
                              'content': self._prompt(absender, betreff, text, anhaenge)}],
                'response_format': {'type': 'json_object'},
                'temperature': 0,
            })
            inhalt = antwort['choices'][0]['message']['content']
            daten = json.loads(inhalt[inhalt.find('{'):inhalt.rfind('}') + 1])
        except Exception as exc:  # KI ist optional: Fehler fuehren zur Rueckfrage
            print('KI nicht verfuegbar: %s' % exc)
            return None
        konf = max(0.0, min(1.0, float(daten.get('konfidenz') or 0)))
        durch = 'ki/' + self.modell
        if daten.get('spam'):
            return Vorschlag(thema='', konfidenz=konf, durch=durch,
                             grund='Spam: ' + str(daten.get('grund', '')))
        thema = daten.get('thema') or ''
        if thema not in self.themen:
            return None
        personen = [p for p in daten.get('personen') or [] if p in self.personen]
        uo = str(daten.get('unterordner') or '')
        if not unterordner_gueltig(uo):
            uo = ''
        return Vorschlag(thema=thema, unterordner=uo, personen=personen,
                         konfidenz=konf if personen else min(konf, 0.5),
                         durch=durch, grund=str(daten.get('grund', '')))


# --- Gesamtentscheidung ----------------------------------------------------

def unterordner_gueltig(uo):
    """Mehrstufig mit /, ohne leere Teile, .. oder fuehrenden /."""
    if not uo:
        return True
    teile = uo.split('/')
    return all(t.strip() and t not in ('.', '..') and '\\' not in t for t in teile)


def einordnen(mail, regelwerk, lerner, einst, ki=None):
    """Ergebnis fuer eine Mail (mail.Mail) nach allen Stufen."""
    regel = regeln.einordnen(mail.absender, mail.betreff, mail.hat_dokument, regelwerk)
    if regel.aktion in (regeln.VERWERFEN, regeln.NOTIZ):
        regel.durch = 'regel/' + regel.regel if regel.regel else 'regel/verwerfen'
        return regel

    spam, gruende = spam_wert(mail.kopf, mail.absender, mail.betreff, mail.hat_dokument,
                              lerner.kennt(mail.absender), mail.kategorie)
    if spam >= einst['spam_schwelle']:
        return regeln.Ergebnis(regeln.VERWERFEN, 'Spam-Wert %.2f: %s'
                               % (spam, ', '.join(gruende)),
                               konfidenz=spam, durch='heuristik/spam')

    vorschlag = lerner.vorschlag(mail.absender, mail.betreff,
                                 [n for n, _ in mail.anhaenge])
    versicherung = regel.aktion == regeln.OFFEN and regel.grund.startswith('Versicherung')
    sicher = lambda v: v is not None and v.thema and v.konfidenz >= einst['schwelle']

    if not versicherung and sicher(vorschlag):
        return _notiz(vorschlag)

    if (ki is not None and not versicherung
            and (mail.hat_dokument or vorschlag is not None)):
        kv = ki.frage(mail.absender, mail.betreff, mail.text,
                      [n for n, _ in mail.anhaenge])
        if kv is not None and not kv.thema and kv.konfidenz >= einst['schwelle']:
            return regeln.Ergebnis(regeln.VERWERFEN, kv.grund,
                                   konfidenz=kv.konfidenz, durch=kv.durch)
        if sicher(kv):
            return _notiz(kv)
        if kv is not None and kv.thema and (vorschlag is None
                                            or kv.konfidenz > vorschlag.konfidenz):
            vorschlag = kv

    if mail.hat_dokument or versicherung or (
            vorschlag is not None and vorschlag.konfidenz >= einst['vorschlag_ab']):
        if versicherung or vorschlag is None:
            grund = regel.grund
        else:
            grund = 'Konfidenz %.2f unter Schwelle %.2f' % (vorschlag.konfidenz,
                                                          einst['schwelle'])
        return regeln.Ergebnis(regeln.OFFEN, grund, vorschlag=vorschlag,
                               konfidenz=vorschlag.konfidenz if vorschlag else 0.0)

    return regeln.Ergebnis(regeln.INDEX, regel.grund, spam=spam)


def _notiz(v):
    return regeln.Ergebnis(regeln.NOTIZ, v.grund, thema=v.thema,
                           unterordner=v.unterordner, personen=list(v.personen),
                           konfidenz=v.konfidenz, durch=v.durch)
