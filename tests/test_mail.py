import datetime
import json
import os
import shutil
from email.message import EmailMessage

import pytest

from second_brain import daten, mail, notiz as nz

BEISPIEL = os.path.join(os.path.dirname(__file__), '..', 'beispiel-daten')
HEUTE = datetime.date(2026, 10, 30)


def roh(absender, betreff, text='Hallo', anhang=None, html=False, mid=None):
    m = EmailMessage()
    m['From'] = absender
    m['Subject'] = betreff
    m['Date'] = 'Wed, 28 Oct 2026 10:00:00 +0100'
    m['Message-ID'] = mid or '<%s@test>' % abs(hash((absender, betreff)))
    if html:
        m.set_content('<html><style>x{}</style><p>%s</p></html>' % text, subtype='html')
    else:
        m.set_content(text)
    if anhang:
        m.add_attachment(b'%PDF-1.4 test', maintype='application', subtype='pdf', filename=anhang)
    return m.as_bytes()


@pytest.fixture
def repo(tmp_path):
    ziel = tmp_path / 'daten'
    shutil.copytree(BEISPIEL, ziel)
    return str(ziel)


def lauf(repo, rohmails, anhaenge=None):
    ablage = mail.Ablage(repo, 'gmx', anhang_ziel=anhaenge, heute=HEUTE)
    return mail.verarbeiten([mail.mail_aus_bytes(r) for r in rohmails], ablage,
                            daten.regelwerk(repo))


def test_regel_erzeugt_gueltige_notiz_mit_anhang_ausserhalb(repo, tmp_path):
    anh = tmp_path / 'anhaenge'
    b = lauf(repo, [roh('Hoster <billing@hoster-beispiel.de>', 'Rechnung November',
                        'Betrag 12,00 EUR', anhang='rechnung.pdf')], str(anh))
    assert b.notiz == 1
    pfad = os.path.join(repo, 'notizen', '2026', 'edv',
                        '2026-10-28-hoster-rechnung-november.md')
    with open(pfad, encoding='utf-8') as fh:
        n = nz.lesen(fh.read())
    assert n.meta['ablage'] == '0-2026/31 EDV/hoster'
    assert n.meta['eingeordnet_durch'] == 'regel/hoster'
    assert n.meta['personen'] == ['anna']
    assert 'Betrag 12,00 EUR' in n.text and 'Anhänge: rechnung.pdf' in n.text
    assert (anh / '2026-10-28-hoster-rechnung-november' / 'rechnung.pdf').exists()
    assert not any(f.endswith('.pdf') for _, _, fs in os.walk(repo) for f in fs)
    with open(os.path.join(repo, 'protokoll', '2026-10.md'), encoding='utf-8') as fh:
        assert 'regel/hoster' in fh.read()
    assert daten.pruefen(repo) == []


def test_ohne_regel_und_anhang_kommt_in_den_index(repo):
    b = lauf(repo, [roh('Freund <f@mail.de>', 'Grillen', 'Samstag 18 Uhr', html=True)])
    assert b.index == 1
    with open(os.path.join(repo, 'index', 'mail', '2026-10.jsonl'), encoding='utf-8') as fh:
        zeile = json.loads(fh.readline())
    assert zeile['betreff'] == 'Grillen'
    assert zeile['kurz'] == 'Samstag 18 Uhr'


def test_unbekannt_mit_anhang_landet_im_eingang(repo):
    b = lauf(repo, [roh('wer@irgendwo.de', 'Vertrag', anhang='vertrag.pdf')])
    assert b.offen == 1
    dateien = [d for d in os.listdir(os.path.join(repo, 'eingang')) if d.endswith('.md')]
    assert len(dateien) == 1
    with open(os.path.join(repo, 'eingang', dateien[0]), encoding='utf-8') as fh:
        assert nz.lesen(fh.read()).meta['offen_grund'] == 'unbekannter Absender mit Dokument'


def test_verworfene_mail_bleibt_mit_grund_im_index(repo):
    assert lauf(repo, [roh('news@shop.de', 'Newsletter KW 44')]).verwerfen == 1
    assert not os.path.exists(os.path.join(repo, 'eingang'))
    with open(os.path.join(repo, 'index', 'mail', '2026-10.jsonl'), encoding='utf-8') as fh:
        zeile = json.loads(fh.readline())
    assert zeile['verworfen'] == 'Spam/Newsletter: newsletter'


def test_zweiter_lauf_erkennt_bekannte_mails(repo):
    mails = [roh('billing@hoster-beispiel.de', 'Rechnung', mid='<a@x>'),
             roh('f@mail.de', 'Hallo', mid='<b@x>'),
             roh('wer@irgendwo.de', 'Vertrag', anhang='v.pdf', mid='<c@x>')]
    lauf(repo, mails)
    b = lauf(repo, mails)
    assert (b.doppelt, b.notiz, b.index, b.offen) == (3, 0, 0, 0)


def test_gleicher_titel_bekommt_eigene_id(repo):
    lauf(repo, [roh('billing@hoster-beispiel.de', 'Rechnung', mid='<1@x>'),
                roh('billing@hoster-beispiel.de', 'Rechnung', mid='<2@x>')])
    ordner = os.path.join(repo, 'notizen', '2026', 'edv')
    assert '2026-10-28-hoster-beispiel-rechnung-2.md' in os.listdir(ordner)
    assert daten.pruefen(repo) == []


def test_jahr_ordner():
    assert mail.jahr_ordner(datetime.date(2026, 3, 1), HEUTE) == '0-2026'
    assert mail.jahr_ordner(datetime.date(2025, 3, 1), HEUTE) == '2025'
