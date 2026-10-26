import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class _Handler(BaseHTTPRequestHandler):
    hits: list[dict] = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length)
        type(self).hits.append(json.loads(body or b"{}"))
        payload = b'{"ok": true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


ADAPTER = """version: 1
project: demo
envs:
  dev:
    base_url: ${BASE}
auth:
  type: none
entities:
  order:
    description: 测试单
    id_rule: "E{run_id}{idx:04d}"
    steps:
      - id: create
        call: POST /orders
        body:
          "no": ${ctx.external_no}
"""


def test_cli_end_to_end_and_resume(tmp_path):
    _Handler.hits = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()

    try:
        home = tmp_path / "home"
        project = home / "projects" / "demo"
        project.mkdir(parents=True)
        (project / ".env").write_text(f"BASE=http://127.0.0.1:{port}\n", encoding="utf-8")
        (project / "adapter.yaml").write_text(ADAPTER, encoding="utf-8")

        root = Path(__file__).resolve().parents[1]
        env = {**os.environ, "HEXIN_DATA_HOME": str(home)}

        def run():
            return subprocess.run(
                [sys.executable, str(root / "scripts" / "run.py"),
                 "--project", "demo", "--entity", "order",
                 "--count", "2", "--workers", "2", "--run-id", "e2e"],
                cwd=tmp_path, env=env, capture_output=True, text=True,
            )

        first = run()
        assert first.returncode == 0, first.stderr
        assert len(_Handler.hits) == 2
        assert sorted(hit["no"] for hit in _Handler.hits) == ["Ee2e0000", "Ee2e0001"]

        ledger = (project / "ledger.csv").read_text(encoding="utf-8")
        assert ledger.count(",done") == 2

        second = run()
        assert second.returncode == 0, second.stderr
        assert len(_Handler.hits) == 2
    finally:
        server.shutdown()
        server.server_close()
