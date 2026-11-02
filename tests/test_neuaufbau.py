import json
import os
import shutil

import pytest

from second_brain import cli, neuaufbau as na, regeln

BEISPIEL = os.path.join(os.path.dirname(__file__), '..', 'beispiel-daten')


@pytest.mark.parametrize('name, erwartet', [
    ('07HUK_Kfz_624_220429-P', ['624_220429']),
    ('03HUK_Privathaftpflicht702213446-Y-16', ['702213446-Y-16']),
    ('01Grundabgaben_Kieler35_1142801_GRDABG_1', ['1142801_GRDABG_1']),
    ('01_Gesetzlich_58_130667_K_006', ['58_130667_K_006']),
    ('03_HDI_40-011840459-2', ['40-011840459-2']),
    ('01ARAG_Krankenversicherung_KV00100211610', ['KV00100211610']),
    ('52Piaggia_SAL1T0065061', ['SAL1T0065061']),
    ('01MieteOG_Kieler37_1140Miete_+80Garage_+70NK-1290', []),
    ('05TelekomHarald', []),
])
def test_nummern_im_namen(name, erwartet):
    assert na.nummern_im_namen(name) == erwartet


def test_domain_passt_nur_als_ganzer_name():
    assert na._domain_passt('huk-coburg.de', '11Huk-Coburg_BMW')
    assert na._domain_passt('amazon.de', '01Amazon_Prime')
    assert not na._domain_passt('smart-hosts.co', '07SmartHome')
    assert not na._domain_passt('home-connect.com', '07SmartHome')


@pytest.fixture
def repo(tmp_path):
    ziel = tmp_path / 'daten'
    shutil.copytree(BEISPIEL, ziel)
    with open(ziel / 'config' / 'ordner.yaml', 'w', encoding='utf-8') as fh:
        fh.write('ordner:\n'
                 '  versicherungen:\n'
                 '    - 01Huk-Coburg_BMW\n'
                 '    - 02Huk-Coburg_Renault\n'
                 '    - 03HUK_Kfz_624_220429-P\n'
                 '  edv:\n'
                 '    - 01HUK_Hausrat_702_213446\n'
                 '    - 02HUK_Haftpflicht_702_213446-Y-16\n'
                 '    - Garten\n')
    os.makedirs(ziel / 'index' / 'mail', exist_ok=True)
    with open(ziel / 'index' / 'mail' / '2026-10.jsonl', 'a', encoding='utf-8') as fh:
        fh.write(json.dumps({'message_id': '<x1>', 'datum': '2026-10-02',
                             'absender': 'HUK <info@huk-coburg.de>',
                             'betreff': 'Beitrag BMW', 'kurz': ''}) + '\n')
    return str(ziel)


def test_neuaufbau_vorschlaege_eindeutig(repo):
    liste, ohne = na.vorschlaege(repo)
    nach = {v['dann']['unterordner']: v for v in liste}
    assert nach['03HUK_Kfz_624_220429-P']['wenn'] == [
        {'teil': 'ueberall', 'vergleich': 'nummer', 'werte': ['624_220429']}]
    # gleiche Absender-Domain fuer zwei Ordner: nachgeschaerft mit eigenem Wort
    bmw = nach['01Huk-Coburg_BMW']['wenn']
    assert bmw[0]['werte'] == ['huk-coburg.de'] and bmw[1]['werte'] == ['bmw']
    assert nach['01Huk-Coburg_BMW']['passt'] == 1
    # Hausratnummer steckt in der Haftpflichtnummer: Hausrat bekommt "hausrat"
    assert {'teil': 'ueberall', 'vergleich': 'wortteil', 'werte': ['hausrat']} in \
        nach['01HUK_Hausrat_702_213446']['wenn']
    assert not any(v.get('ueberschneidung') for v in liste)
    assert 'edv/Garten' in ohne
    for v in liste:
        assert v['herkunft'] == 'bestand'
        assert regeln.wert_im_ordner({k: v[k] for k in ('name', 'art', 'wenn', 'dann')})


def test_neuaufbau_cli_schreibt_vorschlaege(repo, capsys):
    assert cli.main(['neuaufbau', repo]) == 0
    with open(os.path.join(repo, 'regeln', 'mail-vorschlaege.json'), encoding='utf-8') as fh:
        d = json.load(fh)
    assert len([v for v in d['vorschlaege'] if v['herkunft'] == 'bestand']) == 5
    assert 'Ordner ohne Vorschlag' in capsys.readouterr().out


@pytest.mark.parametrize('name, doc, erwartet', [
    ('526-041384', '526-41384', True),            # fuehrende Null
    ('702_213446-Y-00', '702/213446-Y-63', True),  # andere Endung
    ('1054125-1039311', '76-1054125', True),      # lange Nummer steckt drin
    ('702_213446-Y-00', '602/718680-P', False),
    ('1142801_GRDABG_1', '1142801/GRDABG/3', False),  # zu kurz gemeinsam
])
def test_variante(name, doc, erwartet):
    assert na.variante(name, doc) is erwartet


def _dokumente(repo, doks):
    pfad = os.path.join(repo, 'doks.json')
    with open(pfad, 'w', encoding='utf-8') as fh:
        json.dump(doks, fh)
    return pfad


def test_neuaufbau_aus_drive_dokumenten(repo, capsys):
    """Ordner ohne Nummer im Namen: die Nummer aus den Briefen im Ordner;
    Ordner mit Nummer: die Schreibweise in den Briefen kommt dazu."""
    brief = 'HUK-COBURG\nREFERENZ BETRIFFT\nCoburg, im Januar 2025 %s Pkw | %s\nSehr geehrter Herr'
    doks = [
        {'ordner': 'versicherungen/01Huk-Coburg_BMW', 'titel': 'a.pdf', 'text': brief % ('602/718680-P', 'BMW')},
        {'ordner': 'versicherungen/01Huk-Coburg_BMW', 'titel': 'b.pdf', 'text': brief % ('602/718680-P', 'BMW')},
        {'ordner': 'versicherungen/02Huk-Coburg_Renault', 'titel': 'c.pdf',
         'text': brief % ('602/724298-A', 'Renault')},
        {'ordner': 'edv/02HUK_Haftpflicht_702_213446-Y-16', 'titel': 'd.pdf',
         'text': 'Vertragsnummer: 702/213446-Y-16 Privat-Haftpflicht'},
        {'ordner': 'edv/Garten', 'titel': 'Zugangsdaten', 'text': 'Passwort: 4711-0815-2233'},
    ]
    assert cli.main(['neuaufbau', repo, '--dokumente', _dokumente(repo, doks)]) == 0
    with open(os.path.join(repo, na.KENNUNGEN), encoding='utf-8') as fh:
        gespeichert = json.load(fh)
    assert 'Passwort' not in json.dumps(gespeichert) and '4711' not in json.dumps(gespeichert)
    assert 'Sehr geehrter' not in json.dumps(gespeichert)  # kein Dokumenttext
    liste, ohne = na.vorschlaege(repo)
    nach = {v['dann']['unterordner']: v for v in liste}
    # die Nummer entscheidet, nicht die Domain, die sich zwei Ordner teilen
    assert nach['01Huk-Coburg_BMW']['wenn'] == [
        {'teil': 'ueberall', 'vergleich': 'nummer', 'werte': ['602/718680-P']}]
    assert '2 von 2 Dokumenten' in nach['01Huk-Coburg_BMW']['grund']
    assert nach['02Huk-Coburg_Renault']['wenn'][0]['werte'] == ['602/724298-A']
    assert 'steht in 1 Dokument im Ordner' in nach['02HUK_Haftpflicht_702_213446-Y-16']['grund']
    # die Hausratnummer steckt im Haftpflichtbrief, ist aber nachgeschaerft
    assert not nach['01HUK_Hausrat_702_213446'].get('ueberschneidung')


def test_kennung_im_fremden_ordner_wird_gemeldet(repo):
    doks = [{'ordner': 'edv/Garten', 'titel': 'x', 'text': 'Ihre Kfz-Versicherung 624/220429-P'},
            {'ordner': 'versicherungen/03HUK_Kfz_624_220429-P', 'titel': 'y', 'text': 'eVB 624/220429-P'}]
    na.kennungen_schreiben(repo, doks, 'Test')
    liste, _ = na.vorschlaege(repo)
    kfz = {v['dann']['unterordner']: v for v in liste}['03HUK_Kfz_624_220429-P']
    assert kfz['ueberschneidung'] == ['edv/Garten']
    assert 'bitte nachschärfen' in kfz['grund']
