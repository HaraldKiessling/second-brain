"""Kommandozeile: second-brain <befehl> ..."""

import argparse
import os
import sys

from . import daten, regeln


def _pruefen(args):
    fehler = daten.pruefen(args.daten)
    for pfad, meldung in fehler:
        print('%s: %s' % (pfad, meldung))
    anzahl = sum(1 for _ in daten.notiz_pfade(args.daten))
    print('%d Notizen geprueft, %d Fehler' % (anzahl, len(fehler)))
    return 1 if fehler else 0


def _regel(args):
    e = regeln.einordnen(args.absender, args.betreff, args.anhang,
                         daten.regelwerk(args.daten))
    print('%s (%s)' % (e.aktion, e.grund))
    if e.thema:
        print('thema=%s unterordner=%s personen=%s'
              % (e.thema, e.unterordner, ','.join(e.personen)))
    return 0


def _mail_abruf(args):
    from . import mail

    ablage = mail.Ablage(args.daten, args.konto, anhang_ziel=args.anhaenge)
    regelwerk = daten.regelwerk(args.daten)
    if args.eml:
        mails = []
        for d in sorted(os.listdir(args.eml)):
            if d.endswith('.eml'):
                with open(os.path.join(args.eml, d), 'rb') as fh:
                    mails.append(mail.mail_aus_bytes(fh.read()))
        print('%s: %s' % (args.konto, mail.verarbeiten(mails, ablage, regelwerk)))
        return 0

    benutzer, passwort = os.environ.get('MAIL_USER'), os.environ.get('MAIL_PASSWORD')
    if not (benutzer and passwort and args.host):
        print('MAIL_USER, MAIL_PASSWORD und --host werden benoetigt (oder --eml)')
        return 2
    status = mail.status_laden(args.daten, args.konto)
    mails, neu = mail.imap_abruf(args.host, benutzer, passwort, status,
                                 postfach=args.postfach, start_tage=args.tage)
    print('%s: %d neue Mails, %s' % (args.konto, len(mails),
                                     mail.verarbeiten(mails, ablage, regelwerk)))
    mail.status_speichern(args.daten, args.konto, neu)
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog='second-brain')
    sub = p.add_subparsers(dest='befehl', required=True)

    pr = sub.add_parser('pruefen', help='Notizen und Regeln eines Daten-Repos pruefen')
    pr.add_argument('daten', help='Pfad zum Daten-Repo')
    pr.set_defaults(fn=_pruefen)

    rg = sub.add_parser('regel', help='zeigen, wie eine Mail eingeordnet wuerde')
    rg.add_argument('daten', help='Pfad zum Daten-Repo')
    rg.add_argument('absender')
    rg.add_argument('betreff')
    rg.add_argument('--anhang', action='store_true', help='Mail hat Dokument-Anhang')
    rg.set_defaults(fn=_regel)

    ma = sub.add_parser('mail-abruf', help='Mails abholen und ablegen (IMAP oder .eml-Ordner)')
    ma.add_argument('daten', help='Pfad zum Daten-Repo')
    ma.add_argument('--konto', required=True, help='Name der Quelle, z. B. gmx oder gmail')
    ma.add_argument('--host', help='IMAP-Server, z. B. imap.gmx.net')
    ma.add_argument('--postfach', default='INBOX')
    ma.add_argument('--tage', type=int, default=30, help='beim ersten Abruf so weit zurueck')
    ma.add_argument('--eml', help='statt IMAP: Ordner mit .eml-Dateien')
    ma.add_argument('--anhaenge', help='Verzeichnis fuer Anhaenge (nicht im Daten-Repo)')
    ma.set_defaults(fn=_mail_abruf)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == '__main__':
    sys.exit(main())
