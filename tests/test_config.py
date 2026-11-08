import pytest

from invoice_manager.config import Config, load_config


def test_default_keywords_query():
    q = Config().full_query()
    assert q == (
        "has:attachment {subject:Facture subject:Facturation subject:Invoice "
        "filename:Facture filename:Facturation filename:Invoice} "
        "-label:invoices-processed newer_than:1y"
    )


def test_keywords_from_file(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('keywords = ["Facture", "Avis de paiement"]\nrequire_attachment = false\n'
                 'extra_query = "-from:promo@x.com"\nnewer_than = ""\nprocessed_label = ""\n')
    cfg = load_config(p)
    assert cfg.keywords == ["Facture", "Avis de paiement"]
    assert cfg.full_query() == (
        '{subject:Facture subject:"Avis de paiement" filename:Facture '
        'filename:"Avis de paiement"} -from:promo@x.com'
    )


def test_query_overrides_keywords(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('query = "from:edf.fr"\nnewer_than = ""\n')
    assert load_config(p).full_query() == "from:edf.fr -label:invoices-processed"


def test_bad_keywords(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('keywords = "Facture"\n')
    with pytest.raises(ValueError, match="list of strings"):
        load_config(p)
    with pytest.raises(ValueError, match="No keywords"):
        Config(keywords=[]).full_query()


def test_account_from_file(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('account = "me@gmail.com"\n')
    assert load_config(p).account == "me@gmail.com"


def test_password_key_rejected(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('account = "me@gmail.com"\npassword = "secret"\n')
    with pytest.raises(ValueError, match="password"):
        load_config(p)


def test_check_account():
    from pathlib import Path

    from invoice_manager.gmail import WrongAccountError, check_account

    check_account("Me@Gmail.com", "me@gmail.com", Path("token.json"))
    check_account("me@gmail.com", "", Path("token.json"))
    with pytest.raises(WrongAccountError, match="Delete token.json"):
        check_account("other@gmail.com", "me@gmail.com", Path("token.json"))


def test_invoices_dir(tmp_path):
    from pathlib import Path

    assert Config().files_dir == Path("data/files")
    p = tmp_path / "config.toml"
    p.write_text('invoices_dir = "~/Factures"\ndata_dir = "reg"\n')
    cfg = load_config(p)
    assert cfg.files_dir == Path.home() / "Factures"
    assert cfg.db_path == Path("reg/invoices.db")
    p.write_text('invoices_dir = ""\n')
    assert load_config(p).files_dir == Path("data/files")


def test_fetch_uses_invoices_dir(tmp_path):
    from test_fetch import FakeSource, _msg

    from invoice_manager.fetcher import fetch
    from invoice_manager.store import Store

    cfg = Config(data_dir=tmp_path / "data", invoices_dir=tmp_path / "Factures")
    store = Store(cfg.db_path)
    fetch(FakeSource({"m1": _msg("m1", {"a.xml": b"Total 10,00 EUR"})}), store, cfg, log=lambda *_: None)
    saved = store.list()[0]["file_path"]
    assert saved.startswith(str(tmp_path / "Factures" / "2024" / "03"))
