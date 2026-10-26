# AI 数据工具包 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付一套可安装的能力包，让用户用白话触发连库操作与业务数据批量生成，规则本地累积。

**Architecture:** markdown 规则（skills/）与 Python 引擎（runtime/）分离；引擎按本地 `adapter.yaml` 声明驱动执行；`install.py` 把同一份规则渲染成 Claude / Cursor / Codex 三种入口。

**Tech Stack:** Python 3.13、pytest、PyYAML、requests、psycopg[binary]

**Spec:** `docs/superpowers/specs/2026-10-23-ai-data-toolkit-design.md`

## Global Constraints

- Python 3.13；Windows 优先，路径一律用 `pathlib.Path`
- 运行时依赖只允许：`PyYAML`、`requests`、`psycopg[binary]`
- 仓库内不得出现真实密码、token、内网 IP、人员姓名
- 生成文件带版本头，禁止手改；改源文件后重跑 install
- 所有可变值在 `adapter.yaml` 中用 `${VAR}`，值只来自同目录 `.env`
- 测试不得访问真实数据库或网络，一律用桩对象或临时目录

## Review Focus

1. `.env` 值中含 `=`、`#`、引号 → 必须原样保留，不得截断
2. `adapter.yaml` 引用了未定义的 `${VAR}` → 加载期明确报错，不得发出请求
3. 多线程并发写台账 → 不丢行、不重复表头
4. 重复执行 install → AGENTS.md 托管块不得重复追加
5. HTTP 4xx 不重试；网络错误/超时最多重试 2 次

---

## 文件结构

| 文件 | 职责 |
|---|---|
| `runtime/config.py` | 数据根目录、项目目录、`.env` 解析 |
| `runtime/adapter.py` | 加载并校验 `adapter.yaml`，替换 `${VAR}` |
| `runtime/ledger.py` | CSV 台账：追加、读取已完成 |
| `runtime/http_client.py` | 请求、重试、超时、拼接 base_url |
| `runtime/db.py` | 建立数据库连接、执行 SQL |
| `runtime/verify.py` | 按 adapter 的 verify 段做 SQL 校验 |
| `runtime/runner.py` | 单条执行（call/poll/impl）与批量并发续跑 |
| `scripts/check_secrets.py` | 扫描敏感信息 |
| `scripts/install.py` | 渲染三种工具入口 |
| `skills/**` | 规则、契约、模板 |

---

### Task 1: 骨架、配置与适配层加载

**Files:**
- Create: `requirements.txt`、`requirements-dev.txt`、`runtime/__init__.py`、`runtime/config.py`、`runtime/adapter.py`
- Test: `tests/test_config.py`、`tests/test_adapter.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `config.data_home() -> Path`
  - `config.project_dir(project_id: str) -> Path`
  - `config.load_env(path: Path) -> dict[str, str]`
  - `config.resolve_project(explicit: str | None = None) -> str`
  - `config.ConfigError(Exception)`
  - `adapter.AdapterError(Exception)`
  - `adapter.load_adapter(project_id: str) -> Adapter`
  - `Adapter` 字段：`version: int`、`project: str`、`envs: dict`、`auth: dict`、`entities: dict[str, Entity]`、`pitfalls: list[dict]`
  - `Entity` 字段：`id`、`description`、`stop_at`、`id_rule`、`steps: list[Step]`、`verify: dict | None`
  - `Step` 字段：`id`、`call`、`poll`、`until`、`timeout`、`before`、`impl`、`body`

- [ ] **Step 1: 写失败测试**

`tests/test_config.py`：

```python
def test_data_home_prefers_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_TOOLS_HOME", str(tmp_path))
    assert config.data_home() == tmp_path

def test_load_env_keeps_equals_and_hash(tmp_path):
    p = tmp_path / ".env"
    p.write_text("PW=a=b#c\n", encoding="utf-8")
    assert config.load_env(p)["PW"] == "a=b#c"

def test_resolve_project_explicit_beats_config(monkeypatch, tmp_path):
    (tmp_path / "config.yaml").write_text("default_project: from_config\n", encoding="utf-8")
    monkeypatch.setenv("DATA_TOOLS_HOME", str(tmp_path))
    assert config.resolve_project("explicit") == "explicit"

def test_resolve_project_falls_back_to_config(monkeypatch, tmp_path):
    (tmp_path / "config.yaml").write_text("default_project: from_config\n", encoding="utf-8")
    monkeypatch.setenv("DATA_TOOLS_HOME", str(tmp_path))
    assert config.resolve_project(None) == "from_config"

def test_resolve_project_without_any_source_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_TOOLS_HOME", str(tmp_path))
    with pytest.raises(config.ConfigError):
        config.resolve_project(None)
```

`tests/test_adapter.py`：

```python
def _write_adapter(tmp_path, body: str):
    proj = tmp_path / "projects" / "demo"
    proj.mkdir(parents=True)
    (proj / "adapter.yaml").write_text(body, encoding="utf-8")
    (proj / ".env").write_text("BASE=http://example\n", encoding="utf-8")
    return proj

def test_missing_var_raises(monkeypatch, tmp_path):
    _write_adapter(tmp_path, MINIMAL.replace("${BASE}", "${NOPE}"))
    monkeypatch.setenv("DATA_TOOLS_HOME", str(tmp_path))
    with pytest.raises(adapter.AdapterError, match="NOPE"):
        adapter.load_adapter("demo")

def test_step_with_two_modes_raises(monkeypatch, tmp_path):
    _write_adapter(tmp_path, MINIMAL.replace("        call: POST /x", "        call: POST /x\n        poll: GET /y"))
    monkeypatch.setenv("DATA_TOOLS_HOME", str(tmp_path))
    with pytest.raises(adapter.AdapterError, match="exactly one"):
        adapter.load_adapter("demo")

def test_entity_without_steps_raises(monkeypatch, tmp_path):
    _write_adapter(tmp_path, MINIMAL.replace("      - id: create\n        call: POST /x\n", ""))
    monkeypatch.setenv("DATA_TOOLS_HOME", str(tmp_path))
    with pytest.raises(adapter.AdapterError, match="steps"):
        adapter.load_adapter("demo")

def test_loads_and_substitutes(monkeypatch, tmp_path):
    _write_adapter(tmp_path, MINIMAL)
    monkeypatch.setenv("DATA_TOOLS_HOME", str(tmp_path))
    a = adapter.load_adapter("demo")
    assert a.project == "demo"
    assert a.envs["dev"]["base_url"] == "http://example"
```

`MINIMAL` 常量放在测试文件顶部：

```python
MINIMAL = """version: 1
project: demo
envs:
  dev:
    base_url: ${BASE}
    db_prefix: DEV
auth:
  type: none
entities:
  order:
    description: 测试单
    stop_at: DONE
    id_rule: "T{idx}"
    steps:
      - id: create
        call: POST /x
pitfalls: []
"""
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_config.py tests/test_adapter.py -q`
Expected: FAIL，`ModuleNotFoundError: runtime`

- [ ] **Step 3: 实现**

`requirements.txt`：`PyYAML==6.0.2`、`requests==2.34.2`、`psycopg[binary]==3.3.6`
`requirements-dev.txt`：`-r requirements.txt`、`pytest==8.4.2`

`config.py`：`data_home()` 读 `DATA_TOOLS_HOME`，否则 `Path.home()/".data-tools"`；`project_dir()` 返回 `data_home()/projects/<id>`；`load_env()` 按 `split("=", 1)` 解析、忽略空行与 `#` 开头、不 strip 值内部字符；`resolve_project()` 顺序为显式参数 → `config.yaml:default_project` → 抛 `ConfigError`。

`adapter.py`：`load_adapter()` 读 YAML，校验 `version == 1`、`entities` 非空、每个 entity 有 `steps`、每个 step 的 `call`/`poll`/`impl` 恰好一个；用同目录 `.env` 替换所有 `${VAR}`，未定义则 `AdapterError("未定义变量 NOPE")`。返回 dataclass。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_config.py tests/test_adapter.py -q`
Expected: PASS（9 passed）

- [ ] **Step 5: 提交**

```bash
git add requirements.txt requirements-dev.txt runtime/ tests/
git commit -m "feat: 配置与适配层加载"
```

---

### Task 2: 台账

**Files:**
- Create: `runtime/ledger.py`
- Test: `tests/test_ledger.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `ledger.FIELDS: list[str]`
  - `Ledger(path: Path)`
  - `Ledger.read_done(run_id: str) -> set[int]`
  - `Ledger.append(row: dict) -> None`（线程安全）

- [ ] **Step 1: 写失败测试**

```python
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
    threads = [threading.Thread(target=lg.append, args=({"run_id": "r", "idx": i, "status": "done"},)) for i in range(50)]
    [t.start() for t in threads]; [t.join() for t in threads]
    lines = (tmp_path / "l.csv").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 51
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_ledger.py -q`
Expected: FAIL，`ModuleNotFoundError`

- [ ] **Step 3: 实现**

`FIELDS` 与现 `hexin-data-gen/batch_run.py` 保持一致。`append()` 用模块级 `threading.Lock` 保护「判断文件是否存在 → 写表头 → 写行」的整段。

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_ledger.py -q`
Expected: PASS（3 passed）

- [ ] **Step 5: 提交**

```bash
git add runtime/ledger.py tests/test_ledger.py
git commit -m "feat: 批量台账与断点续跑基础"
```

---

### Task 3: HTTP 客户端

**Files:**
- Create: `runtime/http_client.py`
- Test: `tests/test_http_client.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `HttpClient(base_url: str, auth=None, timeout: float = 15.0, retries: int = 2)`
  - `HttpClient.request(method: str, path: str, json=None, params=None) -> dict`
  - `HttpClientError(Exception)`

- [ ] **Step 1: 写失败测试**

用 `monkeypatch` 替换 `requests.Session.request`。

```python
def test_joins_base_url_and_path(monkeypatch):
    calls = []
    monkeypatch.setattr(requests.Session, "request", lambda self, m, url, **kw: calls.append((m, url)) or _Resp({"ok": 1}))
    c = HttpClient("http://h/api")
    c.request("POST", "/x")
    assert calls == [("POST", "http://h/api/x")]

def test_retries_twice_on_connection_error(monkeypatch):
    n = {"i": 0}
    def boom(self, m, url, **kw):
        n["i"] += 1
        raise requests.ConnectionError("reset")
    monkeypatch.setattr(requests.Session, "request", boom)
    with pytest.raises(HttpClientError):
        HttpClient("http://h", retries=2).request("GET", "/x")
    assert n["i"] == 3

def test_does_not_retry_on_4xx(monkeypatch):
    n = {"i": 0}
    def boom(self, m, url, **kw):
        n["i"] += 1
        return _Resp({}, status=404)
    monkeypatch.setattr(requests.Session, "request", boom)
    with pytest.raises(HttpClientError, match="404"):
        HttpClient("http://h", retries=2).request("GET", "/x")
    assert n["i"] == 1
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_http_client.py -q`

- [ ] **Step 3: 实现**

`request()` 拼接 `base_url + path`，网络错误/超时重试 `retries` 次后抛 `HttpClientError`；`status >= 400` 不重试直接抛；成功返回 `resp.json()`。`auth` 若提供，调用 `auth.apply(headers: dict) -> dict`。

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_http_client.py -q`
Expected: PASS（3 passed）

- [ ] **Step 5: 提交**

```bash
git add runtime/http_client.py tests/test_http_client.py
git commit -m "feat: HTTP 客户端重试与超时"
```

---

### Task 4: 校验

**Files:**
- Create: `runtime/verify.py`
- Test: `tests/test_verify.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `verify.run_verify(conn, spec: dict, params: dict) -> tuple[bool, object]`

- [ ] **Step 1: 写失败测试**

用桩连接（对象实现 `cursor()`，返回上下文管理器与 `fetchone`）。

```python
def test_returns_true_when_value_matches():
    ok, got = run_verify(_FakeConn("UPLOADED"), {"sql": "select status from t where no = %(no)s", "expect": "UPLOADED"}, {"no": "X"})
    assert ok is True and got == "UPLOADED"

def test_returns_false_on_mismatch():
    ok, got = run_verify(_FakeConn("NEW"), {"sql": "select status from t", "expect": "UPLOADED"}, {})
    assert ok is False and got == "NEW"
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_verify.py -q`

- [ ] **Step 3: 实现**

执行 SQL，取第一行第一列，与 `spec["expect"]` 比较；`spec` 为空返回 `(True, None)`。

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_verify.py -q`

- [ ] **Step 5: 提交**

```bash
git add runtime/verify.py tests/test_verify.py
git commit -m "feat: 数据结果校验"
```

---

### Task 5: 数据库访问

**Files:**
- Create: `runtime/db.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: `config.load_env`
- Produces:
  - `db.DbError(Exception)`
  - `db.connect(env: dict[str, str], prefix: str, database: str) -> Connection`
  - `db.execute(conn, sql: str, params: dict | None = None) -> tuple[list[tuple], int]`

- [ ] **Step 1: 写失败测试**

```python
def test_missing_prefix_key_raises():
    with pytest.raises(DbError, match="DEV_HOST"):
        connect({"DEV_PORT": "5432"}, "DEV", "hexin_wms")

def test_connect_uses_prefixed_keys(monkeypatch):
    seen = {}
    monkeypatch.setattr(psycopg, "connect", lambda **kw: seen.update(kw) or object())
    env = {"DEV_HOST": "h", "DEV_PORT": "5432", "DEV_USER": "u", "DEV_PASSWORD": "p"}
    connect(env, "DEV", "db1")
    assert seen == {"host": "h", "port": 5432, "user": "u", "password": "p", "dbname": "db1"}

def test_execute_returns_rows_and_rowcount():
    conn = _FakeConn(rows=[("A",)], rowcount=3)
    rows, count = execute(conn, "update t set s=%s", ("A",))
    assert rows == [("A",)] and count == 3
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_db.py -q`
Expected: FAIL，`ModuleNotFoundError`

- [ ] **Step 3: 实现**

`connect()` 从 `env` 取 `<prefix>_HOST/_PORT/_USER/_PASSWORD`，任一项缺失抛 `DbError("<KEY> 未配置")`；端口转 `int`；带 `connect_timeout=10`。`execute()` 用 `conn.cursor()`，有结果集时 `fetchall()`，返回 `(rows, cursor.rowcount)`；不自动提交，由调用方决定。

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_db.py -q`
Expected: PASS（3 passed）

- [ ] **Step 5: 提交**

```bash
git add runtime/db.py tests/test_db.py
git commit -m "feat: 数据库连接与 SQL 执行"
```

---

### Task 6: 单条执行

**Files:**
- Create: `runtime/runner.py`
- Test: `tests/test_runner.py`

**Interfaces:**
- Consumes: `adapter.Entity`、`adapter.Step`、`HttpClient`
- Produces:
  - `runner.RunError(Exception)`
  - `runner.run_entity(entity: Entity, client, ctx: dict, impl_root: Path | None = None) -> dict`
  - `runner.run_entity` 的 `ctx` 键：`external_no`、`values`（步骤产出）、`stage`

- [ ] **Step 1: 写失败测试**

```python
def test_call_step_substitutes_vars():
    client = _FakeClient({"POST /x": {"id": 7}})
    entity = _entity([Step(id="create", call="POST /x", body={"no": "${ctx.external_no}"})])
    ctx = {"external_no": "T1", "values": {}, "stage": "init"}
    out = run_entity(entity, client, ctx)
    assert out["values"]["create"]["id"] == 7
    assert client.last_json == {"no": "T1"}

def test_poll_step_until_true():
    client = _FakeClient_Seq([{"status": None}, {"status": "OK"}])
    entity = _entity([Step(id="wait", poll="GET /x", until="resp['status'] == 'OK'", timeout=5)])
    out = run_entity(entity, client, {"external_no": "T", "values": {}, "stage": "init"})
    assert out["values"]["wait"]["status"] == "OK"

def test_poll_timeout_raises():
    client = _FakeClient_Seq([{"status": None}] * 10)
    entity = _entity([Step(id="wait", poll="GET /x", until="resp['status'] == 'OK'", timeout=0)])
    with pytest.raises(RunError, match="timeout"):
        run_entity(entity, client, {"external_no": "T", "values": {}, "stage": "init"})

def test_impl_step_loads_function(tmp_path, monkeypatch):
    (tmp_path / "hook.py").write_text("def go(ctx, resp):\n    return {'ok': True}\n", encoding="utf-8")
    entity = _entity([Step(id="hook", impl="hook.py:go")])
    out = run_entity(entity, _FakeClient({}), {"external_no": "T", "values": {}, "stage": "init"}, impl_root=tmp_path)
    assert out["values"]["hook"] == {"ok": True}
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_runner.py -q`

- [ ] **Step 3: 实现**

- `call`：`"POST /x"` 拆方法+路径，`body` 中 `${ctx.X}` / `${prev.STEP.FIELD}` 递归替换后发出，结果存 `ctx["values"][step.id]`
- `poll`：循环请求，用 `eval(step.until, {"resp": ..., "ctx": ctx, "None": None})` 判断；超过 `timeout` 秒抛 `RunError("timeout: <step.id>")`；轮询间隔 1 秒
- `impl`：`<相对路径>:<函数名>`，用 `importlib` 从 `impl_root`（默认 `project_dir(pid)/`）加载，调用 `func(ctx, resp=None)`

`until` 语法是 Python 表达式，文档与示例统一按此写。

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_runner.py -q`
Expected: PASS（4 passed）

- [ ] **Step 5: 提交**

```bash
git add runtime/runner.py tests/test_runner.py
git commit -m "feat: 单条业务链执行"
```

---

### Task 7: 批量并发与续跑

**Files:**
- Modify: `runtime/runner.py`
- Test: `tests/test_runner_batch.py`

**Interfaces:**
- Consumes: Task 2 的 `Ledger`、Task 6 的 `run_entity`
- Produces:
  - `runner.run_batch(entity, client_factory, count: int, workers: int, run_id: str, ledger: Ledger) -> dict`
  - 返回 `{"done": int, "failed": int, "failures": list[tuple[int, str]]}`

- [ ] **Step 1: 写失败测试**

```python
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

def test_resume_same_run_id_skips_previous(tmp_path):
    lg = Ledger(tmp_path / "l.csv")
    run_batch(_entity_ok(), lambda: _RecordingClient([]), count=2, workers=1, run_id="r", ledger=lg)
    out = run_batch(_entity_ok(), lambda: _RecordingClient([]), count=2, workers=1, run_id="r", ledger=lg)
    assert out["done"] == 0
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_runner_batch.py -q`

- [ ] **Step 3: 实现**

按 `idx` 取模分片给 `workers` 个线程，每线程独立 `client_factory()`（避免共享会话）。每完成或失败写一行台账，字段沿用 `FIELDS`。批量结果不因单条失败中断。

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_runner_batch.py -q`
Expected: PASS（3 passed）

- [ ] **Step 5: 提交**

```bash
git add runtime/runner.py tests/test_runner_batch.py
git commit -m "feat: 批量并发与断点续跑"
```

---

### Task 8: 敏感信息扫描

**Files:**
- Create: `scripts/check_secrets.py`
- Test: `tests/test_check_secrets.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `check_secrets.scan(paths: list[Path]) -> list[tuple[Path, int, str]]`
  - `check_secrets.main(argv) -> int`（命中返回 1）

- [ ] **Step 1: 写失败测试**

```python
def test_flags_password_literal(tmp_path):
    f = tmp_path / "a.py"; f.write_text('password = "SuperSecret123"\n', encoding="utf-8")  # noqa: secrets
    hits = scan([f])
    assert hits and "password" in hits[0][2].lower()

def test_flags_private_ip(tmp_path):
    f = tmp_path / "a.py"; f.write_text("HOST = '192.168.1.10'\n", encoding="utf-8")  # noqa: secrets
    assert scan([f])

def test_allows_env_reference(tmp_path):
    f = tmp_path / "a.py"; f.write_text('password = os.getenv("PW")\n', encoding="utf-8")
    assert scan([f]) == []

def test_clean_tree_returns_zero(tmp_path):
    (tmp_path / "ok.py").write_text("x = 1\n", encoding="utf-8")
    assert main([str(tmp_path)]) == 0
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_check_secrets.py -q`

- [ ] **Step 3: 实现**

规则：`(password|passwd|secret|token|api_key)\s*[:=]\s*["'][^"']{6,}`、`ghp_[A-Za-z0-9]{20,}`、`github_pat_[A-Za-z0-9_]{20,}`、`BEGIN [A-Z ]*PRIVATE KEY`、私有 IP `(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)`。

跳过目录：`.git`、`.venv`、`node_modules`、`__pycache__`、`projects`。跳过文件：`*.example`、`*.md` 中的说明性片段不跳过（误报以 `# noqa: secrets` 行内标记豁免）。

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_check_secrets.py -q`
Expected: PASS（4 passed）

- [ ] **Step 5: 提交**

```bash
git add scripts/check_secrets.py tests/test_check_secrets.py
git commit -m "feat: 敏感信息扫描"
```

---

### Task 9: 三工具安装

**Files:**
- Create: `scripts/install.py`
- Test: `tests/test_install.py`

**Interfaces:**
- Consumes: `skills/` 下的源文件
- Produces:
  - `install.render(tool: str, name: str, body: str, description: str, tools_dir: Path) -> str`
  - `install.install(targets: list[str], scope: str, project_dir: Path | None, tools_dir: Path, home: Path) -> list[Path]`
  - `install.remove(targets, scope, project_dir, home) -> None`

- [ ] **Step 1: 写失败测试**

```python
def test_claude_skill_has_name_and_description(tmp_path):
    paths = install(["claude"], "global", None, TOOLS, home=tmp_path)
    text = paths[0].read_text(encoding="utf-8")
    assert "name: data-gen-core" in text and "description:" in text
    assert paths[0].name == "SKILL.md"

def test_cursor_rule_has_always_apply(tmp_path):
    paths = install(["cursor"], "project", tmp_path / "repo", TOOLS, home=tmp_path)
    text = paths[0].read_text(encoding="utf-8")
    assert "alwaysApply: false" in text and paths[0].suffix == ".mdc"

def test_codex_block_is_not_duplicated(tmp_path):
    repo = tmp_path / "repo"
    install(["codex"], "project", repo, TOOLS, home=tmp_path)
    install(["codex"], "project", repo, TOOLS, home=tmp_path)
    text = (repo / "AGENTS.md").read_text(encoding="utf-8")
    assert text.count("data-tools:begin") == 1

def test_remove_deletes_generated(tmp_path):
    repo = tmp_path / "repo"
    install(["cursor"], "project", repo, TOOLS, home=tmp_path)
    remove(["cursor"], "project", repo, home=tmp_path)
    assert not (repo / ".cursor/rules/data-gen-core.mdc").exists()
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_install.py -q`

- [ ] **Step 3: 实现**

- 读取 `skills/<name>/SKILL.md`，拆 frontmatter 与正文
- Claude：`<home>/.claude/skills/<name>/SKILL.md`，frontmatter 为 `name` + `description`
- Cursor：`<project>/.cursor/rules/<name>.mdc`，frontmatter 为 `description` + `globs: []` + `alwaysApply: false`
- Codex：在 `<project>/AGENTS.md` 维护 `<!-- data-tools:begin -->` 到 `:end` 的块，内容为三行索引
- 正文中 `{{TOOLS_DIR}}` 替换为 `tools_dir`
- 三处生成文件首行写 `<!-- generated by data-tools v1; edit source, do not edit here -->`
- `remove()` 只删生成文件和托管块

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_install.py -q`
Expected: PASS（4 passed）

- [ ] **Step 5: 提交**

```bash
git add scripts/install.py tests/test_install.py
git commit -m "feat: 三工具安装与卸载"
```

---

### Task 10: 规则、契约与模板

**Files:**
- Create: `skills/data-gen-core/SKILL.md`、`skills/db-access/SKILL.md`、`skills/adapter-bootstrap/SKILL.md`
- Create: `skills/_references/adapter-contract.md`、`runtime-contract.md`、`trigger-routing.md`、`pitfalls.md`
- Create: `skills/_TEMPLATE/adapter.example.yaml`、`pitfalls.example.md`、`env.example`
- Test: `tests/test_skills.py`

**Interfaces:**
- Consumes: Task 9 的 `install.render`
- Produces: 三份可被 install 渲染的 skill 源文件

- [ ] **Step 1: 写失败测试**

```python
@pytest.mark.parametrize("name", ["data-gen-core", "db-access", "adapter-bootstrap"])
def test_skill_has_frontmatter_and_sections(name):
    text = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---")
    for section in ["## 适用场景", "## 前置检查", "## 执行", "## 失败处理"]:
        assert section in text

def test_data_gen_requires_adapter_and_forbids_improvisation():
    text = (SKILLS / "data-gen-core" / "SKILL.md").read_text(encoding="utf-8")
    assert "adapter-bootstrap" in text
    assert "不允许现场推导" in text

def test_trigger_routing_covers_four_intents():
    text = (SKILLS / "_references" / "trigger-routing.md").read_text(encoding="utf-8")
    for word in ["造数", "连库", "接入", "沉淀"]:
        assert word in text

def test_adapter_example_parses():
    data = yaml.safe_load((SKILLS / "_TEMPLATE" / "adapter.example.yaml").read_text(encoding="utf-8"))
    assert data["version"] == 1 and "entities" in data
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_skills.py -q`

- [ ] **Step 3: 写内容**

每份 SKILL.md 必须包含：适用场景（含触发词）、前置检查、执行、失败处理。`data-gen-core` 额外写「无适配层必须转 bootstrap，不允许现场推导」。

`trigger-routing.md` 按设计稿第 7 节写路由表与 5 条消歧顺序。
`adapter-contract.md` 写字段定义 + 4 条规则 + `until` 用 Python 表达式的说明。
`runtime-contract.md` 写 runner 如何消费 adapter（call/poll/impl 语义）。
`pitfalls.md` 初始为空模板，含四段格式说明。
`adapter.example.yaml` 逐字段注释，值全部用 `${VAR}`。

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_skills.py -q`
Expected: PASS（6 passed）

- [ ] **Step 5: 提交**

```bash
git add skills/ tests/test_skills.py
git commit -m "docs: 规则、契约与模板"
```

---

### Task 11: 安装脚本包装与本机落地

**Files:**
- Create: `install.ps1`
- Modify: `README.md`
- 本机生成：`~/.claude/skills/**`、`C:\project\hexincloud\.cursor\rules\**`、`C:\project\hexincloud\AGENTS.md`

**Interfaces:**
- Consumes: `scripts/install.py`

- [ ] **Step 1: 写 install.ps1**

接受参数 `-Target claude,cursor,codex -Scope global|project -ProjectDir <路径> -Remove`，内部转调 `python scripts/install.py`，失败时 `exit 1`。

- [ ] **Step 2: 本机执行安装**

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -Target claude,cursor,codex -Scope global
powershell -ExecutionPolicy Bypass -File .\install.ps1 -Target cursor,codex -Scope project -ProjectDir C:\project\hexincloud
```

- [ ] **Step 3: 验证生成物**

- `~/.claude/skills/data-gen-core/SKILL.md` 存在且含 `name: data-gen-core`
- `C:\project\hexincloud\.cursor\rules\data-gen-core.mdc` 存在且含 `alwaysApply: false`
- `C:\project\hexincloud\AGENTS.md` 含且仅含一处 `data-tools:begin`

- [ ] **Step 4: 生成首个适配层**

按 `adapter-bootstrap` 流程，从现有 `hexin-data-gen` 抽象出 `%USERPROFILE%\.data-tools\projects\<项目ID>\adapter.yaml`，凭据由用户口述后写入同目录 `.env`。此步需要用户参与，执行前先向用户索取项目 ID、接口地址、账号。

- [ ] **Step 5: 端到端验证**

在 dev 环境造 1 张单，确认：
- 台账新增 1 行 `status=done`
- `verify` 段的 SQL 校验通过
- 重复执行同一 `run_id` 不再重复造单

- [ ] **Step 6: 提交**

```bash
git add install.ps1 README.md
git commit -m "feat: 安装脚本与本机落地"
```
