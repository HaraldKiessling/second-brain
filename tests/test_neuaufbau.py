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
    assert {'teil': 'ueberall', 'vergleich': 'wort', 'werte': ['hausrat']} in \
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
