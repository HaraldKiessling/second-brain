import datetime
import json
import os
import shutil

import pytest
import yaml

from second_brain import cli, daten, einordnen as eo, mail, notiz as nz

BEISPIEL = os.path.join(os.path.dirname(__file__), '..', 'beispiel-daten')
HEUTE = datetime.date(2026, 10, 30)
NEWSLETTER = {'list-unsubscribe': '<mailto:ab@shop.de>', 'precedence': 'bulk',
              'list-id': '<angebote.shop.de>'}


def m(absender, betreff, anhang=None, kopf=None, mid=None, kategorie=''):
    return mail.Mail(message_id=mid or '<%s|%s>' % (absender, betreff),
                     datum=datetime.date(2026, 10, 28), absender=absender,
                     betreff=betreff, text='Hallo',
                     anhaenge=[(anhang, b'%PDF')] if anhang else [],
                     kopf=kopf or {}, kategorie=kategorie)


@pytest.fixture
def repo(tmp_path):
    ziel = tmp_path / 'daten'
    shutil.copytree(BEISPIEL, ziel)
    return str(ziel)


def lauf(repo, mails, ki=None):
    ablage = mail.Ablage(repo, 'gmx', heute=HEUTE)
    return mail.verarbeiten(mails, ablage, daten.regelwerk(repo), daten.lerner(repo),
                            daten.einstellungen(repo), ki)


def eingang(repo):
    ordner = os.path.join(repo, 'eingang')
    dateien = sorted(d for d in os.listdir(ordner) if d.endswith('.md'))
    return [nz.lesen(open(os.path.join(ordner, d), encoding='utf-8').read()) for d in dateien]


def notiz_ablegen(repo, nid, absender, thema, ablage, personen=('anna',)):
    pfad = os.path.join(repo, 'notizen', '2026', thema, nid + '.md')
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    with open(pfad, 'w', encoding='utf-8') as fh:
        fh.write(nz.schreiben(nz.Notiz(meta={
            'id': nid, 'erstellt': datetime.date(2026, 5, 1), 'quelle': 'gmx',
            'personen': list(personen), 'themen': [thema], 'ablage': ablage,
            'absender': absender, 'eingeordnet_durch': 'manuell'}, text='# %s\n' % nid)))


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


# --- Heuristik -------------------------------------------------------------

def test_eine_fruehere_notiz_ergibt_vorschlag(repo):
    notiz_ablegen(repo, 'n1', 'post@praxis.de', 'versicherungen',
                  '0-2026/08Versicherungen/praxis/2026')
    b = lauf(repo, [m('Praxis <post@praxis.de>', 'Befund')])
    assert b.offen == 1
    v = eingang(repo)[0].meta['vorschlag']
    assert v['thema'] == 'versicherungen'
    assert v['unterordner'] == 'praxis/{jahr}'
    assert v['konfidenz'] == 0.67
    assert v['durch'] == 'heuristik/absender'


def test_zwei_gleiche_notizen_legen_ohne_rueckfrage_ab(repo):
    for i in (1, 2):
        notiz_ablegen(repo, 'n%d' % i, 'post@praxis.de', 'versicherungen',
                      '0-2026/08Versicherungen/praxis/rechnungen/2026')
    b = lauf(repo, [m('Praxis <post@praxis.de>', 'Rechnung', anhang='r.pdf')])
    assert b.notiz == 1
    [pfad] = [os.path.join(v, d) for v, _, ds in os.walk(os.path.join(repo, 'notizen'))
              for d in ds if 'praxis-rechnung' in d]
    n = nz.lesen(open(pfad, encoding='utf-8').read())
    assert n.meta['ablage'] == '0-2026/08Versicherungen/praxis/rechnungen/2026'
    assert n.meta['eingeordnet_durch'] == 'heuristik/absender'
    assert n.meta['konfidenz'] == 0.8
    assert n.meta['absender'] == 'post@praxis.de'
    assert daten.pruefen(repo) == []


def test_gleiche_domain_mit_geringerer_konfidenz(repo):
    notiz_ablegen(repo, 'n1', 'a@firma.de', 'edv', '0-2026/31 EDV/firma')
    notiz_ablegen(repo, 'n2', 'a@firma.de', 'edv', '0-2026/31 EDV/firma')
    v = daten.lerner(repo).vorschlag('b@firma.de', 'Hallo')
    assert v.durch == 'heuristik/domain' and v.konfidenz == pytest.approx(0.68)


def test_freemail_domain_lernt_nichts(repo):
    notiz_ablegen(repo, 'n1', 'a@gmail.com', 'edv', '0-2026/31 EDV')
    assert daten.lerner(repo).vorschlag('b@gmail.com', 'Hallo') is None


def test_ablagewissen_schlaegt_vor(repo):
    b = lauf(repo, [m('Service <service@versicherung-beispiel.de>', 'Beitragsrechnung Hausrat',
                      anhang='beitrag.pdf')])
    assert b.offen == 1
    v = eingang(repo)[0].meta['vorschlag']
    assert (v['thema'], v['unterordner'], v['konfidenz']) == ('versicherungen', '01Hausrat', 0.7)


def test_bestaetigtes_ablagewissen_reicht_beim_naechsten_mal(repo):
    notiz_ablegen(repo, 'n1', 'service@versicherung-beispiel.de', 'versicherungen',
                  '0-2026/08Versicherungen/01Hausrat')
    v = daten.lerner(repo).vorschlag('service@versicherung-beispiel.de', 'Hausrat 2027')
    assert (v.durch, v.unterordner) == ('heuristik/absender', '01Hausrat')
    assert v.konfidenz == pytest.approx(0.82, abs=0.01)
    assert 'passt zu bekannt aus Drive-Ablage' in v.grund


def test_ablagewissen_mehrdeutig_gibt_niedrige_konfidenz(repo):
    v = daten.lerner(repo).vorschlag('service@versicherung-beispiel.de', 'Ihr Vertrag')
    assert v.konfidenz == 0.4


def test_ohne_dokument_und_ohne_vorschlag_nur_index(repo):
    assert lauf(repo, [m('freund@mail.de', 'Grillen')]).index == 1


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


def test_ki_legt_bei_hoher_konfidenz_ab(repo):
    ki, gesendet = ki_mit({'thema': 'steuer', 'unterordner': 'bescheide/{jahr}',
                           'personen': ['anna'], 'konfidenz': 0.9, 'grund': 'Bescheid'})
    b = lauf(repo, [m('amt@stadt.de', 'Bescheid', anhang='b.pdf')], ki)
    assert b.notiz == 1 and len(gesendet) == 1
    assert 'Absender: amt@stadt.de' in gesendet[0]['messages'][0]['content']
    pfad = os.path.join(repo, 'notizen', '2026', 'steuer')
    n = nz.lesen(open(os.path.join(pfad, os.listdir(pfad)[0]), encoding='utf-8').read())
    assert n.meta['eingeordnet_durch'] == 'ki/test/modell'
    assert n.meta['ablage'] == '0-2026/09Steuer/bescheide/2026'


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
                m('b@y.de', 'Brief 2', anhang='2.pdf')], ki)
    assert len(gesendet) == 1


# --- Einstellungen, Pruefung, Kommandozeile --------------------------------

def test_unterordner_gueltig():
    assert eo.unterordner_gueltig('ionos/rechnungen/{jahr}')
    assert not eo.unterordner_gueltig('ionos//x')
    assert not eo.unterordner_gueltig('../geheim')
    assert not eo.unterordner_gueltig('/ionos')


def test_schwelle_ist_einstellbar(repo):
    with open(os.path.join(repo, 'config', 'einordnen.yaml'), 'w') as fh:
        yaml.safe_dump({'schwelle': 0.6}, fh)
    notiz_ablegen(repo, 'n1', 'post@praxis.de', 'versicherungen', '0-2026/08Versicherungen')
    assert lauf(repo, [m('post@praxis.de', 'Befund')]).notiz == 1


def test_pruefen_meldet_falsches_ablagewissen(repo):
    with open(os.path.join(repo, 'config', 'ablagewissen.yaml'), 'w') as fh:
        yaml.safe_dump({'eintraege': [{'muster': ['x'], 'thema': 'gibtsnicht'}]}, fh)
    assert daten.pruefen(repo) == [('config/ablagewissen.yaml',
                                    'Eintrag 1: Thema unbekannt: gibtsnicht')]


def test_cli_einordnen(capsys):
    assert cli.main(['einordnen', BEISPIEL, 'service@versicherung-beispiel.de',
                     'Hausrat', '--anhang', 'a.pdf']) == 0
    aus = capsys.readouterr().out
    assert 'offen, Konfidenz 0.70' in aus
    assert 'thema=versicherungen unterordner=01Hausrat' in aus
