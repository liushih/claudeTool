import json
import threading
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from runtime.report_config import ZentaoConfig
from runtime.zentao import ZentaoClient, ZentaoError, collect_zentao

TASKS_P1 = {
    "tasks": [
        {"id": 1, "name": "任务一", "status": "done", "finishedDate": "2026-10-21"},
        {"id": 2, "name": "任务二", "status": "done", "finishedDate": "2026-09-01"},
    ],
    "total": "2",
}
TASKS_P2 = {"tasks": [], "total": "2"}
BUGS = {"bugs": [{"id": 9, "title": "Bug 一", "status": "resolved", "resolvedDate": "2026-10-22"}]}


class _Handler(BaseHTTPRequestHandler):
    def _send(self, payload):
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        self._send({"status": "success", "token": "tok-1"})

    def do_GET(self):
        if self.path.startswith("/api.php/v2/projects/73/executions"):
            self._send({"executions": [{"id": 101}, {"id": 102}], "total": "2"})
        elif "/executions/101/tasks" in self.path:
            self._send(TASKS_P1 if "pageID=1" in self.path else TASKS_P2)
        elif "/executions/102/tasks" in self.path:
            self._send({"tasks": [], "total": "0"})
        elif "/products/31/bugs" in self.path:
            self._send(BUGS)
        else:
            self._send({"status": "fail", "message": "nope"})

    def log_message(self, *args):
        pass


@pytest.fixture
def server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


def test_client_logs_in_and_sends_token(server, tmp_path):
    client = ZentaoClient(server, "me", "pw", cache_path=tmp_path / "t.json")
    assert client.login() == "tok-1"
    assert client.get("/projects/73/executions")["executions"][0]["id"] == 101


def test_failed_login_raises(tmp_path):
    client = ZentaoClient("http://127.0.0.1:1", "me", "pw", cache_path=tmp_path / "t.json")
    with pytest.raises(ZentaoError, match="登录"):
        client.login()


def test_collects_completed_items_in_range(server):
    cfg = ZentaoConfig(api="v2", base_url=server, account="me", password="pw",
                       product_id=31, project_ids=[73])
    tasks, bugs, warnings = collect_zentao(cfg, date(2026, 10, 19), date(2026, 10, 25))
    assert [t["id"] for t in tasks] == [1]
    assert [b["id"] for b in bugs] == [9]
    assert warnings == []


def test_unreachable_zentao_returns_warning():
    cfg = ZentaoConfig(api="v2", base_url="http://127.0.0.1:1", account="me", password="pw",
                       product_id=31, project_ids=[73])
    tasks, bugs, warnings = collect_zentao(cfg, date(2026, 10, 19), date(2026, 10, 25))
    assert tasks == [] and bugs == []
    assert warnings and "禅道" in warnings[0]


def test_pagination_mismatch_adds_warning(server, monkeypatch):
    import runtime.zentao as zt

    real = zt._items_from
    monkeypatch.setattr(zt, "_items_from", lambda payload, key: real(payload, key)[:1])

    cfg = ZentaoConfig(api="v2", base_url=server, account="me", password="pw",
                       product_id=31, project_ids=[73])
    _tasks, _bugs, warnings = collect_zentao(cfg, date(2026, 10, 19), date(2026, 10, 25))
    assert any("total" in w or "未拉全" in w for w in warnings)


def test_item_without_date_is_warned_not_dropped(server, monkeypatch):
    import runtime.zentao as zt

    def fake_items(payload, key):
        if key == "executions":
            return payload.get("executions", [])
        if key == "tasks":
            return [{"id": 3, "name": "无日期任务"}]
        return payload.get(key, [])

    monkeypatch.setattr(zt, "_items_from", fake_items)
    cfg = ZentaoConfig(api="v2", base_url=server, account="me", password="pw",
                       product_id=31, project_ids=[73])
    _tasks, _bugs, warnings = collect_zentao(cfg, date(2026, 10, 19), date(2026, 10, 25))
    assert any("未解析" in w for w in warnings)
