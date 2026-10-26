# 报告生成能力实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 增加日报、周报、月报、述职四种报告的生成能力，数据来自 git 提交与禅道 v2，输出 Markdown 并按需渲染 Word / PPT。

**Architecture:** 三段式：`collect.py` 确定性采集出 JSON；技能读 JSON 并结合用户口述写成 Markdown；`render.py` 从 Markdown 渲染 docx / pptx。AI 只负责中间组织文字，采集与渲染都可单测。

**Tech Stack:** Python 3.11+、PyYAML、requests、python-docx、python-pptx、pytest。

**Spec:** `docs/superpowers/specs/2026-10-26-report-generation-design.md`

## Global Constraints

- 平台：Windows，解释器用仓库内 `.venv/Scripts/python.exe`
- 本地数据根：`~/.data-tools`，可用 `DATA_TOOLS_HOME` 覆盖
- 报告与采集产物只写 `~/.data-tools/`，不进 git
- 禅道 API 版本：v2，基础路径 `/api.php/v2`，Header 携带 `token`
- 凭据只来自项目 `.env` 与 `~/.zentao-token.json`
- 采集只读，不修改任何仓库或禅道数据
- 报告不编造：数据缺失必须显式写出
- 周报用 ISO 周编号，季度用 `YYYY-Qn`

## Review Focus

1. git 仓库路径不存在或不是仓库时，跳过并记录，其它仓库照常采集
2. 禅道分页中途失败时，`sources` 必须标记不完整，报告开头提示
3. 禅道返回的字段名与预期不同时，记录未解析条数，不静默丢弃
4. 项目无法确定（对不上或命中多个）时停止询问，不猜
5. 渲染依赖缺失时，Markdown 仍产出并给出安装提示

---

### Task 1: 时间区间与标签

**Files:**
- Create: `runtime/period.py`
- Test: `tests/test_period.py`

**Interfaces:**
- Produces:
  - `period_range(kind: str, anchor: date | None = None, start: date | None = None, end: date | None = None) -> tuple[date, date]`
  - `period_label(kind: str, start: date, end: date) -> str`

- [ ] **Step 1: Write the failing test**

```python
from datetime import date

import pytest

from runtime.period import period_label, period_range


def test_daily_range_is_the_anchor_day():
    assert period_range("daily", anchor=date(2026, 10, 26)) == (date(2026, 10, 26), date(2026, 10, 26))


def test_weekly_range_starts_monday():
    assert period_range("weekly", anchor=date(2026, 10, 26)) == (date(2026, 10, 26), date(2026, 11, 1))


def test_weekly_range_on_sunday_stays_in_same_week():
    assert period_range("weekly", anchor=date(2026, 11, 1)) == (date(2026, 10, 26), date(2026, 11, 1))


def test_monthly_range_covers_whole_month():
    assert period_range("monthly", anchor=date(2026, 2, 10)) == (date(2026, 2, 1), date(2026, 2, 28))


def test_review_requires_both_ends():
    with pytest.raises(ValueError, match="start"):
        period_range("review", start=date(2026, 7, 1))


def test_review_rejects_reversed_range():
    with pytest.raises(ValueError, match="早于"):
        period_range("review", start=date(2026, 9, 30), end=date(2026, 7, 1))


def test_labels():
    assert period_label("daily", date(2026, 10, 26), date(2026, 10, 26)) == "2026-10-26-daily"
    assert period_label("weekly", date(2026, 10, 26), date(2026, 11, 1)) == "2026-W44-weekly"
    assert period_label("monthly", date(2026, 10, 1), date(2026, 10, 31)) == "2026-10-monthly"
    assert period_label("review", date(2026, 7, 1), date(2026, 9, 30)) == "2026-Q3-review"
    assert period_label("review", date(2026, 1, 1), date(2026, 6, 30)) == "2026-01-01_2026-06-30-review"


def test_unknown_kind_raises():
    with pytest.raises(ValueError, match="未知报告类型"):
        period_range("yearly")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_period.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'runtime.period'`

- [ ] **Step 3: Implement `runtime/period.py`**

`anchor` 缺省取 `date.today()`。周从周一开始，用 `anchor - timedelta(days=anchor.weekday())`。月用 `calendar.monthrange`。`review` 未给两端或 `end < start` 时抛 `ValueError`。

标签规则：日 `%Y-%m-%d-daily`；周用 `start.isocalendar()[:2]` 组合 `YYYY-Www-weekly`；月 `%Y-%m-monthly`；述职若区间正好是一个自然季度（起于 1/4/7/10 月 1 日、止于季度末）输出 `YYYY-Qn-review`，否则 `YYYY-MM-DD_YYYY-MM-DD-review`。

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_period.py -q`
Expected: PASS（8 passed）

- [ ] **Step 5: Commit**

```bash
git add runtime/period.py tests/test_period.py
git commit -m "feat: 报告时间区间与标签"
```

---

### Task 2: 配置加载与项目定位

**Files:**
- Modify: `runtime/config.py`（新增公开 `substitute`）
- Modify: `runtime/adapter.py`（改用 `config.substitute`，删除私有副本）
- Create: `runtime/report_config.py`
- Test: `tests/test_report_config.py`、`tests/test_config.py`

**Interfaces:**
- Produces:
  - `config.substitute(value: Any, env: dict[str, str]) -> Any`
  - `ReportConfigError(Exception)`
  - `GitConfig(repos: list[Path], authors: list[str])`
  - `ZentaoConfig(api: str, base_url: str, account: str, password: str, product_id: int | None, project_ids: list[int])`
  - `ReportConfig(git: GitConfig, zentao: ZentaoConfig)`
  - `load_report_config(project_id: str) -> ReportConfig`
  - `match_project(cwd: Path, home: Path | None = None) -> str | None`

- [ ] **Step 1: Write the failing test**

```python
import pytest

from runtime import config
from runtime.report_config import ReportConfigError, load_report_config


def test_substitute_keeps_raw_type():
    assert config.substitute("${N}", {"N": "5"}) == "5"
    assert config.substitute({"a": ["${N}"]}, {"N": "5"}) == {"a": ["5"]}


def test_substitute_reports_missing_var():
    with pytest.raises(config.ConfigError, match="NOPE"):
        config.substitute("${NOPE}", {})


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_TOOLS_HOME", str(tmp_path))
    proj = tmp_path / "projects" / "demo"
    proj.mkdir(parents=True)
    (proj / ".env").write_text("ZENTAO_URL=http://z\nZENTAO_ACCOUNT=me\n", encoding="utf-8")
    (proj / "report.yaml").write_text(
        """git:
  repos: [C:/project/demo]
  authors: [me@example.com]
zentao:
  api: auto
  base_url: ${ZENTAO_URL}
  account: ${ZENTAO_ACCOUNT}
  product_id: 31
  project_ids: [73]
""",
        encoding="utf-8",
    )
    return proj


def test_loads_and_substitutes(project):
    cfg = load_report_config("demo")
    assert cfg.git.repos[0].name == "demo"
    assert cfg.zentao.base_url == "http://z"
    assert cfg.zentao.product_id == 31
    assert cfg.zentao.project_ids == [73]


def test_match_project_by_cwd(project, tmp_path):
    from runtime.report_config import match_project

    assert match_project(tmp_path / "projects" / "demo", tmp_path) == "demo"
    assert match_project(tmp_path, tmp_path) is None


def test_match_project_returns_none_when_ambiguous(tmp_path):
    from runtime.report_config import match_project

    for pid in ("one", "two"):
        proj = tmp_path / "projects" / pid
        proj.mkdir(parents=True)
        (proj / "report.yaml").write_text(
            f"git:\n  repos: [{tmp_path.as_posix()}]\n  authors: [me@x.com]\n", encoding="utf-8"
        )
    assert match_project(tmp_path / "sub", tmp_path) is None


def test_missing_file_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_TOOLS_HOME", str(tmp_path))
    (tmp_path / "projects" / "demo").mkdir(parents=True)
    with pytest.raises(ReportConfigError, match="未找到报告配置"):
        load_report_config("demo")


def test_unknown_api_version_raises(project):
    p = project / "report.yaml"
    p.write_text(p.read_text(encoding="utf-8").replace("api: auto", "api: v9"), encoding="utf-8")
    with pytest.raises(ReportConfigError, match="v9"):
        load_report_config("demo")


def test_no_source_raises(project):
    (project / "report.yaml").write_text("git:\n  repos: []\n  authors: []\n", encoding="utf-8")
    with pytest.raises(ReportConfigError, match="数据源"):
        load_report_config("demo")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_report_config.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'runtime.report_config'`

- [ ] **Step 3: Implement**

在 `runtime/config.py` 里把 `adapter.py` 的 `_VAR` / `_substitute` 提升为公开的 `substitute`，缺失变量抛 `ConfigError("未定义变量 X")`；`adapter.py` 改为调用它并在外层捕获 `ConfigError` 重新抛 `AdapterError`，保持现有 `tests/test_adapter.py` 全部通过（其中一条断言异常类型为 `AdapterError`）。

`runtime/report_config.py` 的校验顺序：文件存在 → YAML 解析 → 对所有字符串做变量替换 → `api` 必须在 `{auto, v1, v2}` → `git.repos` 与 `zentao.base_url` 不能同时为空，否则 `ReportConfigError("report.yaml 未配置任何数据源")`。`project_ids` 缺省为空列表，`product_id` 缺省为 `None`。仓库路径用 `Path` 保存，不检查是否存在（存在性由采集阶段处理）。

`match_project(cwd, home=None)`：遍历 `<home>/projects/*/report.yaml`，收集每个项目的 `git.repos`。若恰好一个项目的某个仓库是 `cwd` 的父路径，返回该项目 ID；零个或多个命中都返回 `None`，由调用方询问用户。`home` 缺省取 `data_home()`。

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_report_config.py tests/test_config.py tests/test_adapter.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add runtime/config.py runtime/adapter.py runtime/report_config.py tests/test_report_config.py tests/test_config.py
git commit -m "feat: 报告配置加载与变量替换复用"
```

---

### Task 3: git 采集

**Files:**
- Create: `runtime/gitlog.py`
- Test: `tests/test_gitlog.py`

**Interfaces:**
- Produces:
  - `Commit(hash: str, date: str, subject: str, files: int)`
  - `RepoCommits(repo: str, status: str, commits: list[Commit])`
  - `collect_git(repos: list[Path], authors: list[str], start: date, end: date) -> list[RepoCommits]`

- [ ] **Step 1: Write the failing test**

```python
import os
import subprocess
from datetime import date
from pathlib import Path

from runtime.gitlog import collect_git


def _commit(repo: Path, name: str, email: str, when: str, message: str, filename: str):
    (repo / filename).write_text(message, encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", filename], check=True)
    env = {
        "GIT_AUTHOR_NAME": name, "GIT_AUTHOR_EMAIL": email,
        "GIT_COMMITTER_NAME": name, "GIT_COMMITTER_EMAIL": email,
        "GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when,
    }
    subprocess.run(["git", "-C", str(repo), "commit", "-m", message], check=True,
                   env={**os.environ, **env})


def _repo(tmp_path, name="demo"):
    repo = tmp_path / name
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    return repo


def test_filters_by_author_and_date(tmp_path):
    repo = _repo(tmp_path)
    _commit(repo, "me", "me@x.com", "2026-10-21T10:00:00", "feat: 一", "a.txt")
    _commit(repo, "me", "me@x.com", "2026-09-01T10:00:00", "feat: 旧", "b.txt")
    _commit(repo, "other", "o@x.com", "2026-10-22T10:00:00", "feat: 别人", "c.txt")

    out = collect_git([repo], ["me@x.com"], date(2026, 10, 19), date(2026, 10, 25))
    assert len(out) == 1 and out[0].status == "ok"
    assert [c.subject for c in out[0].commits] == ["feat: 一"]
    assert out[0].commits[0].files == 1


def test_missing_repo_is_recorded_not_raised(tmp_path):
    out = collect_git([tmp_path / "nope"], ["me@x.com"], date(2026, 10, 19), date(2026, 10, 25))
    assert out[0].status.startswith("missing")
    assert out[0].commits == []


def test_empty_range_returns_no_commits(tmp_path):
    repo = _repo(tmp_path)
    _commit(repo, "me", "me@x.com", "2026-10-21T10:00:00", "feat: 一", "a.txt")
    out = collect_git([repo], ["me@x.com"], date(2026, 11, 1), date(2026, 11, 7))
    assert out[0].commits == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_gitlog.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'runtime.gitlog'`

- [ ] **Step 3: Implement**

对每个仓库先判断目录存在且 `.git` 可用（`git -C <repo> rev-parse --git-dir`），否则 `status` 写 `missing: <路径>`，继续下一个。

采集命令：

```
git -C <repo> log --no-merges --date=short
  --pretty=format:%H%x1f%ad%x1f%s --name-only
  --since=<start> 00:00:00 --until=<end> 23:59:59
  [--author=<email> ...]
```

按 `\x1f` 拆出 `hash/date/subject`，其后的非空行数即 `files`。每个 author 追加一个 `--author`，git 之间是「或」关系。命令失败时 `status` 写 `error: <末尾一行 stderr>`。

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_gitlog.py -q`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add runtime/gitlog.py tests/test_gitlog.py
git commit -m "feat: git 提交采集"
```

---

### Task 4: 禅道客户端与采集

**Files:**
- Create: `runtime/zentao.py`
- Test: `tests/test_zentao.py`

**Interfaces:**
- Consumes: `ZentaoConfig`（Task 2）
- Produces:
  - `ZentaoError(Exception)`
  - `ZentaoClient(base_url: str, account: str = "", password: str = "", token: str = "", cache_path: Path | None = None)`
  - `ZentaoClient.login() -> str`
  - `ZentaoClient.get(path: str, params: dict | None = None) -> dict`
  - `collect_zentao(cfg: ZentaoConfig, start: date, end: date) -> tuple[list[dict], list[dict], list[str]]`（tasks, bugs, warnings）

- [ ] **Step 1: Write the failing test**

```python
import json
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading

import pytest

from runtime.report_config import ZentaoConfig
from runtime.zentao import ZentaoClient, ZentaoError, collect_zentao

TASKS_P1 = {"tasks": [{"id": 1, "name": "任务一", "status": "done", "finishedDate": "2026-10-21"},
                      {"id": 2, "name": "任务二", "status": "done", "finishedDate": "2026-09-01"}],
            "total": "2"}
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

    def log_message(self, *a):
        pass


@pytest.fixture
def server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


def test_client_logs_in_and_sends_token(server, tmp_path):
    c = ZentaoClient(server, "me", "pw", cache_path=tmp_path / "t.json")
    assert c.login() == "tok-1"
    assert c.get("/projects/73/executions")["executions"][0]["id"] == 101


def test_failed_login_raises(tmp_path):
    c = ZentaoClient("http://127.0.0.1:1", "me", "pw", cache_path=tmp_path / "t.json")
    with pytest.raises(ZentaoError, match="登录"):
        c.login()


def test_collects_completed_items_in_range(server):
    cfg = ZentaoConfig(api="v2", base_url=server, account="me", password="pw",
                       product_id=31, project_ids=[73])
    tasks, bugs, warnings = collect_zentao(cfg, date(2026, 10, 19), date(2026, 10, 25))
    assert [t["id"] for t in tasks] == [1]
    assert [b["id"] for b in bugs] == [9]
    assert warnings == []


def test_unreachable_zentao_returns_warning(monkeypatch):
    cfg = ZentaoConfig(api="v2", base_url="http://127.0.0.1:1", account="me", password="pw",
                       product_id=31, project_ids=[73])
    tasks, bugs, warnings = collect_zentao(cfg, date(2026, 10, 19), date(2026, 10, 25))
    assert tasks == [] and bugs == []
    assert warnings and "禅道" in warnings[0]


def test_pagination_mismatch_adds_warning(server, monkeypatch):
    import runtime.zentao as zt

    real = zt._items_from

    def truncated(payload, key):
        items = real(payload, key)
        return items[:1]

    monkeypatch.setattr(zt, "_items_from", truncated)
    cfg = ZentaoConfig(api="v2", base_url=server, account="me", password="pw",
                       product_id=31, project_ids=[73])
    _tasks, _bugs, warnings = collect_zentao(cfg, date(2026, 10, 19), date(2026, 10, 25))
    assert any("total" in w or "未拉全" in w for w in warnings)


def test_item_without_date_is_warned_not_dropped(server, monkeypatch):
    import runtime.zentao as zt

    monkeypatch.setattr(zt, "_items_from", lambda payload, key: (
        [{"id": 3, "name": "无日期任务"}] if key == "tasks" else []
    ))
    cfg = ZentaoConfig(api="v2", base_url=server, account="me", password="pw",
                       product_id=31, project_ids=[73])
    _tasks, _bugs, warnings = collect_zentao(cfg, date(2026, 10, 19), date(2026, 10, 25))
    assert any("未解析" in w for w in warnings)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_zentao.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'runtime.zentao'`

- [ ] **Step 3: Implement**

`ZentaoClient.login()` 走 `POST {base_url}/api.php/v2/users/login`，body `{"account","password"}`，token 取 `data.token` 或 `token`；成功后写缓存 `{url, token, account}`（`cache_path` 默认 `~/.zentao-token.json`）。构造时若缓存文件的 `url` 与当前一致且未提供密码，直接复用 token。

`get()` 用 `requests`，Header `{"token": token}`；响应 `status` 为 `fail`/`error` 或含 `Not allowed` 时抛 `ZentaoError`，并尝试重新登录一次后重试。

模块内提供 `_items_from(payload: dict, key: str) -> list[dict]`：返回 `payload.get(key)` 或空列表；测试通过替换它来模拟服务端截断和缺字段。

`collect_zentao` 流程：

1. 枚举 `project_ids` 下的执行：`/projects/{id}/executions`，分页规则与下同
2. 每个执行拉 `/executions/{id}/tasks`，参数 `{"browseType": "assignedtome", "recPerPage": 1000, "pageID": n}`，响应取 `tasks`
3. 拉 `/products/{id}/bugs`，参数 `{"browseType": "assignedtome", "recPerPage": 1000, "pageID": n}`，响应取 `bugs`
4. 分页终止：本页无新增条目即停；`total` 或 `pager.recTotal` 与实际条数不符时追加 warning
5. 过滤：任务保留 `finishedDate` 落在区间内；Bug 保留 `resolvedDate` 落在区间内；日期字段按 `["finishedDate","finished","realFinished"]`（任务）和 `["resolvedDate","resolved","closedDate"]`（Bug）依次尝试
6. 归一化：任务 `{"id","title","status","date","execution"}`（`title` 取 `name`），Bug `{"id","title","status","date","product"}`
7. 任何一条缺少可识别日期时计入 `unparsed` 并追加 warning `未解析 N 条：缺少日期字段`，不静默丢弃
8. 网络或认证失败时返回空列表 + warning `禅道采集失败：<原因>`，不抛异常

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_zentao.py -q`
Expected: PASS（6 passed）

- [ ] **Step 5: Commit**

```bash
git add runtime/zentao.py tests/test_zentao.py
git commit -m "feat: 禅道 v2 采集"
```

---

### Task 5: 采集命令行

**Files:**
- Create: `scripts/collect.py`
- Test: `tests/test_collect_cli.py`

**Interfaces:**
- Consumes: Task 1–4 的全部接口
- Produces: `main(argv: list[str] | None = None, git_fn=None, zentao_fn=None) -> int`
- 输出 JSON 字段与 spec §4.5 一致

- [ ] **Step 1: Write the failing test**

```python
import json

import pytest

from scripts.collect import main


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_TOOLS_HOME", str(tmp_path))
    proj = tmp_path / "projects" / "demo"
    proj.mkdir(parents=True)
    (proj / ".env").write_text("ZENTAO_URL=http://z\n", encoding="utf-8")
    (proj / "report.yaml").write_text(
        """git:
  repos: [C:/project/demo]
  authors: [me@x.com]
zentao:
  api: v2
  base_url: ${ZENTAO_URL}
  account: me
""",
        encoding="utf-8",
    )
    return tmp_path


def test_writes_json_with_sources(project, tmp_path):
    out = tmp_path / "out.json"
    rc = main(
        ["--project", "demo", "--type", "weekly", "--anchor", "2026-10-26", "--out", str(out)],
        git_fn=lambda repos, authors, start, end: [],
        zentao_fn=lambda cfg, start, end: ([], [], []),
    )
    assert rc == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["period"] == {"type": "weekly", "start": "2026-10-19", "end": "2026-10-25"}
    assert data["sources"] == {"git": "ok", "zentao": "ok"}
    assert data["project"] == "demo"


def test_partial_failure_is_recorded(project, tmp_path):
    out = tmp_path / "out.json"
    main(
        ["--project", "demo", "--type", "daily", "--anchor", "2026-10-26", "--out", str(out)],
        git_fn=lambda *a: [],
        zentao_fn=lambda *a: ([], [], ["禅道采集失败：401"]),
    )
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["sources"]["zentao"].startswith("failed")
    assert "401" in data["sources"]["zentao"]


def test_invalid_range_exits_nonzero(project, tmp_path):
    with pytest.raises(SystemExit):
        main(["--project", "demo", "--type", "review",
              "--start", "2026-09-30", "--end", "2026-07-01", "--out", str(tmp_path / "x.json")])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_collect_cli.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.collect'`

- [ ] **Step 3: Implement**

`scripts/collect.py` 先做 `sys.path` 引导（与 `scripts/run.py` 相同）和 `sys.stdout.reconfigure(encoding="utf-8")`。

参数：`--project`（必填）、`--type`（`daily|weekly|monthly|review`）、`--anchor`（默认今天）、`--start/--end`（仅 review）、`--out`（默认 `<DATA_TOOLS_HOME>/reports/<项目ID>/.collect/<label>.json`）。

组装 `sources`：git 全为 `ok` 才是 `ok`，否则 `partial`；禅道有 warning 时写 `failed: <首个 warning>`。`git` 段把 `RepoCommits` 序列化为 spec 中的结构。`review` 的区间非法时 `parser.error()`。

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_collect_cli.py -q`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add scripts/collect.py tests/test_collect_cli.py
git commit -m "feat: 报告采集命令行"
```

---

### Task 6: Markdown 渲染 Word / PPT

**Files:**
- Create: `runtime/render.py`
- Create: `scripts/render.py`
- Modify: `requirements.txt`
- Test: `tests/test_render.py`

**Interfaces:**
- Produces:
  - `parse_markdown(text: str) -> tuple[str, list[tuple[str, list[str]]]]`（标题、章节列表）
  - `render_docx(md_text: str, path: Path, title: str) -> None`
  - `render_pptx(md_text: str, path: Path, title: str, subtitle: str) -> None`
  - `scripts/render.py: main(argv=None) -> int`

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path

from docx import Document
from pptx import Presentation

from runtime.render import parse_markdown, render_docx, render_pptx

MD = """# 周报

## 本周完成
- 完成提货单状态流转
- 修复登录超时

## 下周计划
- 接入用户管理
"""


def test_parse_markdown_splits_sections():
    title, sections = parse_markdown(MD)
    assert title == "周报"
    assert [s[0] for s in sections] == ["本周完成", "下周计划"]
    assert sections[0][1] == ["完成提货单状态流转", "修复登录超时"]


def test_render_docx_writes_headings(tmp_path):
    out = tmp_path / "r.docx"
    render_docx(MD, out, "周报")
    assert out.exists() and out.stat().st_size > 0
    doc = Document(out)
    texts = [p.text for p in doc.paragraphs]
    assert "本周完成" in texts and "接入用户管理" in texts


def test_render_pptx_creates_slide_per_section(tmp_path):
    out = tmp_path / "r.pptx"
    render_pptx(MD, out, "周报", "hexincloud · 2026-W44")
    prs = Presentation(out)
    assert len(prs.slides) == 3
    first = "\n".join(shape.text for shape in prs.slides[1].shapes if shape.has_text_frame)
    assert "本周完成" in first


def test_render_cli_reports_missing_dependency(tmp_path, monkeypatch, capsys):
    import builtins

    from scripts import render as cli

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name in {"docx", "pptx"}:
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    rc = cli.main(["--input", str(tmp_path / "x.md"), "--format", "docx", "--out-dir", str(tmp_path)])
    assert rc == 1
    assert "缺少依赖" in capsys.readouterr().out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_render.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'runtime.render'`（若缺库则先执行 Step 3 的依赖安装）

- [ ] **Step 3: Add dependencies and implement**

`requirements.txt` 追加：

```
python-docx==1.2.0
python-pptx==1.0.2
```

安装：`.venv/Scripts/python.exe -m pip install python-docx==1.2.0 python-pptx==1.0.2`

`parse_markdown`：首个 `# ` 为标题；`## ` 开新章节；`- ` 开头的行去掉前缀收进该章节；其余非空行也作为正文行。

`render_docx`：默认模板，标题用 Heading 0，章节用 Heading 1，条目用 List Bullet。

`render_pptx`：16:9；第 1 页为标题页（标题 + 副标题）；此后每个章节一页，标题 + 至多 6 条要点，超出则拆「（续）」页。页面留白统一，不套主题色。

`scripts/render.py`：`--input`、`--format`（逗号分隔 `docx,pptx`）、`--out-dir`、`--title`、`--subtitle`；缺库时捕获 `ImportError`，打印 `缺少依赖：python-docx / python-pptx，请先 pip install -r requirements.txt` 并返回 1。

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_render.py -q`
Expected: PASS（4 passed）
git commit -m "feat: Markdown 渲染 Word 与 PPT"
```

---

### Task 7: 技能与安装接入

**Files:**
- Create: `skills/report-writer/SKILL.md`
- Modify: `scripts/install.py`（`SKILLS` 增加 `report-writer`）
- Modify: `tests/test_skills.py`（参数化加入新技能）
- Test: `tests/test_install.py` 现有断言覆盖

**Interfaces:**
- Consumes: Task 1–6 的 CLI
- Produces: 可被 Claude / Cursor / Codex 加载的第四个技能

- [ ] **Step 1: Write the failing test**

在 `tests/test_skills.py` 的 `@pytest.mark.parametrize` 列表中加入 `"report-writer"`。

```python
@pytest.mark.parametrize("name", ["data-gen-core", "db-access", "adapter-bootstrap", "report-writer"])
def test_skill_has_frontmatter_and_sections(name):
    ...
```

新增：

```python
def test_report_skill_asks_audience_and_scope():
    text = (SKILLS / "report-writer" / "SKILL.md").read_text(encoding="utf-8")
    assert "给谁" in text
    assert "不猜" in text
    assert "collect.py" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_skills.py -q`
Expected: FAIL（文件不存在）

- [ ] **Step 3: Write `skills/report-writer/SKILL.md`**

frontmatter：`name: report-writer`，`description` 写明触发词「日报 / 周报 / 月报 / 述职 / 汇报材料」，并声明「生成前必须确认受众；项目无法确定时必须询问」。

正文沿用现有技能的四个小节结构（适用场景 / 前置检查 / 执行 / 失败处理），另加「路径」小节，写清 `<TOOLS_DIR>` 的三级解析（`DATA_TOOLS_DIR` → `~/.data-tools/config.yaml` → 询问）。

执行步骤必须写明：

1. 确定项目：用户指定 → 用 `match_project(cwd)` 匹配 → 询问（不查则问，不猜）
2. 确定时间区间与报告类型
3. 询问受众（默认沿用 `reports/<项目ID>/.audience`），确定语气；确认后写回该文件
4. 运行 `scripts/collect.py` 得到 JSON
5. 摆事实（提交数、完成任务数、Bug 数），询问补充
6. 读取模板 `~/.data-tools/templates/<项目ID>/<类型>.md`；没有则用内置结构
7. 按组织规则写 Markdown：写结果不写动作、合并去重、字数区间
8. 存到 `~/.data-tools/reports/<项目ID>/<label>.md`
9. 需要 Word/PPT 时运行 `scripts/render.py`
10. 数据缺失时在开头显式说明

失败处理表覆盖：配置缺失、项目不明、禅道失败、无数据、渲染缺依赖。

同时在 `scripts/install.py` 的 `SKILLS` 列表追加 `"report-writer"`。

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_skills.py tests/test_install.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add skills/report-writer/SKILL.md scripts/install.py tests/test_skills.py
git commit -m "feat: 报告技能与安装接入"
```

---

### Task 8: 文档与端到端自检

**Files:**
- Modify: `README.md`
- Modify: `docs/usage.md`
- Modify: `requirements.txt`（Task 6 已加，确认存在）
- Test: 无新增单测；跑全量

**Interfaces:**
- Consumes: Task 1–7

- [ ] **Step 1: 更新 README 的能力表**

在 `## Preview` 的表格加一行：

```
| 写这周的周报，顺便出 Word | 采集提交与禅道任务，组织成稿并渲染 |
```

在 `## Features` 加一条：`- 报告生成：日报/周报/月报/述职，Markdown 为源，可渲染 Word/PPT`。

- [ ] **Step 2: 更新 `docs/usage.md`**

新增一章「十、写报告」，追加在「九、常见问题」之后，并在开头的目录中登记。内容覆盖：

- 触发说法与四种类型
- 生成前会问受众，语气随受众变化
- 配置位置 `report.yaml` 与必填项
- 报告存放位置与命名
- 模板位置与写法
- 数据缺失时的表现

- [ ] **Step 3: 跑全量验证**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: 全部通过

Run: `.venv/Scripts/python.exe scripts/check_secrets.py`
Expected: `未发现敏感信息`

Run: `.venv/Scripts/python.exe scripts/collect.py --help`
Expected: 打印用法，退出码 0

- [ ] **Step 4: Commit**

```bash
git add README.md docs/usage.md
git commit -m "docs: 报告生成能力说明"
```

---

## 端到端验收（人工）

1. 在 `C:/project/hexincloud` 下说「写今天的日报」，确认项目被正确识别、受众提问出现
2. 用同一区间重复生成，确认条目数一致
3. 断开禅道（错误地址）后生成，确认报告开头写明缺失且仍能产出
4. 同时要 md 和 pptx，确认两者章节一致
