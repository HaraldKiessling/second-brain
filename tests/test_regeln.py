import json
import os

import pytest

from second_brain import regeln

BEISPIEL = os.path.join(os.path.dirname(__file__), '..', 'beispiel-daten')


@pytest.fixture
def regelwerk():
    with open(os.path.join(BEISPIEL, 'regeln', 'mail.json'), encoding='utf-8') as fh:
        return json.load(fh)


def test_spam_wird_verworfen(regelwerk):
    e = regeln.einordnen('news@shop.de', 'Unser Newsletter', True, regelwerk)
    assert e.aktion == regeln.VERWERFEN


def test_regel_nach_absender(regelwerk):
    e = regeln.einordnen('Rechnung <billing@hoster-beispiel.de>', 'Ihre Rechnung', True, regelwerk)
    assert (e.aktion, e.thema, e.unterordner, e.personen) == (regeln.NOTIZ, 'edv', 'hoster', ['anna'])


def test_regel_greift_auch_ohne_anhang(regelwerk):
    e = regeln.einordnen('billing@hoster-beispiel.de', 'Wartung', False, regelwerk)
    assert e.aktion == regeln.NOTIZ


def test_regel_nach_betreff_mit_personen(regelwerk):
    e = regeln.einordnen('poststelle@fa.de', 'Ihr Steuerbescheid 2025', True, regelwerk)
    assert e.thema == 'steuer'
    assert e.personen == ['anna', 'ben']


def test_ohne_regel_und_anhang_nur_index(regelwerk):
    e = regeln.einordnen('freund@mail.de', 'Hallo', False, regelwerk)
    assert e.aktion == regeln.INDEX


def test_versicherung_wird_offen_mit_sparte(regelwerk):
    e = regeln.einordnen('service@huk.de', 'Ihre Hausrat-Police', True, regelwerk)
    assert e.aktion == regeln.OFFEN
    assert 'Hausrat' in e.grund


def test_unbekannt_mit_anhang_ist_offen(regelwerk):
    e = regeln.einordnen('wer@irgendwo.de', 'Dokument', True, regelwerk)
    assert e.aktion == regeln.OFFEN
