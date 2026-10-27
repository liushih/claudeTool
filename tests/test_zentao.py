import json
import threading
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from runtime.report_config import ZentaoConfig
from runtime.zentao import ZentaoClient, ZentaoError, collect_zentao

TASKS_P1 = {
    "tasks": [
        {"id": 1, "name": "任务一", "status": "done", "finishedDate": "2026-10-21", "finishedBy": "me"},
        {"id": 2, "name": "任务二", "status": "done", "finishedDate": "2026-09-01", "finishedBy": "me"},
    ],
    "total": "2",
}
TASKS_P2 = {"tasks": [], "total": "2"}
BUGS = {
    "bugs": [
        {
            "id": 9,
            "title": "Bug 一",
            "status": "resolved",
            "resolvedDate": "2026-10-22",
            "resolvedBy": "me",
        }
    ]
}


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


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    cache = tmp_path / "zentao-cache.json"
    monkeypatch.setenv("ZENTAO_TOKEN_CACHE", str(cache))
    return cache


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


def test_cache_path_defaults_to_env_override(server, isolated_cache):
    client = ZentaoClient(server, "me", "pw")
    client.login()
    assert isolated_cache.exists()


def test_forced_relogin_without_password_is_actionable(server, tmp_path):
    cache = tmp_path / "stale.json"
    cache.write_text(
        json.dumps({"url": server, "token": "stale", "account": "me"}), encoding="utf-8"
    )
    client = ZentaoClient(server, "me", "", cache_path=cache)
    with pytest.raises(ZentaoError, match="password"):
        client.login(force=True)


def test_pages_warns_when_key_absent():
    from runtime.zentao import _pages

    class _Client:
        def get(self, path, params=None):
            return {"data": []}

    warnings: list[str] = []
    items = _pages(_Client(), "/tasks", "tasks", {}, warnings)
    assert items == []
    assert any("tasks" in warning for warning in warnings)


def test_v1_api_is_rejected_explicitly():
    cfg = ZentaoConfig(api="v1", base_url="http://127.0.0.1:1", account="me")
    tasks, bugs, warnings = collect_zentao(cfg, date(2026, 10, 1), date(2026, 10, 7))
    assert tasks == [] and bugs == []
    assert any("v1" in warning and "未实现" in warning for warning in warnings)


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


def _cfg(server):
    return ZentaoConfig(api="v2", base_url=server, account="me", password="pw",
                        product_id=31, project_ids=[73])


def test_unfinished_task_is_skipped_without_warning(server, monkeypatch):
    import runtime.zentao as zt

    def fake_items(payload, key):
        if key == "executions":
            return payload.get("executions", [])
        if key == "tasks":
            return [{"id": 3, "name": "未完成任务", "status": "wait"}]
        return payload.get(key, [])

    monkeypatch.setattr(zt, "_items_from", fake_items)
    tasks, _bugs, warnings = collect_zentao(_cfg(server), date(2026, 10, 19), date(2026, 10, 25))
    assert tasks == []
    assert [w for w in warnings if "未解析" in w or "完成人" in w] == []


def test_items_finished_or_resolved_by_others_are_excluded(server, monkeypatch):
    import runtime.zentao as zt

    def fake_items(payload, key):
        if key == "executions":
            return payload.get("executions", [])
        if key == "tasks":
            return [{"id": 4, "name": "别人的任务", "finishedDate": "2026-10-21", "finishedBy": "someone"}]
        if key == "bugs":
            return [{"id": 10, "title": "别人的 Bug", "resolvedDate": "2026-10-22", "resolvedBy": "someone"}]
        return payload.get(key, [])

    monkeypatch.setattr(zt, "_items_from", fake_items)
    tasks, bugs, warnings = collect_zentao(_cfg(server), date(2026, 10, 19), date(2026, 10, 25))
    assert tasks == [] and bugs == []
    assert [w for w in warnings if "未解析" in w or "完成人" in w] == []


def test_invalid_date_is_warned(server, monkeypatch):
    import runtime.zentao as zt

    def fake_items(payload, key):
        if key == "executions":
            return payload.get("executions", [])
        if key == "tasks":
            return [{"id": 5, "name": "坏日期", "finishedDate": "not-a-date", "finishedBy": "me"}]
        return payload.get(key, [])

    monkeypatch.setattr(zt, "_items_from", fake_items)
    _tasks, _bugs, warnings = collect_zentao(_cfg(server), date(2026, 10, 19), date(2026, 10, 25))
    assert any("未解析" in w for w in warnings)


def test_missing_owner_is_warned(server, monkeypatch):
    import runtime.zentao as zt

    def fake_items(payload, key):
        if key == "executions":
            return payload.get("executions", [])
        if key == "tasks":
            return [{"id": 6, "name": "无完成人", "finishedDate": "2026-10-21"}]
        return payload.get(key, [])

    monkeypatch.setattr(zt, "_items_from", fake_items)
    _tasks, _bugs, warnings = collect_zentao(_cfg(server), date(2026, 10, 19), date(2026, 10, 25))
    assert any("完成人" in w for w in warnings)


def test_missing_account_and_authors_collects_nothing():
    cfg = ZentaoConfig(api="v2", base_url="http://127.0.0.1:1", account="", product_id=31, project_ids=[73])
    tasks, bugs, warnings = collect_zentao(cfg, date(2026, 10, 19), date(2026, 10, 25))
    assert tasks == [] and bugs == []
    assert any("按人过滤" in w for w in warnings)
