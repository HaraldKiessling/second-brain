import datetime
import json
import os
import shutil

import pytest

from second_brain import cli, daten, einordnen as eo, mail, notiz as nz

BEISPIEL = os.path.join(os.path.dirname(__file__), '..', 'beispiel-daten')
HEUTE = datetime.date(2026, 10, 30)
NEWSLETTER = {'list-unsubscribe': '<mailto:ab@shop.de>', 'precedence': 'bulk',
              'list-id': '<angebote.shop.de>'}


def m(absender, betreff, anhang=None, kopf=None, mid=None, kategorie='', text='Hallo',
      anhangtext='', an=''):
    return mail.Mail(message_id=mid or '<%s|%s>' % (absender, betreff),
                     datum=datetime.date(2026, 10, 28), absender=absender,
                     betreff=betreff, text=text,
                     anhaenge=[(anhang, b'%PDF')] if anhang else [],
                     kopf=kopf or {}, kategorie=kategorie, anhangtext=anhangtext,
                     empfaenger=an)


@pytest.fixture
def repo(tmp_path):
    ziel = tmp_path / 'daten'
    shutil.copytree(BEISPIEL, ziel)
    return str(ziel)


def lauf(repo, mails, ki=None):
    ablage = mail.Ablage(repo, 'gmx', heute=HEUTE)
    return mail.verarbeiten(mails, ablage, daten.regelwerk(repo), daten.einstellungen(repo), ki,
                            daten.steuer_config(repo))


def eingang(repo):
    ordner = os.path.join(repo, 'eingang')
    dateien = sorted(d for d in os.listdir(ordner) if d.endswith('.md'))
    return [nz.lesen(open(os.path.join(ordner, d), encoding='utf-8').read()) for d in dateien]


def notiz_ablegen(repo, nid, absender, thema, ablage, personen=('anna',), text=''):
    pfad = os.path.join(repo, 'notizen', '2026', thema, nid + '.md')
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    with open(pfad, 'w', encoding='utf-8') as fh:
        fh.write(nz.schreiben(nz.Notiz(meta={
            'id': nid, 'erstellt': datetime.date(2026, 5, 1), 'quelle': 'gmx',
            'personen': list(personen), 'themen': [thema], 'ablage': ablage,
            'absender': absender, 'eingeordnet_durch': 'manuell'},
            text='# %s\n\n%s\n' % (nid, text))))


# --- Spam ------------------------------------------------------------------

def test_spam_wert_aus_kopfzeilen():
    wert, gruende = eo.spam_wert(NEWSLETTER, 'Shop <info@shop.de>', 'Neue Produkte')
    assert wert >= 0.7
    assert 'Abmeldelink' in gruende and 'Massenversand' in gruende


def test_provider_markierung_ist_eindeutig():
    assert eo.spam_wert({'x-spam-flag': 'YES'}, 'a@b.de', 'Hallo')[0] == 1.0


def test_dokument_und_bekannter_absender_senken_den_spam_wert():
    wert, _ = eo.spam_wert(NEWSLETTER, 'rechnung@shop.de', 'Ihre Rechnung',
                           hat_dokument=True, bekannt=True)
    assert wert < 0.3


def test_gmail_werbung_zaehlt():
    assert eo.spam_wert({'list-unsubscribe': 'x'}, 'a@b.de', 'Hi', kategorie='werbung')[0] >= 0.7


def test_spam_wird_verworfen_aber_im_index_markiert(repo):
    b = lauf(repo, [m('Shop <info@shop.de>', 'Neue Produkte', kopf=NEWSLETTER)])
    assert b.verwerfen == 1
    with open(os.path.join(repo, 'index', 'mail', '2026-10.jsonl'), encoding='utf-8') as fh:
        zeile = json.loads(fh.readline())
    assert zeile['verworfen'].startswith('Spam-Wert')


def test_transaktionsmail_mit_abmeldelink_bleibt(repo):
    b = lauf(repo, [m('Shop <info@shop.de>', 'Ihre Bestellung',
                      kopf={'list-unsubscribe': 'x'})])
    assert b.index == 1


def test_kleines_bild_ist_kein_dokument():
    logo = m('a@b.de', 'Hallo')
    logo.anhaenge = [('logo.png', b'x' * 2000)]
    scan = m('a@b.de', 'Scan')
    scan.anhaenge = [('scan.jpg', b'x' * 200_000)]
    assert not logo.hat_dokument and scan.hat_dokument


def test_werbe_absender_und_emoji_zaehlen():
    wert, gruende = eo.spam_wert({'list-unsubscribe': 'x'}, 'Hotel <info@mail.hotel.de>',
                                 '🍂 Goldener Herbst')
    assert wert >= 0.6 and 'Werbe-Absender' in gruende and 'Emoji im Betreff' in gruende


def test_rechnungsabsender_ist_keine_werbung():
    assert eo.spam_wert({}, 'IONOS <rechnung@ionos.de>', 'Ihre Rechnung')[0] == 0


# --- KI --------------------------------------------------------------------

def ki_mit(antwort, **kw):
    gesendet = []

    def senden(nutzlast):
        gesendet.append(nutzlast)
        if isinstance(antwort, Exception):
            raise antwort
        return {'choices': [{'message': {'content': json.dumps(antwort)}}]}
    ki = eo.KI('schluessel', 'test/modell', daten.themen(BEISPIEL), {'anna', 'ben'},
               senden=senden, **kw)
    return ki, gesendet


def test_ki_legt_nie_ohne_regel_ab_auch_bei_hoher_konfidenz(repo):
    ki, gesendet = ki_mit({'thema': 'steuer', 'unterordner': 'bescheide/{jahr}',
                           'personen': ['anna'], 'konfidenz': 0.99, 'grund': 'Bescheid'})
    b = lauf(repo, [m('amt@stadt.de', 'Bescheid', anhang='b.pdf',
                      anhangtext='Bescheid fuer 2026')], ki)
    assert (b.notiz, b.offen) == (0, 1) and len(gesendet) == 1
    inhalt = gesendet[0]['messages'][0]['content']
    assert 'Absender: amt@stadt.de' in inhalt and 'Text der Anhaenge' in inhalt
    e = eingang(repo)[0].meta
    assert e['vorschlag']['durch'] == 'ki/test/modell'
    assert e['offen_grund'] == 'keine Regel passt, Vorschlag der KI'


def test_ki_unsicher_wird_vorschlag(repo):
    ki, _ = ki_mit({'thema': 'steuer', 'personen': ['anna'], 'konfidenz': 0.6})
    lauf(repo, [m('amt@stadt.de', 'Bescheid', anhang='b.pdf')], ki)
    assert eingang(repo)[0].meta['vorschlag']['durch'] == 'ki/test/modell'


def test_ki_fehler_fuehrt_zur_rueckfrage(repo):
    ki, _ = ki_mit(OSError('kein Netz'))
    assert lauf(repo, [m('amt@stadt.de', 'Bescheid', anhang='b.pdf')], ki).offen == 1


def test_ki_unbekanntes_thema_wird_ignoriert(repo):
    ki, _ = ki_mit({'thema': 'erfunden', 'personen': ['anna'], 'konfidenz': 0.99})
    assert lauf(repo, [m('amt@stadt.de', 'Bescheid', anhang='b.pdf')], ki).offen == 1


def test_ki_nur_fuer_relevante_mails_und_mit_budget(repo):
    ki, gesendet = ki_mit({'thema': 'steuer', 'personen': ['anna'], 'konfidenz': 0.6},
                          max_anfragen=1)
    lauf(repo, [m('freund@mail.de', 'Grillen'),
                m('a@x.de', 'Brief 1', anhang='1.pdf'),
                m('b@y.de', 'Brief 2', anhang='2.pdf'),
                m('c@z.de', 'Noch eine')], ki)
    # je eine Anfrage: "wichtig?" fuer Grillen, Ablage fuer Brief 1 (getrennte Budgets)
    assert len(gesendet) == 2
    assert 'kein Dokument' in gesendet[0]['messages'][0]['content']
    assert 'Brief 1' in gesendet[1]['messages'][0]['content']


# --- Einstellungen, Pruefung, Kommandozeile --------------------------------

def test_unterordner_gueltig():
    assert eo.unterordner_gueltig('ionos/rechnungen/{jahr}')
    assert not eo.unterordner_gueltig('ionos//x')
    assert not eo.unterordner_gueltig('../geheim')
    assert not eo.unterordner_gueltig('/ionos')


def test_ki_neue_ordner_mit_gegenpartei_und_nummer(repo):
    ki, gesendet = ki_mit({'wichtig': False})
    lauf(repo, [m('x@neu.de', 'Hallo', anhang='a.pdf')], ki)
    assert 'Gegenpartei' in gesendet[0]['messages'][0]['content']


# --- Regeln im Ablauf -------------------------------------------------------

def test_regel_legt_ab_und_merkt_woran_erkannt(repo):
    lauf(repo, [m('Hoster <billing@hoster-beispiel.de>', 'Rechnung', anhang='r.pdf',
                  text='Rechnungsbetrag 12,00 EUR, Abbuchung am 05.11.2026')])
    pfad = os.path.join(repo, 'notizen', '2026', 'edv', '2026-10-28-hoster-rechnung.md')
    n = nz.lesen(open(pfad, encoding='utf-8').read())
    assert n.meta['eingeordnet_durch'] == 'regel/hoster'
    assert n.meta['regel_treffer'] == [{'teil': 'absender', 'wert': 'hoster-beispiel.de',
                                        'regel': 'hoster'}]
    assert n.meta['betrag'] == 12.0 and n.meta['zahlung'] == datetime.date(2026, 11, 5)
    assert n.meta['steuer'] == ['anna.n.arbeitsmittel']
    assert daten.pruefen(repo) == []


def test_nummer_im_anhangtext_reicht(repo):
    b = lauf(repo, [m('service@versicherer.de', 'Ihre Unterlagen', anhang='u.pdf',
                      anhangtext='Versicherungsschein Nr. 624 220429 P')])
    assert b.notiz == 1
    pfad = os.path.join(repo, 'notizen', '2026', 'versicherungen')
    n = nz.lesen(open(os.path.join(pfad, os.listdir(pfad)[0]), encoding='utf-8').read())
    assert n.meta['ablage'] == '0-2026/08Versicherungen/07Kfz_624_220429-P'
    assert n.meta['objekte'] == ['auto']


def test_regelkonflikt_landet_mit_beiden_regeln_im_eingang(repo):
    b = lauf(repo, [m('billing@hoster-beispiel.de', 'Kfz 624/220429-P', anhang='r.pdf')])
    assert (b.notiz, b.offen) == (0, 1)
    e = eingang(repo)[0].meta
    assert e['regelkonflikt'] == ['hoster', 'kfz-624-220429-p']
    assert e['offen_grund'] == 'Regelkonflikt: hoster, kfz-624-220429-p'
    v = e['vorschlag']
    assert {v['thema'], v['alternativen'][0]['thema']} == {'edv', 'versicherungen'}


def test_aussortieren_ist_eine_regel(repo):
    b = lauf(repo, [m('Shop <newsletter@shop.de>', 'Neuigkeiten')])
    assert b.verwerfen == 1
    with open(os.path.join(repo, 'index', 'mail', '2026-10.jsonl'), encoding='utf-8') as fh:
        assert json.loads(fh.readline())['verworfen'].startswith('Regel newsletter')


def test_merkmalregeln_ergaenzen_regel_und_ki(repo):
    lauf(repo, [m('Hoster <billing@hoster-beispiel.de>', 'Rechnung', anhang='r.pdf',
                  an='ben@beispiel.de', anhangtext='Arbeitskosten 80,00 EUR')])
    pfad = os.path.join(repo, 'notizen', '2026', 'edv', '2026-10-28-hoster-rechnung.md')
    n = nz.lesen(open(pfad, encoding='utf-8').read())
    assert n.meta['personen'] == ['ben']
    assert n.meta['steuer'] == ['anna.n.arbeitsmittel', 'anna.35a.handwerker']
    assert n.meta['lohnanteil'] == 80.0
    ki, _ = ki_mit({'thema': 'steuer', 'personen': ['anna'], 'konfidenz': 0.7})
    lauf(repo, [m('maler@firma.de', 'Rechnung Malerarbeiten', anhang='m.pdf',
                  anhangtext='Lohnkosten 300,00 EUR')], ki)
    assert eingang(repo)[0].meta['vorschlag']['steuer'] == ['anna.35a.handwerker']


def test_ohne_regel_mit_dokument_immer_zu_erledigen(repo):
    b = lauf(repo, [m('wer@irgendwo.de', 'Vertrag', anhang='v.pdf')])
    assert b.offen == 1
    assert eingang(repo)[0].meta['offen_grund'] == 'keine Regel passt'


def test_an_sich_selbst_gesendet_wird_immer_erfasst(repo):
    with open(os.path.join(repo, 'config', 'einordnen.yaml'), 'a', encoding='utf-8') as fh:
        fh.write('eigene_adressen: [anna@beispiel.de]\n')
    b = lauf(repo, [m('Anna <anna@beispiel.de>', 'Notiz an mich')])
    assert b.offen == 1
    assert eingang(repo)[0].meta['offen_grund'] == 'an dich selbst gesendet'


# --- Regelvorschlaege --------------------------------------------------------

def test_regelvorschlag_mit_gemeinsamer_nummer_und_beispielen(repo, capsys):
    for i in (1, 2):
        notiz_ablegen(repo, 'w%d' % i, 'kasse@werke.de', 'versicherungen',
                      '0-2026/08Versicherungen/Werke_4711-0815', text='Kundennummer 4711-0815')
    assert cli.main(['regelvorschlaege', repo]) == 0
    with open(os.path.join(repo, 'regeln', 'mail-vorschlaege.json'), encoding='utf-8') as fh:
        [v] = json.load(fh)['vorschlaege']
    assert v['wenn'] == [{'teil': 'ueberall', 'vergleich': 'nummer', 'werte': ['4711-0815']}]
    assert v['dann']['unterordner'] == 'Werke_4711-0815'
    assert v['passt'] == 2 and v['konflikte'] == [] and v['wert_im_ordner'] is True
    assert 'werke' in capsys.readouterr().out.lower()


def test_regelvorschlag_nach_domain_und_nicht_wenn_abgelehnt(repo):
    for i in (1, 2):
        notiz_ablegen(repo, 'p%d' % i, 'post@praxis.de', 'versicherungen',
                      '0-2026/08Versicherungen/praxis')
    [v] = daten.regelvorschlaege_schreiben(repo)
    assert v['wenn'][0] == {'teil': 'absender', 'vergleich': 'wort', 'werte': ['praxis.de']}
    pfad = os.path.join(repo, 'regeln', 'mail-vorschlaege.json')
    d = json.load(open(pfad, encoding='utf-8'))
    d['abgelehnt'] = ['praxis.de']
    json.dump(d, open(pfad, 'w', encoding='utf-8'))
    assert daten.regelvorschlaege_schreiben(repo) == []


def test_vorschlag_aus_neuaufbau_bleibt_und_wird_geprueft(repo):
    pfad = os.path.join(repo, 'regeln', 'mail-vorschlaege.json')
    v = {'name': 'kfz-neu', 'art': 'ordner', 'herkunft': 'bestand', 'grund': 'Drive',
         'wenn': [{'teil': 'absender', 'vergleich': 'wort', 'werte': ['hoster-beispiel.de']}],
         'dann': {'thema': 'edv', 'unterordner': 'x'}}
    json.dump({'abgelehnt': [], 'vorschlaege': [v]}, open(pfad, 'w', encoding='utf-8'))
    [neu] = daten.regelvorschlaege_schreiben(repo)
    assert neu['name'] == 'kfz-neu' and neu['passt'] == 1
    assert neu['konflikte'][0]['regeln'] == ['hoster']


def test_cli_einordnen(capsys):
    assert cli.main(['einordnen', BEISPIEL, 'Hoster <billing@hoster-beispiel.de>', 'Rechnung',
                     '--anhang', 'r.pdf']) == 0
    aus = capsys.readouterr().out
    assert 'notiz (Regel hoster' in aus and 'erkannt an: Absender: hoster-beispiel.de' in aus


def test_cli_konflikte_und_bestand(repo, capsys):
    lauf(repo, [m('billing@hoster-beispiel.de', 'Kfz 624/220429-P', anhang='r.pdf')])
    assert cli.main(['bestand', repo]) == 0
    assert os.path.exists(os.path.join(repo, 'index', 'bestand.jsonl'))
    assert cli.main(['konflikte', repo, '--streng']) == 1
    assert 'Konflikt hoster / kfz-624-220429-p' in capsys.readouterr().out
