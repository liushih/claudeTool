import pytest

from runtime.adapter import Entity, Step
from runtime.runner import RunError, run_entity


class _FakeClient:
    def __init__(self, mapping):
        self.mapping = mapping
        self.last_json = None

    def request(self, method, path, json=None, params=None):
        self.last_json = json
        return self.mapping[f"{method} {path}"]


class _FakeClientSeq:
    def __init__(self, seq):
        self.seq = list(seq)
        self.i = 0

    def request(self, method, path, json=None, params=None):
        item = self.seq[min(self.i, len(self.seq) - 1)]
        self.i += 1
        return item


def _entity(steps):
    return Entity(id="e", description="t", steps=steps)


def _ctx():
    return {"external_no": "T", "values": {}, "stage": "init"}


def test_call_step_substitutes_vars():
    client = _FakeClient({"POST /x": {"id": 7}})
    entity = _entity([Step(id="create", call="POST /x", body={"no": "${ctx.external_no}"})])
    out = run_entity(entity, client, _ctx())
    assert out["values"]["create"]["id"] == 7
    assert client.last_json == {"no": "T"}


def test_poll_step_until_true():
    client = _FakeClientSeq([{"status": None}, {"status": "OK"}])
    entity = _entity([Step(id="wait", poll="GET /x", until="resp['status'] == 'OK'", timeout=5)])
    out = run_entity(entity, client, _ctx())
    assert out["values"]["wait"]["status"] == "OK"


def test_poll_timeout_raises():
    client = _FakeClientSeq([{"status": None}])
    entity = _entity([Step(id="wait", poll="GET /x", until="resp['status'] == 'OK'", timeout=0)])
    with pytest.raises(RunError, match="timeout"):
        run_entity(entity, client, _ctx())


def test_impl_step_loads_function(tmp_path):
    (tmp_path / "hook.py").write_text(
        "def go(ctx, resp):\n    return {'ok': True}\n", encoding="utf-8"
    )
    entity = _entity([Step(id="hook", impl="hook.py:go")])
    out = run_entity(entity, _FakeClient({}), _ctx(), impl_root=tmp_path)
    assert out["values"]["hook"] == {"ok": True}
