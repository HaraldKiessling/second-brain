import datetime
import json
import os
import shutil

import pytest

from second_brain import daten, einordnen as eo, mail, notiz as nz

BEISPIEL = os.path.join(os.path.dirname(__file__), '..', 'beispiel-daten')
HEUTE = datetime.date(2026, 11, 1)


@pytest.fixture
def repo(tmp_path):
    ziel = tmp_path / 'daten'
    shutil.copytree(BEISPIEL, ziel)
    return str(ziel)


def m(absender, betreff, text='Hallo', anhang='brief.pdf'):
    return mail.Mail(message_id='<%s>' % betreff, datum=datetime.date(2026, 11, 1),
                     absender=absender, betreff=betreff, text=text,
                     anhaenge=[(anhang, b'%PDF')] if anhang else [])


def lauf(repo, mails, ki=None):
    ablage = mail.Ablage(repo, 'gmx', heute=HEUTE)
    return mail.verarbeiten(mails, ablage, daten.regelwerk(repo), daten.lerner(repo),
                            daten.einstellungen(repo), ki, daten.vertraege(repo))


def ki_mit(antwort):
    gesendet = []

    def senden(nutzlast):
        gesendet.append(nutzlast)
        return {'choices': [{'message': {'content': json.dumps(antwort)}}]}
    b = daten.bezuege(BEISPIEL)
    return eo.KI('s', 'test/modell', daten.themen(BEISPIEL), {'anna', 'ben'}, senden=senden,
                 objekte=b['objekte'], steuer=b['steuer'],
                 vertraege=daten.vertraege(BEISPIEL)), gesendet


def lesen(pfad):
    with open(pfad, encoding='utf-8') as fh:
        return nz.lesen(fh.read())


# --- Vertragsnummer --------------------------------------------------------

@pytest.mark.parametrize('text', ['Vertrag 624/220429-P', 'Vertrag 624 220429 P',
                                  'vertrag 624220429p', 'Nr. 624-220429-P.'])
def test_vertragsnummer_mit_beliebigen_trennzeichen(text):
    assert eo.vertrag_finden(daten.vertraege(BEISPIEL), text)['name'] == 'Kfz-Versicherung'


@pytest.mark.parametrize('text', ['1624/220429-P', '624/220429-P1', '624/22042'])
def test_vertragsnummer_nur_als_ganzes(text):
    assert eo.vertrag_finden(daten.vertraege(BEISPIEL), text) is None


def test_laengste_nummer_gewinnt():
    vertraege = [{'nummer': '702213446', 'thema': 'a'}, {'nummer': '702213446-Y-16', 'thema': 'b'}]
    assert eo.vertrag_finden(vertraege, 'Police 702213446-Y-16')['thema'] == 'b'
    assert eo.vertrag_finden(vertraege, 'Police 702 213446')['thema'] == 'a'


def test_vertrag_legt_ab_wie_eine_regel_mit_bezuegen(repo):
    # huk steht unter "pruefen": ohne Vertrag landete die Mail im Eingang
    b = lauf(repo, [m('HUK <info@kundendialog.huk-coburg.de>',
                      'Ihre eVB-Nummer zum Vertrag 624/220429-P')])
    assert b.notiz == 1
    pfad = os.path.join(repo, 'notizen', '2026', 'versicherungen')
    n = lesen(os.path.join(pfad, os.listdir(pfad)[0]))
    assert n.meta['themen'] == ['versicherungen', 'steuer']
    assert n.meta['objekte'] == ['auto'] and n.meta['steuer'] == ['vorsorge']
    assert n.meta['ablage'] == '0-2026/08Versicherungen/07Kfz_624_220429-P'
    assert n.meta['eingeordnet_durch'] == 'vertrag/624/220429-P'
    assert daten.pruefen(repo) == []


def test_vertrag_im_mailtext_reicht(repo):
    assert lauf(repo, [m('x@huk.de', 'Ihre Unterlagen', text='zu Vertrag 624 220429-P')]).notiz == 1


# --- Versicherung pruefen fragt jetzt die KI ---------------------------------

def test_versicherung_fragt_ki_bleibt_aber_im_eingang(repo):
    ki, gesendet = ki_mit({'vorschlaege': [
        {'thema': 'versicherungen', 'unterordner': 'HUK/08Kfz', 'personen': ['anna'],
         'weitere_themen': ['steuer', 'erfunden'], 'objekte': ['auto'], 'steuer': ['vorsorge'],
         'konfidenz': 0.95, 'grund': 'eVB ist Kfz'}]})
    b = lauf(repo, [m('info@huk.de', 'Ihre Hausrat-Police')], ki)
    assert b.offen == 1 and len(gesendet) == 1
    inhalt = gesendet[0]['messages'][0]['content']
    assert 'Objekte: haus (Eigenheim), auto (Auto)' in inhalt
    assert '624/220429-P: Kfz-Versicherung -> versicherungen/07Kfz_624_220429-P' in inhalt
    v = nz.lesen(open(os.path.join(repo, 'eingang', os.listdir(os.path.join(repo, 'eingang'))[0]),
                      encoding='utf-8').read()).meta['vorschlag']
    assert (v['thema'], v['unterordner'], v['durch']) == ('versicherungen', 'HUK/08Kfz', 'ki/test/modell')
    assert v['weitere_themen'] == ['steuer'] and v['objekte'] == ['auto']


# --- Neue Vorschlaege auf Anforderung -----------------------------------------

def eingang_anlegen(repo, nid, anfordern, quelle='gmx', text='Ihr Fahrzeug ist zugelassen.'):
    pfad = os.path.join(repo, 'eingang', nid + '.md')
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    meta = {'id': nid, 'erstellt': datetime.date(2026, 11, 1), 'quelle': quelle, 'personen': [],
            'themen': [], 'absender': 'info@huk.de', 'vorschlag_anfordern': anfordern,
            'vorschlag': {'thema': 'versicherungen', 'unterordner': '01Hausrat', 'konfidenz': 0.4}}
    with open(pfad, 'w', encoding='utf-8') as fh:
        fh.write(nz.schreiben(nz.Notiz(meta=meta, text='# Ihre eVB-Nummer\n\n' + text + '\n')))
    return pfad


def test_neue_vorschlaege_mit_hinweis(repo):
    pfad = eingang_anlegen(repo, 'evb', 'neues Auto, Kfz-Versicherung')
    andere = eingang_anlegen(repo, 'gmail-mail', True, quelle='gmail')
    ki, gesendet = ki_mit({'vorschlaege': [
        {'thema': 'versicherungen', 'unterordner': 'HUK/08Kfz', 'personen': ['anna'], 'konfidenz': 0.9},
        {'thema': 'steuer', 'personen': ['anna'], 'konfidenz': 0.5}]})
    assert mail.neue_vorschlaege(repo, 'gmx', ki, heute=HEUTE) == (1, 0)
    assert 'Hinweis von Harald zu dieser Mail (hat Vorrang): neues Auto' in gesendet[0]['messages'][0]['content']
    n = lesen(pfad)
    assert 'vorschlag_anfordern' not in n.meta
    assert n.meta['vorschlag']['unterordner'] == 'HUK/08Kfz'
    assert n.meta['vorschlag']['alternativen'][0]['thema'] == 'steuer'
    assert lesen(andere).meta['vorschlag_anfordern'] is True  # anderes Konto
    assert 'Neue Vorschläge für `evb` (Hinweis: neues Auto' in open(
        os.path.join(repo, 'protokoll', '2026-11.md'), encoding='utf-8').read()


def test_neue_vorschlaege_vertrag_zuerst(repo):
    pfad = eingang_anlegen(repo, 'evb', True, text='zum Vertrag 624/220429-P')
    ki, _ = ki_mit({'vorschlaege': [{'thema': 'steuer', 'personen': ['anna'], 'konfidenz': 0.7}]})
    mail.neue_vorschlaege(repo, 'gmx', ki, daten.vertraege(repo), ['anna'], heute=HEUTE)
    v = lesen(pfad).meta['vorschlag']
    assert (v['durch'], v['konfidenz']) == ('vertrag/624/220429-P', 1.0)
    assert v['alternativen'][0]['thema'] == 'steuer'


def test_neue_vorschlaege_ohne_ki(repo):
    pfad = eingang_anlegen(repo, 'evb', True)
    assert mail.neue_vorschlaege(repo, 'gmx', None, heute=HEUTE) == (0, 1)
    n = lesen(pfad)
    assert n.meta['vorschlag_fehler'] == 'KI nicht eingerichtet'
    assert n.meta['vorschlag']['unterordner'] == '01Hausrat'  # alter Vorschlag bleibt


# --- Pruefen ---------------------------------------------------------------

def test_pruefen_meldet_unbekannte_bezuege(repo):
    with open(os.path.join(repo, 'config', 'vertraege.yaml'), 'a', encoding='utf-8') as fh:
        fh.write('  - nummer: "123"\n    thema: versicherungen\n    objekte: [boot]\n')
    fehler = [f for _, f in daten.pruefen(repo)]
    assert 'Vertrag 2: nummer zu kurz (mind. 5 Zeichen)' in fehler
    assert 'Vertrag 2: Objekt unbekannt: boot' in fehler


# --- Vertragsnummer im Ordnernamen -------------------------------------------

def test_nummern_ohne_trennzeichen():
    assert eo.nummern('Vertrag 624/220429-P vom 1.11.') == {'624220429'}
    assert eo.nummern('01HUK_Hausrat_702_213446') == {'702213446'}


def test_andere_vertragsnummer_im_betreff_senkt_vorschlag(repo):
    # Ablagewissen kennt nur "huk" -> Hausrat; der Betreff nennt aber einen anderen Vertrag
    lerner = eo.Lerner([], daten.themen(repo), ['anna'], wissen=[
        {'name': 'HUK Hausrat', 'muster': ['huk'], 'thema': 'versicherungen',
         'unterordner': '01HUK_Hausrat_702_213446'}])
    v = lerner.vorschlag('info@huk.de', 'Ihre eVB-Nummer zum Vertrag 111/222333-P')
    assert v.konfidenz == 0.15 and 'andere Vertragsnummer' in v.grund


def test_ordner_mit_derselben_nummer_wird_vorgeschlagen(repo):
    lerner = eo.Lerner([], daten.themen(repo), ['anna'], wissen=[
        {'name': 'HUK Hausrat', 'muster': ['huk'], 'thema': 'versicherungen',
         'unterordner': '01HUK_Hausrat_702_213446'}],
        ordner={'versicherungen': {'01HUK_Hausrat_702_213446', 'HUK/07Kfz_111_222333-P'}})
    v = lerner.vorschlag('info@huk.de', 'Ihre eVB-Nummer zum Vertrag 111/222333-P')
    assert (v.unterordner, v.konfidenz, v.durch) == ('HUK/07Kfz_111_222333-P', 0.9, 'heuristik/vertragsnummer')
    assert v.alternativen[0].konfidenz == 0.15


def test_ki_vorschlag_mit_falscher_nummer_rutscht_nach_hinten(repo):
    os.remove(os.path.join(repo, 'config', 'vertraege.yaml'))
    ki, _ = ki_mit({'vorschlaege': [
        {'thema': 'versicherungen', 'unterordner': '03HUK_Privathaftpflicht702213446-Y-16',
         'personen': ['anna'], 'konfidenz': 0.9},
        {'thema': 'versicherungen', 'unterordner': 'HUK/Kfz', 'personen': ['anna'], 'konfidenz': 0.5}]})
    lauf(repo, [m('info@huk.de', 'Ihre eVB-Nummer zum Vertrag 624/220429-P')], ki)
    v = nz.lesen(open(os.path.join(repo, 'eingang', os.listdir(os.path.join(repo, 'eingang'))[0]),
                      encoding='utf-8').read()).meta['vorschlag']
    assert v['unterordner'] == 'HUK/Kfz'
    assert v['alternativen'][0]['konfidenz'] == 0.15


def test_bestehende_ordner_nur_aus_ordnerliste(repo):
    # Ziele aus Ablagewissen gelten nicht als bestehend, nur die Ordnerliste (Drive-Baum)
    with open(os.path.join(repo, 'config', 'ordner.yaml'), 'w', encoding='utf-8') as fh:
        fh.write('ordner:\n  versicherungen:\n  - 05Echt\n  - 05Echt/Unter\n')
    bekannt = daten.bekannte_unterordner(repo)
    assert {'05Echt', '05Echt/Unter'} <= bekannt['versicherungen']
    assert '01Hausrat' not in bekannt.get('versicherungen', set())
