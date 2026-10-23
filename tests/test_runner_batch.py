from runtime.adapter import Entity, Step
from runtime.ledger import Ledger
from runtime.runner import run_batch


class _RecordingClient:
    def __init__(self, calls):
        self.calls = calls

    def request(self, method, path, json=None, params=None):
        self.calls.append(int(str(json["no"])[-1]))
        return {"ok": True}


def _entity_ok():
    return Entity(
        id="e",
        description="t",
        steps=[Step(id="create", call="POST /x", body={"no": "${ctx.external_no}"})],
    )


def _entity_boom():
    return Entity(
        id="e",
        description="t",
        steps=[Step(id="wait", poll="GET /x", until="False", timeout=0)],
    )


def test_skips_done_indexes(tmp_path):
    lg = Ledger(tmp_path / "l.csv")
    lg.append({"run_id": "r", "idx": 0, "status": "done"})
    calls = []
    out = run_batch(_entity_ok(), lambda: _RecordingClient(calls), count=3, workers=2, run_id="r", ledger=lg)
    assert out["done"] == 2
    assert sorted(calls) == [1, 2]


def test_counts_failures_and_records(tmp_path):
    lg = Ledger(tmp_path / "l.csv")
    out = run_batch(_entity_boom(), lambda: _RecordingClient([]), count=2, workers=1, run_id="r", ledger=lg)
    assert out["failed"] == 2
    assert len(out["failures"]) == 2
    lines = (tmp_path / "l.csv").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3


def test_resume_same_run_id_skips_previous(tmp_path):
    lg = Ledger(tmp_path / "l.csv")
    run_batch(_entity_ok(), lambda: _RecordingClient([]), count=2, workers=1, run_id="r", ledger=lg)
    out = run_batch(_entity_ok(), lambda: _RecordingClient([]), count=2, workers=1, run_id="r", ledger=lg)
    assert out["done"] == 0


def test_uses_entity_id_rule(tmp_path):
    lg = Ledger(tmp_path / "l.csv")
    seen = []

    class _C:
        def request(self, method, path, json=None, params=None):
            seen.append(json["no"])
            return {}

    entity = Entity(
        id="e",
        description="t",
        id_rule="PB{run_id}{idx:04d}",
        steps=[Step(id="create", call="POST /x", body={"no": "${ctx.external_no}"})],
    )
    run_batch(entity, lambda: _C(), count=1, workers=1, run_id="r", ledger=lg)
    assert seen == ["PBr0000"]
