import pytest

from invoice_manager.cli import main
from invoice_manager.store import NewInvoice, Store


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    s = Store(tmp_path / "data" / "invoices.db")
    s.add(NewInvoice("m1", "EDF <a@edf.fr>", "Facture", "2026-10-14T09:00:00", "f.pdf", "f.pdf",
                     "h1", "EDF", "FA-1", None, 87.4, "EUR"))
    s.close()
    return tmp_path


def test_export_excel(workdir):
    assert main(["export", "--excel", "-o", "out.csv"]) == 0
    raw = (workdir / "out.csv").read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")  # BOM
    line = raw.decode("utf-8-sig").splitlines()[1]
    assert ";87,40;EUR;" in line


def test_invalid_date_rejected(workdir, capsys):
    with pytest.raises(SystemExit):
        main(["pay", "1", "--on", "05/11/2026"])
    assert "expected YYYY-MM-DD" in capsys.readouterr().err


def test_pay(workdir, capsys):
    assert main(["pay", "1", "--on", "2026-11-05"]) == 0
    main(["list", "--status", "paid"])
    assert "EDF" in capsys.readouterr().out
