"""Kommandozeile: second-brain <befehl> ..."""

import argparse
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

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == '__main__':
    sys.exit(main())
