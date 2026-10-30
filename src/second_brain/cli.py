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
    return einordnen.KI(schluessel, einst['ki']['modell'], daten.themen(wurzel),
                        daten.kontext(wurzel).personen, einst['ki']['max_pro_lauf'],
                        hinweise=einst['ki']['hinweise'],
                        unterordner=daten.bekannte_unterordner(wurzel))


def _einordnen(args):
    from . import einordnen, mail
    m = mail.Mail(message_id='', datum=datetime.date.today(), absender=args.absender,
                  betreff=args.betreff, text='',
                  anhaenge=[(n, b'') for n in args.anhang or []], empfaenger=args.an or '')
    einst = daten.einstellungen(args.daten)
    e = einordnen.einordnen(m, daten.regelwerk(args.daten), daten.lerner(args.daten), einst)
    print('%s, Konfidenz %.2f (%s)' % (e.aktion, e.konfidenz, e.grund))
    v = e.vorschlag if e.vorschlag is not None else e
    if v.thema:
        print('thema=%s unterordner=%s personen=%s durch=%s'
              % (v.thema, v.unterordner, ','.join(v.personen), v.durch))
    return 0


def _mail_abruf(args):
    from . import mail

    ablage = mail.Ablage(args.daten, args.konto, anhang_ziel=args.anhaenge)
    regelwerk = daten.regelwerk(args.daten)
    einst = daten.einstellungen(args.daten)
    stufen = dict(lerner=daten.lerner(args.daten), einst=einst, ki=_ki(args.daten, einst))
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


def _drive(args):
    from . import drive
    url, schluessel = os.environ.get('DRIVE_SKRIPT_URL'), os.environ.get('DRIVE_SCHLUESSEL')
    if not (url and schluessel):
        print('DRIVE_SKRIPT_URL und DRIVE_SCHLUESSEL werden benoetigt')
        return 2
    try:
        hoch, verschoben = drive.abgleichen(args.daten, drive.Bruecke(url, schluessel),
                                            args.anhaenge)
    except drive.DriveFehler as e:
        print(e)
        return 1
    print('Drive: %d Notizen hochgeladen, %d verschoben' % (hoch, verschoben))
    return 0


def _regelvorschlaege(args):
    for v in daten.regelvorschlaege_schreiben(args.daten):
        print('%s: %s -> %s %s (%s)' % (v['name'], ','.join(v['absender']), v['thema'],
                                        v.get('unterordner', ''), v['grund']))
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
                    help='Dateiname eines Anhangs, mehrfach moeglich')
    rg.add_argument('--an', help='Empfaenger (An/Cc)')
    rg.set_defaults(fn=_einordnen)

    rv = sub.add_parser('regelvorschlaege',
                        help='Regelentwuerfe aus gleich eingeordneten Notizen berechnen')
    rv.add_argument('daten', help='Pfad zum Daten-Repo')
    rv.set_defaults(fn=_regelvorschlaege)

    ma = sub.add_parser('mail-abruf', help='Mails abholen und ablegen (IMAP oder .eml-Ordner)')
    ma.add_argument('daten', help='Pfad zum Daten-Repo')
    ma.add_argument('--konto', required=True, help='Name der Quelle, z. B. gmx oder gmail')
    ma.add_argument('--host', help='IMAP-Server, z. B. imap.gmx.net')
    ma.add_argument('--postfach', default='INBOX')
    ma.add_argument('--tage', type=int, default=30, help='beim ersten Abruf so weit zurueck')
    ma.add_argument('--eml', help='statt IMAP: Ordner mit .eml-Dateien')
    ma.add_argument('--anhaenge', help='Verzeichnis fuer Anhaenge (nicht im Daten-Repo)')
    ma.set_defaults(fn=_mail_abruf)

    dr = sub.add_parser('drive', help='Anhaenge in die Drive-Ordner hochladen und nachziehen')
    dr.add_argument('daten', help='Pfad zum Daten-Repo')
    dr.add_argument('--anhaenge', help='Verzeichnis mit den Anhaengen des Abrufs')
    dr.set_defaults(fn=_drive)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == '__main__':
    sys.exit(main())
