"""Kommandozeile: second-brain <befehl> ..."""

import argparse
import datetime
import os
import sys

from . import daten


def _pruefen(args):
    fehler = daten.pruefen(args.daten)
    for pfad, meldung in fehler:
        print('%s: %s' % (pfad, meldung))
    anzahl = sum(1 for _ in daten.notiz_pfade(args.daten))
    print('%d Notizen geprueft, %d Fehler' % (anzahl, len(fehler)))
    return 1 if fehler else 0


def _ki(wurzel, einst):
    """KI-Stufe, wenn in config/einordnen.yaml aktiv und Schluessel gesetzt."""
    from . import einordnen
    schluessel = os.environ.get('OPENROUTER_API_KEY')
    if not (einst['ki']['aktiv'] and schluessel):
        return None
    b = daten.bezuege(wurzel)
    return einordnen.KI(schluessel, einst['ki']['modell'], daten.themen(wurzel),
                        daten.kontext(wurzel).personen, einst['ki']['max_pro_lauf'],
                        hinweise=einst['ki']['hinweise'],
                        unterordner=daten.bekannte_unterordner(wurzel),
                        objekte=b['objekte'], steuer=b['steuer'],
                        beispiele=einordnen.beispiele_aus_notizen(daten.notiz_pfade(wurzel),
                                                                  daten.themen(wurzel)))


def _einordnen(args):
    from . import anhangtext, einordnen, mail, regeln
    anhaenge = []
    for n in args.anhang or []:
        inhalt = b''
        if os.path.exists(n):
            with open(n, 'rb') as fh:
                inhalt = fh.read()
        anhaenge.append((os.path.basename(n), inhalt))
    m = mail.Mail(message_id='', datum=datetime.date.today(), absender=args.absender,
                  betreff=args.betreff, text=args.text or '', anhaenge=anhaenge,
                  empfaenger=args.an or '')
    if m.hat_dokument:
        m.anhangtext = anhangtext.texte(m.dokumente)
    e = einordnen.einordnen(m, daten.regelwerk(args.daten), daten.einstellungen(args.daten),
                            steuerposten=daten.steuer_config(args.daten))
    print('%s (%s)' % (e.aktion, e.grund))
    v = e.vorschlag if e.vorschlag is not None else e
    if v.thema:
        print('thema=%s unterordner=%s personen=%s steuer=%s durch=%s'
              % (v.thema, v.unterordner, ','.join(v.personen), ','.join(v.steuer), v.durch))
    if e.treffer:
        print('erkannt an: ' + regeln.treffer_text(e.treffer))
    return 0


def _mail_abruf(args):
    from . import mail

    ablage = mail.Ablage(args.daten, args.konto, anhang_ziel=args.anhaenge)
    regelwerk = daten.regelwerk(args.daten)
    einst = daten.einstellungen(args.daten)
    stufen = dict(einst=einst, ki=_ki(args.daten, einst),
                  steuerposten=daten.steuer_config(args.daten))
    if args.eml:
        mails = []
        for d in sorted(os.listdir(args.eml)):
            if d.endswith('.eml'):
                with open(os.path.join(args.eml, d), 'rb') as fh:
                    mails.append(mail.mail_aus_bytes(fh.read()))
        bilanz = mail.verarbeiten(mails, ablage, regelwerk, **stufen)
        print('%s: %s' % (args.konto, bilanz))
        mail.lauf_protokollieren(args.daten, args.konto, bilanz)
        return 0

    benutzer, passwort = os.environ.get('MAIL_USER'), os.environ.get('MAIL_PASSWORD')
    if not (benutzer and passwort and args.host):
        print('MAIL_USER, MAIL_PASSWORD und --host werden benoetigt (oder --eml)')
        return 2
    status = mail.status_laden(args.daten, args.konto)
    mails, neu = mail.imap_abruf(args.host, benutzer, passwort, status,
                                 postfach=args.postfach, start_tage=args.tage)
    bilanz = mail.verarbeiten(mails, ablage, regelwerk, **stufen)
    print('%s: %d neue Mails, %s' % (args.konto, len(mails), bilanz))
    mail.status_speichern(args.daten, args.konto, neu)
    mail.lauf_protokollieren(args.daten, args.konto, bilanz)
    return 0


def _nachholen(args):
    from . import mail
    benutzer, passwort = os.environ.get('MAIL_USER'), os.environ.get('MAIL_PASSWORD')
    if args.eml:
        def holen(ids):
            gefunden = {}
            for d in sorted(os.listdir(args.eml)):
                if d.endswith('.eml'):
                    with open(os.path.join(args.eml, d), 'rb') as fh:
                        roh = fh.read()
                    mid = mail.mail_aus_bytes(roh).message_id
                    if mid in ids:
                        gefunden[mid] = roh
            return gefunden
    elif benutzer and passwort and args.host:
        def holen(ids):
            return mail.imap_holen(args.host, benutzer, passwort, ids, postfach=args.postfach)
    else:
        print('MAIL_USER, MAIL_PASSWORD und --host werden benoetigt (oder --eml)')
        return 2
    fertig, fehlt = mail.nachholen(args.daten, args.konto, holen, args.anhaenge)
    print('%s: %d Mails nachgeholt, %d nicht mehr im Postfach' % (args.konto, fertig, fehlt))
    return 0


def _vorschlagen(args):
    from . import mail
    einst = daten.einstellungen(args.daten)
    neu, fehler = mail.neue_vorschlaege(
        args.daten, args.konto, _ki(args.daten, einst), daten.regelwerk(args.daten),
        daten.steuer_config(args.daten))
    print('%s: %d neue Vorschlaege, %d ohne Ergebnis' % (args.konto, neu, fehler))
    return 0


def _drive(args):
    from . import drive
    url, schluessel = os.environ.get('DRIVE_SKRIPT_URL'), os.environ.get('DRIVE_SCHLUESSEL')
    if not (url and schluessel):
        print('DRIVE_SKRIPT_URL und DRIVE_SCHLUESSEL werden benoetigt')
        return 2
    try:
        hoch, verschoben = drive.abgleichen(args.daten, drive.Bruecke(url, schluessel),
                                            args.anhaenge, nachtragen=args.nachtragen)
    except drive.DriveFehler as e:
        print(e)
        return 1
    print('Drive: %d Notizen hochgeladen, %d verschoben' % (hoch, verschoben))
    return 0


def _regelvorschlaege(args):
    from . import regeln
    for v in daten.regelvorschlaege_schreiben(args.daten):
        print('%s: %s -> %s %s (%d passend, %d Konflikte; %s)' % (
            v['name'], regeln.treffer_text([{'teil': b.get('teil', 'ueberall'),
                                             'wert': ', '.join(b.get('werte') or [])}
                                            for b in v.get('wenn') or []]),
            (v.get('dann') or {}).get('thema', v.get('art')),
            (v.get('dann') or {}).get('unterordner', ''), v.get('passt', 0),
            len(v.get('konflikte') or []), v.get('grund', '')))
    return 0


def _bestand(args):
    n = daten.bestand_schreiben(args.daten)
    print('Bestand: %d Eingaenge in %s' % (n, daten.BESTAND_DATEI))
    return 0


def _steuer(args):
    from . import steuer
    jahre = steuer.schreiben(args.daten, daten.steuerposten(args.daten))
    print('Steuer: Uebersicht fuer %s' % (', '.join(map(str, jahre)) or 'kein Jahr'))
    return 0


def _konflikte(args):
    """Alle Regeln gegen den Bestand pruefen: Regelkonflikte melden."""
    from . import regeln
    rw = daten.regelwerk(args.daten)
    alle = daten.bestand(args.daten)
    gesamt = 0
    for r in rw.get('regeln') or []:
        passt, konflikte = regeln.pruefen_gegen_bestand(r, rw, alle)
        for e, namen in konflikte:
            if r['name'] < min(namen):  # jeden Konflikt nur einmal
                gesamt += 1
                print('Konflikt %s / %s: %s %s' % (r['name'], ', '.join(namen),
                                                   e.get('datum'), e.get('betreff')))
    print('%d Regeln, %d Konflikte im Bestand' % (len(rw.get('regeln') or []), gesamt))
    return 1 if gesamt and args.streng else 0


def _neuaufbau(args):
    """Regelvorschlaege aus Ordnerliste und Bestand neu aufbauen (ADR 0004)."""
    from . import neuaufbau
    neu, ohne = neuaufbau.schreiben(args.daten)
    for v in neu:
        print('%-28s %-40s -> %s/%s  (%d Mails, %d Konflikte)' % (
            v['name'], '; '.join('%s %s %s' % (b['teil'], b['vergleich'], ', '.join(b['werte']))
                                 for b in v['wenn']),
            v['dann']['thema'], v['dann']['unterordner'], v.get('passt', 0),
            len(v.get('konflikte') or [])))
    print('%d Vorschlaege, %d Ordner ohne Vorschlag (KI schlaegt vor, sobald Mails kommen)'
          % (len(neu), len(ohne)))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog='second-brain')
    sub = p.add_subparsers(dest='befehl', required=True)

    pr = sub.add_parser('pruefen', help='Notizen und Regeln eines Daten-Repos pruefen')
    pr.add_argument('daten', help='Pfad zum Daten-Repo')
    pr.set_defaults(fn=_pruefen)

    rg = sub.add_parser('einordnen', aliases=['regel'],
                        help='zeigen, wie eine Mail eingeordnet wuerde (ohne KI)')
    rg.add_argument('daten', help='Pfad zum Daten-Repo')
    rg.add_argument('absender')
    rg.add_argument('betreff')
    rg.add_argument('--anhang', action='append', metavar='DATEINAME',
                    help='Anhang (Pfad, wird gelesen) oder Dateiname, mehrfach moeglich')
    rg.add_argument('--an', help='Empfaenger (An/Cc)')
    rg.add_argument('--text', help='Mailtext')
    rg.set_defaults(fn=_einordnen)

    rv = sub.add_parser('regelvorschlaege',
                        help='Regelvorschlaege mit Beispielen und Konflikten aktualisieren')
    rv.add_argument('daten', help='Pfad zum Daten-Repo')
    rv.set_defaults(fn=_regelvorschlaege)

    bs = sub.add_parser('bestand', help='index/bestand.jsonl fuer die Web-App schreiben')
    bs.add_argument('daten', help='Pfad zum Daten-Repo')
    bs.set_defaults(fn=_bestand)

    st = sub.add_parser('steuer', help='Steueruebersicht steuer/<jahr>.json und .csv schreiben')
    st.add_argument('daten', help='Pfad zum Daten-Repo')
    st.set_defaults(fn=_steuer)

    kf = sub.add_parser('konflikte', help='Regeln gegen den Bestand pruefen (Regelkonflikte)')
    kf.add_argument('daten', help='Pfad zum Daten-Repo')
    kf.add_argument('--streng', action='store_true', help='bei Konflikten mit Fehler beenden')
    kf.set_defaults(fn=_konflikte)

    na = sub.add_parser('neuaufbau',
                        help='Regelvorschlaege aus Ordnerliste und Bestand neu aufbauen')
    na.add_argument('daten', help='Pfad zum Daten-Repo')
    na.set_defaults(fn=_neuaufbau)

    ma = sub.add_parser('mail-abruf', help='Mails abholen und ablegen (IMAP oder .eml-Ordner)')
    ma.add_argument('daten', help='Pfad zum Daten-Repo')
    ma.add_argument('--konto', required=True, help='Name der Quelle, z. B. gmx oder gmail')
    ma.add_argument('--host', help='IMAP-Server, z. B. imap.gmx.net')
    ma.add_argument('--postfach', default='INBOX')
    ma.add_argument('--tage', type=int, default=30, help='beim ersten Abruf so weit zurueck')
    ma.add_argument('--eml', help='statt IMAP: Ordner mit .eml-Dateien')
    ma.add_argument('--anhaenge', help='Verzeichnis fuer Anhaenge (nicht im Daten-Repo)')
    ma.set_defaults(fn=_mail_abruf)

    nh = sub.add_parser('nachholen',
                        help='in der Web-App angeforderte Mails noch einmal aus dem Postfach holen')
    nh.add_argument('daten', help='Pfad zum Daten-Repo')
    nh.add_argument('--konto', required=True)
    nh.add_argument('--host', help='IMAP-Server')
    nh.add_argument('--postfach', default='INBOX')
    nh.add_argument('--eml', help='statt IMAP: Ordner mit .eml-Dateien')
    nh.add_argument('--anhaenge', help='Verzeichnis fuer Anhaenge und Mail-Seiten')
    nh.set_defaults(fn=_nachholen)

    vs = sub.add_parser('vorschlagen',
                        help='Neue Ordner-Vorschlaege fuer angeforderte Mails (KI)')
    vs.add_argument('daten', help='Pfad zum Daten-Repo')
    vs.add_argument('--konto', required=True)
    vs.set_defaults(fn=_vorschlagen)

    dr = sub.add_parser('drive', help='Anhaenge in die Drive-Ordner hochladen und nachziehen')
    dr.add_argument('daten', help='Pfad zum Daten-Repo')
    dr.add_argument('--anhaenge', help='Verzeichnis mit den Anhaengen des Abrufs')
    dr.add_argument('--nachtragen', action='store_true',
                    help='aeltere Notizen ohne Anhangliste aus dem Anhang-Verzeichnis ergaenzen')
    dr.set_defaults(fn=_drive)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == '__main__':
    sys.exit(main())
