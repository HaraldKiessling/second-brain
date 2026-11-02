"""Regeln: ordnen einen Eingang ohne KI ein (ADR 0004).

Eine Regel hat zwei Teile:

  wenn  - Bedingungen an Bestandteile des Eingangs. Alle Bedingungen muessen
          zutreffen; innerhalb einer Bedingung reicht einer der Werte.
  dann  - Ordner und Merkmale.

Bestandteile (TEILE): absender, empfaenger, betreff, text (Mailtext),
anhangname, anhangtext (Text der PDFs, notfalls per Texterkennung) und
ueberall (alle zusammen). Andere Quellen (Drive-Eingangsmappe, Konten,
Portale) liefern dieselben Teile, soweit sie sie haben.

Vergleiche (VERGLEICHE):
  wort      - der Wert steht als ganzes Wort darin (Standard)
  wortteil  - der Wert steht irgendwo darin (nur ausdruecklich)
  nummer    - Ziffern und Buchstaben in dieser Folge, Trennzeichen egal
              (624/220429-P = 624 220429 P = 624220429P)
  nicht     - keiner der Werte steht als ganzes Wort darin

Arten (ARTEN):
  ordner       - bestimmt den Drive-Ordner (dann.thema, dann.unterordner)
  aussortieren - verwirft den Eingang (bleibt als Indexeintrag auffindbar)
  merkmal      - ergaenzt nur Personen, weitere Themen, Objekte, Steuerbezug,
                 Mail als PDF, ohne Anhang, Dauerablage

Eindeutig: Auf einen Eingang darf genau eine Ordner- oder Aussortier-Regel
(Zielregel) passen. Passen mehrere, ist das ein Regelkonflikt; der Eingang
kommt mit allen passenden Regeln nach "Zu erledigen". Merkmalregeln duerfen
zusaetzlich passen.

Der Unterordner einer Ordnerregel soll einen Wert aus dem Eingang enthalten
(Vertrags-, Kunden-, Mitgliedsnummer oder Name der Gegenpartei), damit die
Ablage aus der Mail ableitbar ist; wert_im_ordner() prueft das.
"""

import re
from dataclasses import dataclass, field

VERWERFEN = 'verwerfen'
NOTIZ = 'notiz'
OFFEN = 'offen'
INDEX = 'index'

TEILE = ('absender', 'empfaenger', 'betreff', 'text', 'anhangname', 'anhangtext')
ALLE_TEILE = TEILE + ('ueberall',)
TEIL_NAMEN = {'absender': 'Absender', 'empfaenger': 'Empfänger', 'betreff': 'Betreff',
              'text': 'Mailtext', 'anhangname': 'Anhangname', 'anhangtext': 'Anhangtext',
              'ueberall': 'Mail oder Anhang'}
VERGLEICHE = ('wort', 'wortteil', 'nummer', 'nicht')
ARTEN = ('ordner', 'aussortieren', 'merkmal')
ZIELARTEN = ('ordner', 'aussortieren')
MERKMALE = ('personen', 'weitere_themen', 'objekte', 'steuer')
SCHALTER = ('mail_drive', 'ohne_anhang')
VERSION = 3
MIN_NUMMER = 5


@dataclass
class Ergebnis:
    aktion: str
    grund: str
    regel: str = ''
    thema: str = ''
    unterordner: str = ''
    personen: list = field(default_factory=list)
    konfidenz: float = 1.0
    durch: str = ''          # wer entschieden hat: regel/<name>, spam, ki/<modell>
    vorschlag: object = None  # einordnen.Vorschlag bei offen
    spam: float = 0.0
    mail_drive: bool = False  # Mail selbst als PDF in die Drive-Ablage
    weitere_themen: list = field(default_factory=list)  # Schlagworte neben dem Hauptthema
    objekte: list = field(default_factory=list)         # config/bezuege.yaml: objekte
    steuer: list = field(default_factory=list)          # config/steuerposten.yaml
    jahr: int = 0             # Zugehoerigkeitsjahr laut KI (0 = nicht genannt), siehe jahr.py
    jahr_grund: str = ''
    dauerhaft: str = ''       # Grund, warum es zusaetzlich nach 0000-dauerhaft gehoert
    treffer: list = field(default_factory=list)   # [{regel, teil, wert}] woran es erkannt wurde
    konflikt: list = field(default_factory=list)  # Namen der Zielregeln bei Regelkonflikt


# --- Bestandteile ----------------------------------------------------------

@dataclass
class Teile:
    """Die Bestandteile eines Eingangs, wie Regeln sie pruefen."""
    absender: str = ''
    empfaenger: str = ''
    betreff: str = ''
    text: str = ''
    anhangname: str = ''
    anhangtext: str = ''

    @classmethod
    def aus_dict(cls, d):
        return cls(**{t: str(d.get(t) or '') for t in TEILE})

    def als_dict(self):
        return {t: getattr(self, t) for t in TEILE}

    def teil(self, name):
        if name == 'ueberall':
            return '\n'.join(getattr(self, t) for t in TEILE)
        return getattr(self, name, '')


def falten(text):
    """Klein, Umlaute ausgeschrieben, damit 'Gebäude' und 'gebaeude' gleich sind."""
    t = str(text or '').lower()
    for a, b in (('ä', 'ae'), ('ö', 'oe'), ('ü', 'ue'), ('ß', 'ss')):
        t = t.replace(a, b)
    return t


def nummer_muster(wert):
    """Nummer als Regex: Trennzeichen (Leerzeichen / . _ -) sind egal, davor und
    danach steht kein Buchstabe und keine Ziffer. None, wenn zu kurz."""
    zeichen = [z for z in falten(wert) if z.isalnum()]
    if len(zeichen) < MIN_NUMMER:
        return None
    return re.compile(r'(?<![a-z0-9])' + r'[\s/._-]*'.join(map(re.escape, zeichen))
                      + r'(?![a-z0-9])')


def _wort_muster(wert):
    w = falten(wert).strip()
    if not w:
        return None
    teile = [re.escape(x) for x in w.split()]
    return re.compile(r'(?<![a-z0-9])' + r'\s+'.join(teile) + r'(?![a-z0-9])')


def _passt(vergleich, wert, text):
    if vergleich == 'wortteil':
        w = falten(wert).strip()
        return bool(w) and w in text
    if vergleich == 'nummer':
        m = nummer_muster(wert)
        return bool(m and m.search(text))
    m = _wort_muster(wert)  # wort und nicht
    return bool(m and m.search(text))


def bedingung_trifft(b, teile, cache=None):
    """Liefert den passenden Wert (str), '' fuer eine erfuellte nicht-Bedingung,
    oder None, wenn die Bedingung nicht zutrifft."""
    name = b.get('teil') or 'ueberall'
    cache = cache if cache is not None else {}
    if name not in cache:
        cache[name] = falten(teile.teil(name))
    text = cache[name]
    vergleich = b.get('vergleich') or 'wort'
    werte = [str(w) for w in b.get('werte') or [] if str(w).strip()]
    if vergleich == 'nicht':
        return None if any(_passt('wort', w, text) for w in werte) else ''
    for w in werte:
        if _passt(vergleich, w, text):
            return w
    return None


def regel_trifft(regel, teile, cache=None):
    """Liste der Treffer [{teil, wert}] oder None, wenn die Regel nicht passt."""
    wenn = regel.get('wenn') or []
    if not any((b.get('vergleich') or 'wort') != 'nicht' for b in wenn):
        return None  # nur Ausschluesse passen auf fast alles: nie
    cache = cache if cache is not None else {}
    treffer = []
    for b in wenn:
        w = bedingung_trifft(b, teile, cache)
        if w is None:
            return None
        teil = b.get('teil') or 'ueberall'
        if (b.get('vergleich') or 'wort') == 'nicht':
            treffer.append({'teil': teil, 'wert': 'ohne ' + ', '.join(map(str, b.get('werte') or []))})
        else:
            treffer.append({'teil': teil, 'wert': w})
    return treffer


def treffer_text(treffer):
    """'Betreff: 624/220429-P; Absender: huk-coburg.de'"""
    return '; '.join('%s: %s' % (TEIL_NAMEN.get(t['teil'], t['teil']), t['wert'])
                     for t in treffer)


@dataclass
class Auswertung:
    ziel: list = field(default_factory=list)     # [(regel, treffer)] Ordner/Aussortieren
    merkmal: list = field(default_factory=list)  # [(regel, treffer)]

    @property
    def konflikt(self):
        return len(self.ziel) > 1


def auswerten(teile, regelwerk):
    a = Auswertung()
    cache = {}
    for r in regelwerk.get('regeln') or []:
        t = regel_trifft(r, teile, cache)
        if t is None:
            continue
        if r.get('art', 'ordner') in ZIELARTEN:
            a.ziel.append((r, t))
        else:
            a.merkmal.append((r, t))
    return a


def merkmale_anwenden(ziel, merkmale, standard_personen=()):
    """Merkmale der Merkmalregeln auf ein Ergebnis oder einen Vorschlag
    (Felder personen, weitere_themen, objekte, steuer, mail_drive, dauerhaft)
    uebertragen. Personen: die der Ordnerregel plus die der Merkmalregeln;
    nennt keine Regel Personen, gelten die Standardpersonen."""
    for r, _ in merkmale:
        d = r.get('dann') or {}
        for k in MERKMALE:
            liste = getattr(ziel, k)
            for x in d.get(k) or []:
                if x not in liste:
                    liste.append(x)
        if d.get('mail_drive'):
            ziel.mail_drive = True
        if d.get('dauerhaft') and not ziel.dauerhaft:
            ziel.dauerhaft = str(d['dauerhaft'])
    if not ziel.personen:
        ziel.personen = list(standard_personen)
    return ziel


def einordnen(teile, hat_dokument, regelwerk):
    """Ergebnis nach den Regeln, oder None, wenn keine Zielregel passt.

    Merkmalregeln allein entscheiden nichts; sie werden in einordnen.py auch
    auf KI-Vorschlaege angewendet (auswerten().merkmal)."""
    a = auswerten(teile, regelwerk)
    std = regelwerk.get('standard_personen') or []
    alle_treffer = [dict(t, regel=r['name']) for r, ts in a.ziel + a.merkmal for t in ts]
    if not a.ziel:
        return None
    if a.konflikt:
        namen = [r['name'] for r, _ in a.ziel]
        return Ergebnis(OFFEN, 'Regelkonflikt: ' + ', '.join(namen), treffer=alle_treffer,
                        konflikt=namen, konfidenz=0.0)
    r, t = a.ziel[0]
    name = r['name']
    if r.get('art') == 'aussortieren':
        return Ergebnis(VERWERFEN, 'Regel %s (%s)' % (name, treffer_text(t)), regel=name,
                        durch='regel/' + name, treffer=alle_treffer)
    d = r.get('dann') or {}
    ohne = bool(d.get('ohne_anhang')) or any((m.get('dann') or {}).get('ohne_anhang')
                                             for m, _ in a.merkmal)
    if not hat_dokument and not ohne:
        return Ergebnis(INDEX, 'Regel %s, aber kein Dokument' % name, regel=name,
                        thema=d.get('thema', ''), durch='regel/' + name, treffer=alle_treffer)
    e = Ergebnis(NOTIZ, 'Regel %s (%s)' % (name, treffer_text(t)), regel=name,
                 thema=d.get('thema', ''), unterordner=str(d.get('unterordner') or ''),
                 personen=list(d.get('personen') or []), durch='regel/' + name,
                 mail_drive=bool(d.get('mail_drive')),
                 weitere_themen=list(d.get('weitere_themen') or []),
                 objekte=list(d.get('objekte') or []), steuer=list(d.get('steuer') or []),
                 dauerhaft=str(d.get('dauerhaft') or ''), treffer=alle_treffer)
    return merkmale_anwenden(e, a.merkmal, std)


# --- Pruefen und Bestand ---------------------------------------------------

def wert_im_ordner(regel):
    """Steht ein Wert aus den Bedingungen im Unterordner (Trennzeichen egal)?"""
    uo = falten((regel.get('dann') or {}).get('unterordner') or '')
    kurz = re.sub(r'[^a-z0-9]', '', uo)
    for b in regel.get('wenn') or []:
        if (b.get('vergleich') or 'wort') == 'nicht':
            continue
        for w in b.get('werte') or []:
            f = falten(w)
            if b.get('vergleich') == 'nummer':
                z = re.sub(r'[^a-z0-9]', '', f)
                if z and z in kurz:
                    return True
                continue
            # Domain "huk-coburg.de" -> "huk-coburg", "huk", "coburg"
            for teil in re.split(r'[^a-z0-9]+', f.rsplit('.', 1)[0] if '.' in f else f):
                if len(teil) >= 3 and teil in kurz:
                    return True
    return False


def regel_fehler(regel, themen=(), personen=(), objekte=(), steuer=(), namen=()):
    """Fehlertexte fuer eine Regel (leer = in Ordnung)."""
    f = []
    name = regel.get('name')
    if not name or not re.fullmatch(r'[a-z0-9][a-z0-9._-]*', str(name)):
        f.append('Name fehlt oder ungueltig (a-z, 0-9, -)')
    if name in namen:
        f.append('Name doppelt')
    art = regel.get('art', 'ordner')
    if art not in ARTEN:
        f.append('Art unbekannt: %s' % art)
    wenn = regel.get('wenn') or []
    if not any((b.get('vergleich') or 'wort') != 'nicht' for b in wenn):
        f.append('mindestens eine Bedingung, die etwas verlangt (nicht nur "kommt nicht vor")')
    for b in wenn:
        if (b.get('teil') or 'ueberall') not in ALLE_TEILE:
            f.append('Teil unbekannt: %s' % b.get('teil'))
        if (b.get('vergleich') or 'wort') not in VERGLEICHE:
            f.append('Vergleich unbekannt: %s' % b.get('vergleich'))
        werte = [w for w in b.get('werte') or [] if str(w).strip()]
        if not werte:
            f.append('Bedingung ohne Werte')
        if b.get('vergleich') == 'nummer':
            for w in werte:
                if nummer_muster(w) is None:
                    f.append('Nummer zu kurz (mind. %d Zeichen): %s' % (MIN_NUMMER, w))
    d = regel.get('dann') or {}
    if art == 'ordner':
        if themen and d.get('thema') not in themen:
            f.append('Thema unbekannt: %s' % d.get('thema'))
        if not unterordner_gueltig(str(d.get('unterordner') or '')):
            f.append('Unterordner ungueltig: %s' % d.get('unterordner'))
    elif art == 'merkmal':
        if d.get('thema') or d.get('unterordner'):
            f.append('Merkmalregel darf keinen Ordner setzen')
        if not any(d.get(k) for k in MERKMALE + SCHALTER + ('dauerhaft',)):
            f.append('Merkmalregel setzt nichts')
    for feld, bekannt, art_name in (('personen', personen, 'Person'),
                                    ('weitere_themen', themen, 'Thema'),
                                    ('objekte', objekte, 'Objekt'),
                                    ('steuer', steuer, 'Steuerposten')):
        if not bekannt:
            continue
        for x in d.get(feld) or []:
            if x not in bekannt:
                f.append('%s unbekannt: %s' % (art_name, x))
    return f


def unterordner_gueltig(uo):
    """Mehrstufig mit /, ohne leere Teile, .. oder fuehrenden /."""
    if not uo:
        return True
    return all(t.strip() and t not in ('.', '..') and '\\' not in t for t in uo.split('/'))


def pruefen_gegen_bestand(regel, regelwerk, bestand):
    """Auf welche Eingaenge des Bestands passt die Regel, und wo gibt es einen
    Regelkonflikt mit einer anderen Zielregel? bestand: Liste von dicts mit den
    TEILE-Feldern (siehe daten.bestand). Liefert (passt, konflikte):
    passt = [eintrag], konflikte = [(eintrag, [andere Regelnamen])]."""
    andere = [r for r in regelwerk.get('regeln') or []
              if r.get('name') != regel.get('name') and r.get('art', 'ordner') in ZIELARTEN]
    ziel = regel.get('art', 'ordner') in ZIELARTEN
    passt, konflikte = [], []
    for e in bestand:
        teile = Teile.aus_dict(e)
        cache = {}
        if regel_trifft(regel, teile, cache) is None:
            continue
        passt.append(e)
        if ziel:
            namen = [r['name'] for r in andere if regel_trifft(r, teile, cache) is not None]
            if namen:
                konflikte.append((e, namen))
    return passt, konflikte


def leeres_regelwerk(standard_personen=()):
    return {'version': VERSION, 'standard_personen': list(standard_personen), 'regeln': []}
