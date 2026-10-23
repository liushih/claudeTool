import threading

from runtime.ledger import Ledger


def test_append_creates_header_once(tmp_path):
    lg = Ledger(tmp_path / "l.csv")
    lg.append({"run_id": "r1", "idx": 0, "status": "done"})
    lg.append({"run_id": "r1", "idx": 1, "status": "done"})
    lines = (tmp_path / "l.csv").read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("run_id,idx")
    assert len(lines) == 3


def test_read_done_filters_by_run_id(tmp_path):
    lg = Ledger(tmp_path / "l.csv")
    lg.append({"run_id": "r1", "idx": 0, "status": "done"})
    lg.append({"run_id": "r1", "idx": 1, "status": "failed"})
    lg.append({"run_id": "r2", "idx": 0, "status": "done"})
    assert lg.read_done("r1") == {0}


def test_concurrent_append_keeps_all_rows(tmp_path):
    lg = Ledger(tmp_path / "l.csv")
    threads = [
        threading.Thread(target=lg.append, args=({"run_id": "r", "idx": i, "status": "done"},))
        for i in range(50)
    ]
    [t.start() for t in threads]
    [t.join() for t in threads]
    lines = (tmp_path / "l.csv").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 51


def test_header_carries_no_business_columns(tmp_path):
    lg = Ledger(tmp_path / "l.csv")
    lg.append({"run_id": "r", "idx": 0, "status": "done"})
    header = (tmp_path / "l.csv").read_text(encoding="utf-8").splitlines()[0]
    for column in ("order_no", "package_nos", "out_nos", "picking_order_no", "delivery_nos"):
        assert column not in header
