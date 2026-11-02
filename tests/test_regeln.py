import pytest

from second_brain import regeln as rg

T = rg.Teile


def regel(name, *wenn, art='ordner', **dann):
    return {'name': name, 'art': art, 'wenn': list(wenn), 'dann': dann}


def b(teil, *werte, vergleich='wort'):
    return {'teil': teil, 'vergleich': vergleich, 'werte': list(werte)}


@pytest.mark.parametrize('text,passt', [
    ('Ihr Auto ist fertig', True),
    ('automatisch erstellt', False),      # kein Wortteil mehr
    ('AUTO-Versicherung', True),
    ('Gebäude', False),
])
def test_ganzes_wort(text, passt):
    r = regel('a', b('betreff', 'auto'), thema='kfz')
    assert (rg.regel_trifft(r, T(betreff=text)) is not None) == passt


def test_umlaute_sind_egal():
    r = regel('g', b('betreff', 'gebaeude'), thema='x')
    assert rg.regel_trifft(r, T(betreff='Wohngebäude Kieler 37')) is None  # Wortteil
    assert rg.regel_trifft(regel('g', b('betreff', 'wohngebäude'), thema='x'),
                           T(betreff='Wohngebaeude Kieler 37')) is not None


def test_wortteil_nur_ausdruecklich():
    r = regel('w', b('betreff', 'gebaeude', vergleich='wortteil'), thema='x')
    assert rg.regel_trifft(r, T(betreff='Wohngebäude')) is not None


@pytest.mark.parametrize('text', ['Vertrag 624/220429-P', 'Vertrag 624 220429 P',
                                  'vertrag 624220429p', 'Nr. 624-220429-P.'])
def test_nummer_mit_beliebigen_trennzeichen(text):
    r = regel('k', b('ueberall', '624/220429-P', vergleich='nummer'), thema='x')
    assert rg.regel_trifft(r, T(anhangtext=text)) == [{'teil': 'ueberall', 'wert': '624/220429-P'}]


@pytest.mark.parametrize('text', ['1624/220429-P', '624/220429-P1', '624/22042'])
def test_nummer_nur_als_ganzes(text):
    r = regel('k', b('ueberall', '624/220429-P', vergleich='nummer'), thema='x')
    assert rg.regel_trifft(r, T(betreff=text)) is None


def test_alle_bedingungen_und_ausschluss():
    r = regel('huk-hausrat', b('absender', 'huk-coburg.de'), b('betreff', 'hausrat', 'household'),
              b('betreff', 'kfz', vergleich='nicht'), thema='versicherungen')
    assert rg.regel_trifft(r, T(absender='a@huk-coburg.de', betreff='Hausrat 2027'))
    assert rg.regel_trifft(r, T(absender='a@huk-coburg.de', betreff='Hausrat und Kfz')) is None
    assert rg.regel_trifft(r, T(absender='a@vkb.de', betreff='Hausrat')) is None


def test_nur_ausschluss_passt_nie():
    assert rg.regel_trifft(regel('n', b('betreff', 'x', vergleich='nicht'), thema='t'),
                           T(betreff='y')) is None


def test_eindeutig_sonst_konflikt():
    rw = {'regeln': [regel('a', b('absender', 'ionos.de'), thema='edv', unterordner='ionos'),
                     regel('b', b('betreff', 'rechnung'), thema='sonstiges')]}
    e = rg.einordnen(T(absender='x@ionos.de', betreff='Ihre Rechnung'), True, rw)
    assert e.aktion == rg.OFFEN and e.konflikt == ['a', 'b']
    e = rg.einordnen(T(absender='x@ionos.de', betreff='Info'), True, rw)
    assert (e.aktion, e.unterordner, e.durch) == (rg.NOTIZ, 'ionos', 'regel/a')


def test_merkmalregel_entscheidet_allein_nichts_ergaenzt_aber():
    rw = {'standard_personen': ['harald'], 'regeln': [
        regel('ionos', b('absender', 'ionos.de'), thema='edv'),
        regel('samantha', b('empfaenger', 'samantha@x.de'), art='merkmal', personen=['samantha']),
        regel('lohn', b('anhangtext', 'arbeitskosten'), art='merkmal', steuer=['h.35a'])]}
    assert rg.einordnen(T(empfaenger='samantha@x.de'), True, rw) is None
    e = rg.einordnen(T(absender='a@ionos.de', empfaenger='samantha@x.de',
                       anhangtext='Arbeitskosten 10,00'), True, rw)
    assert e.personen == ['samantha'] and e.steuer == ['h.35a']
    assert {t['regel'] for t in e.treffer} == {'ionos', 'samantha', 'lohn'}
    assert rg.einordnen(T(absender='a@ionos.de'), True, rw).personen == ['harald']


def test_ohne_dokument_nur_index_ausser_ohne_anhang():
    rw = {'regeln': [regel('a', b('absender', 'bahn.de'), thema='urlaub')]}
    assert rg.einordnen(T(absender='x@bahn.de'), False, rw).aktion == rg.INDEX
    rw['regeln'][0]['dann']['ohne_anhang'] = True
    assert rg.einordnen(T(absender='x@bahn.de'), False, rw).aktion == rg.NOTIZ


def test_aussortieren():
    rw = {'regeln': [regel('werbung', b('absender', 'newsletter'), art='aussortieren')]}
    e = rg.einordnen(T(absender='newsletter@shop.de'), False, rw)
    assert e.aktion == rg.VERWERFEN and e.durch == 'regel/werbung'


def test_wert_im_ordner():
    assert rg.wert_im_ordner(regel('k', b('ueberall', '624/220429-P', vergleich='nummer'),
                                   thema='v', unterordner='07HUK_Kfz_624_220429-P'))
    assert rg.wert_im_ordner(regel('i', b('absender', 'ionos.de'), thema='edv', unterordner='ionos'))
    assert not rg.wert_im_ordner(regel('i', b('absender', 'ionos.de'), thema='edv',
                                       unterordner='Weitere Kosten'))


def test_regel_fehler():
    f = rg.regel_fehler(regel('X y', b('betreff', vergleich='nummer'), thema='gibtsnicht'),
                        themen={'edv'})
    assert any('Name' in x for x in f) and 'Bedingung ohne Werte' in f
    assert 'Thema unbekannt: gibtsnicht' in f
    assert rg.regel_fehler(regel('m', b('betreff', 'x'), art='merkmal', thema='edv'),
                           themen={'edv'}) == ['Merkmalregel darf keinen Ordner setzen',
                                               'Merkmalregel setzt nichts']
    assert 'Nummer zu kurz (mind. 5 Zeichen): 12' in rg.regel_fehler(
        regel('n', b('betreff', '12', vergleich='nummer'), thema='edv'))


def test_pruefen_gegen_bestand():
    rw = {'regeln': [regel('alt', b('betreff', 'rechnung'), thema='sonstiges')]}
    neu = regel('neu', b('absender', 'ionos.de'), thema='edv')
    bestand = [{'id': '1', 'absender': 'a@ionos.de', 'betreff': 'Rechnung'},
               {'id': '2', 'absender': 'a@ionos.de', 'betreff': 'Info'},
               {'id': '3', 'absender': 'a@x.de', 'betreff': 'Rechnung'}]
    passt, konflikte = rg.pruefen_gegen_bestand(neu, rw, bestand)
    assert [e['id'] for e in passt] == ['1', '2']
    assert [(e['id'], n) for e, n in konflikte] == [('1', ['alt'])]
