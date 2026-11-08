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
