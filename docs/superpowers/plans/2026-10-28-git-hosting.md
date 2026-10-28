# 多平台 Git 管理实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让工具能用一句白话完成 GitHub / Gitee / GitLab 上的提交、推送、拉取、合并和建 MR，并把已有的分支与提交规则固化为代码校验。

**Architecture:** 规则校验是纯函数（`rules.py`），平台差异只放在三个 REST 适配器里，本地 git 操作单独封装（`repo.py`）。命令行 `scripts/git_host.py` 串起三者：先校验规则，再执行本地操作，最后调平台 API。令牌只从项目 `.env` 读取，经 HTTP Header 发送。

**Tech Stack:** Python 3.11+、requests、PyYAML、pytest；本地 git 通过 `subprocess` 调用。

**Spec:** `docs/superpowers/specs/2026-10-28-git-hosting-design.md`

## Global Constraints

- 解释器：仓库内 `.venv/Scripts/python.exe`
- 数据根：`~/.data-tools`，项目目录 `~/.data-tools/projects/<项目ID>/`
- 令牌只存项目 `.env`，键名由 `git_hosts.yaml` 的 `host.token_key` 指定
- 令牌不出现在命令行参数、日志、台账、报告、git 配置中
- 分支名格式：`feature/<目标>/<user_tag>/<任务号>-<描述>`，目标 ∈ {dev, test, prod}
- 提交信息格式：`feat-<任务号>: <中文描述>` 或 `fix-<任务号>: <中文描述>`，正文必须存在
- 禁止提交路径：`pom.xml`、`vite.config.ts`（本地环境配置）
- test、prod 的合并只能通过 MR，不能本地直合
- 测试不得连接真实平台；令牌测试只使用虚构值

## Review Focus

1. 净增量计算：合并前列出的提交数与文件数必须与 `git log` 实际结果一致，源分支自身以外的提交一律计入「将带入」
2. 令牌泄露：任何异常信息、日志行、退出信息中都不得包含令牌原文
3. 写请求超时：建 MR 或推送超时后不自动重试，避免重复创建
4. 分支名含中文或特殊字符：描述部分允许中文，但不允许空格和路径分隔符
5. 平台返回已存在的 MR：报告已有编号，不重复创建，退出码为 0

---

### Task 1: 规则校验（纯函数）

**Files:**
- Create: `runtime/git_host/__init__.py`
- Create: `runtime/git_host/rules.py`
- Test: `tests/test_git_rules.py`

**Interfaces:**
- Produces:
  - `class RuleViolation(Exception)`，属性 `rule: str`、`message: str`
  - `parse_branch(name: str) -> BranchInfo | None`；`BranchInfo(target: str, user_tag: str, task: str, desc: str)`
  - `check_branch_name(name: str, user_tag: str) -> None`（不符合抛 `RuleViolation`，`rule="branch-naming"`）
  - `check_commit_message(message: str) -> None`（格式不符或无正文抛 `RuleViolation`，`rule="commit-message"`）
  - `check_commit_paths(paths: list[str], forbidden: list[str]) -> None`（命中抛 `RuleViolation`，`rule="forbidden-path"`，消息列出命中路径）
  - `check_merge(source: str, target: str, source_base: str | None, bring_in: list[str]) -> list[str]`（违规抛 `RuleViolation`；返回需要用户确认的 `bring_in`，空表示无需确认）

`check_merge` 规则，按顺序判断，首个命中即抛：

1. `target` ∈ {test, prod} → `RuleViolation(rule="direct-merge", message="test/prod 只能通过 MR 合并")`
2. `source_base == "prod"` 且 `target` ∈ {dev, test}（目标分支本身，即 `target` 字符串为 dev 或 test）→ `RuleViolation(rule="prod-derived", ...)`；目标为 `feature/test/...` 这类衍生分支时不拦
3. `target == "dev"` 且 `bring_in` 非空 → 不抛异常。`check_merge` 返回该列表，`Repo.merge` 在 `confirm_bring_in=False` 时拒绝执行并打印清单；只有 `confirm_bring_in=True` 才继续（方案 C：不悄悄带入，但也不因合法的小差异卡死）

- [ ] **Step 1: Write the failing test**

`tests/test_git_rules.py`：

```python
import pytest

from runtime.git_host.rules import (
    RuleViolation,
    check_branch_name,
    check_commit_message,
    check_commit_paths,
    check_merge,
    parse_branch,
)


def test_parse_branch_accepts_chinese_description():
    info = parse_branch("feature/test/lsh/15579-FMS运费推送补全")
    assert info.target == "test" and info.user_tag == "lsh"
    assert info.task == "15579" and info.desc == "FMS运费推送补全"


def test_parse_branch_rejects_missing_task():
    assert parse_branch("feature/test/lsh/no-task") is None


def test_check_branch_name_requires_matching_user_tag():
    with pytest.raises(RuleViolation) as exc:
        check_branch_name("feature/test/other/15579-x", user_tag="lsh")
    assert exc.value.rule == "branch-naming"


def test_check_branch_name_rejects_space_in_desc():
    with pytest.raises(RuleViolation):
        check_branch_name("feature/test/lsh/15579-a b", user_tag="lsh")


def test_check_commit_message_accepts_feat_with_body():
    check_commit_message("feat-15579: 补全运费推送\n\n按平台拆分批次后再推送。")


def test_check_commit_message_rejects_missing_body():
    with pytest.raises(RuleViolation) as exc:
        check_commit_message("feat-15579: 补全运费推送")
    assert exc.value.rule == "commit-message"


def test_check_commit_message_rejects_conventional_style():
    with pytest.raises(RuleViolation):
        check_commit_message("feat(wms): 补全\n\n正文")


def test_check_commit_paths_blocks_pom():
    with pytest.raises(RuleViolation) as exc:
        check_commit_paths(["src/a.java", "pom.xml"], ["pom.xml", "vite.config.ts"])
    assert exc.value.rule == "forbidden-path"
    assert "pom.xml" in exc.value.message


def test_check_commit_paths_allows_clean_set():
    check_commit_paths(["src/a.java"], ["pom.xml"])


def test_merge_to_test_is_direct_violation():
    with pytest.raises(RuleViolation) as exc:
        check_merge("feature/dev/lsh/1-x", "test", None, [])
    assert exc.value.rule == "direct-merge"


def test_merge_to_prod_is_direct_violation():
    with pytest.raises(RuleViolation):
        check_merge("feature/dev/lsh/1-x", "prod", None, [])


def test_merge_prod_derived_into_dev_is_blocked():
    with pytest.raises(RuleViolation) as exc:
        check_merge("feature/prod/lsh/1-x", "dev", "prod", [])
    assert exc.value.rule == "prod-derived"


def test_merge_feature_test_with_foreign_commits_returns_confirmation_list():
    assert check_merge("feature/test/lsh/1-x", "dev", "test", ["abc123"]) == ["abc123"]


def test_merge_feature_test_with_no_foreign_commits_passes():
    check_merge("feature/test/lsh/1-x", "dev", "test", [])


def test_merge_dev_feature_into_dev_passes():
    check_merge("feature/dev/lsh/1-x", "dev", "dev", [])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_git_rules.py -q`
Expected: FAIL，报 `ModuleNotFoundError: No module named 'runtime.git_host'`

- [ ] **Step 3: Implement `runtime/git_host/rules.py` and empty `runtime/git_host/__init__.py`**

分支正则：`^feature/(dev|test|prod)/([A-Za-z0-9_-]+)/(\d+)-([^\s/\\]+)$`。
提交首行正则：`^(feat|fix)-(\d+): \S.*$`，正文要求首行后有非空行。
`check_branch_name` 先调 `parse_branch`，None 则抛违规；再比较 `user_tag`。
`check_merge` 第 3 条的「源分支自身」判定：`bring_in` 非空即视为有外来提交（调用方已经用 `git log target..source` 之外的集合计算好 `bring_in`，rules 不做 git 调用）。

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_git_rules.py -q`
Expected: PASS（14 passed）

- [ ] **Step 5: Commit**

```bash
git add runtime/git_host/__init__.py runtime/git_host/rules.py tests/test_git_rules.py
git commit -m "feat: git 规则校验"
```

---

### Task 2: 项目配置与令牌读取

**Files:**
- Create: `runtime/git_host/config.py`
- Test: `tests/test_git_host_config.py`

**Interfaces:**
- Consumes: `runtime.config.load_env(path) -> dict[str, str]`、`runtime.config.project_dir(project_id) -> Path`（已存在）
- Produces:
  - `class GitHostConfigError(Exception)`
  - `@dataclass GitHostConfig`：`user_tag: str`、`repo_path: Path`、`kind: str`、`base_url: str`、`project_path: str`、`token_key: str`、`branches: dict[str, str]`、`forbid_commit_paths: list[str]`
  - `load_git_host_config(project_id: str, home: Path | None = None) -> GitHostConfig`
  - `read_token(project_id: str, token_key: str, home: Path | None = None) -> str`（缺失抛 `GitHostConfigError`，消息只含键名）
  - `save_user_tag(project_id: str, user_tag: str, home: Path | None = None) -> None`

- [ ] **Step 1: Write the failing test**

`tests/test_git_host_config.py`：

```python
import pytest

from runtime.git_host.config import (
    GitHostConfigError,
    load_git_host_config,
    read_token,
    save_user_tag,
)

YAML = """user_tag: lsh
repo_path: C:/project/demo
host:
  kind: gitlab
  base_url: http://git.example.com
  project_path: grp/demo
  token_key: GITLAB_TOKEN_DEMO
branches:
  dev: dev
  test: test
  prod: prod
rules:
  forbid_commit_paths: [pom.xml, vite.config.ts]
"""


@pytest.fixture
def home(tmp_path):
    proj = tmp_path / "projects" / "demo"
    proj.mkdir(parents=True)
    (proj / "git_hosts.yaml").write_text(YAML, encoding="utf-8")
    (proj / ".env").write_text("GITLAB_TOKEN_DEMO=fake-token-value\n", encoding="utf-8")
    return tmp_path


def test_loads_host_and_rules(home):
    cfg = load_git_host_config("demo", home=home)
    assert cfg.kind == "gitlab" and cfg.project_path == "grp/demo"
    assert cfg.user_tag == "lsh"
    assert cfg.forbid_commit_paths == ["pom.xml", "vite.config.ts"]


def test_reads_token_from_project_env(home):
    assert read_token("demo", "GITLAB_TOKEN_DEMO", home=home) == "fake-token-value"


def test_missing_token_names_key_only(home):
    with pytest.raises(GitHostConfigError) as exc:
        read_token("demo", "GITHUB_TOKEN_NOPE", home=home)
    assert "GITHUB_TOKEN_NOPE" in str(exc.value)
    assert "fake-token-value" not in str(exc.value)


def test_unknown_host_kind_rejected(home):
    p = home / "projects" / "demo" / "git_hosts.yaml"
    p.write_text(YAML.replace("kind: gitlab", "kind: bitbucket"), encoding="utf-8")
    with pytest.raises(GitHostConfigError, match="bitbucket"):
        load_git_host_config("demo", home=home)


def test_save_user_tag_is_persisted(home):
    p = home / "projects" / "demo" / "git_hosts.yaml"
    p.write_text(YAML.replace("user_tag: lsh", "user_tag: "), encoding="utf-8")
    save_user_tag("demo", "zhang", home=home)
    assert load_git_host_config("demo", home=home).user_tag == "zhang"


def test_missing_user_tag_is_empty_not_default(home):
    p = home / "projects" / "demo" / "git_hosts.yaml"
    p.write_text(YAML.replace("user_tag: lsh", "user_tag: "), encoding="utf-8")
    assert load_git_host_config("demo", home=home).user_tag == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_git_host_config.py -q`
Expected: FAIL，`ModuleNotFoundError: No module named 'runtime.git_host.config'`

- [ ] **Step 3: Implement `runtime/git_host/config.py`**

`load_git_host_config` 读 `<project_dir>/git_hosts.yaml`，缺文件抛 `GitHostConfigError("未找到 git_hosts.yaml")`。`kind` 只允许 `github|gitee|gitlab`。
`user_tag` 缺省为空字符串，不设默认值（spec §6：第一次使用询问）。
`save_user_tag` 只改写 `user_tag` 行，不重新序列化整份 YAML（保留注释和其它键）。
`read_token` 用 `runtime.config.load_env`，缺失时消息格式 `"缺少令牌 {token_key}，请在项目 .env 中填写"`。

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_git_host_config.py -q`
Expected: PASS（6 passed）

- [ ] **Step 5: Commit**

```bash
git add runtime/git_host/config.py tests/test_git_host_config.py
git commit -m "feat: git 托管项目配置与令牌读取"
```

---

### Task 3: 本地 git 操作封装

**Files:**
- Create: `runtime/git_host/repo.py`
- Test: `tests/test_git_repo.py`

**Interfaces:**
- Consumes: `rules.check_commit_message`、`rules.check_commit_paths`、`rules.check_merge`（Task 1）
- Produces:
  - `class RepoError(Exception)`
  - `class Repo(path: Path)`，方法：
    - `current_branch() -> str`
    - `is_clean() -> bool`
    - `staged_paths() -> list[str]`
    - `commit(message: str, forbidden: list[str]) -> str`（返回短 hash；先 `check_commit_message` 与 `check_commit_paths`）
    - `bring_in_commits(source: str, target: str, base: str) -> list[str]`（定义：`incoming = git rev-list --cherry-pick --right-only <target>...<source>`，`own = git rev-list --cherry-pick --right-only <base>...<source>`，返回 `incoming - own`；`base` 由 `fork_base(source)` 给出）。另有 `fork_base(source: str) -> str | None`：在 dev/test/prod 中取 source 的祖先分支，其中 `git rev-list --count <b>..<source>` 最小者
    - `merge(source: str, target: str, source_base: str | None, forbidden_targets: list[str]) -> None`（先 `check_merge`，再 `git checkout target && git merge --no-ff source`；冲突时 `git merge --abort` 并抛 `RepoError` 列出冲突文件）
    - `push(branch: str) -> None`
    - `create_branch(name: str, target: str) -> None`：`git fetch origin`，然后 `git checkout -b <name> --no-track origin/<target>`；切后执行 `git rev-list --count origin/<target>..HEAD`，非 0 则抛 `RepoError`
    - `verify_flow(prod_branch: str, test_branch: str, target: str) -> FlowReport`：`FlowReport` 含三份清单 `prod_into_test`、`test_net_vs_test`、`test_net_vs_target`，每份是 `list[Commit]` 加 `files: int`；`prod_only: list[str]` 为「在 origin/prod 中、不在 origin/test 中」的提交，非空则 `safe` 为 False。只读，不修改仓库
    - `cherry_pick(commits: list[str]) -> list[str]`：在当前分支（同步分支）上按顺序执行 `git cherry-pick -x <hash>`，返回新提交的短 hash 列表；冲突时 `git cherry-pick --abort` 并抛 `RepoError` 列出冲突文件，不自动解决
    - `check_prod_derived(source_base: str | None, target_branch: str) -> None`：只当 `target_branch` 是 `dev` 或 `test`（分支名本身，不是衍生关系）且源分支以 prod 为基底时抛 `prod-derived`；目标为 test 衍生分支（`feature/test/...`）时不抛
    - `push` 的远端分支名固定为本地分支名：`git push -u origin <branch>:<branch>`；本地分支名为 test/dev/prod 时抛 `RuleViolation(rule="push-target")`

- [ ] **Step 1: Write the failing test**

`tests/test_git_repo.py`：

```python
import os
import subprocess

import pytest

from runtime.git_host.repo import Repo, RepoError
from runtime.git_host.rules import RuleViolation


def _git(repo, *args, env=None):
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          capture_output=True, text=True,
                          env={**os.environ, **(env or {})}).stdout.strip()


def _init(tmp_path):
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "dev")
    _git(repo, "config", "user.email", "t@x.com")
    _git(repo, "config", "user.name", "t")
    (repo / "a.txt").write_text("1", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-q", "-m", "init")
    return repo


def test_commit_rejects_bad_message(tmp_path):
    repo = _init(tmp_path)
    (repo / "b.txt").write_text("2", encoding="utf-8")
    _git(repo, "add", "b.txt")
    with pytest.raises(RuleViolation):
        Repo(repo).commit("随便写写", forbidden=["pom.xml"])


def test_commit_rejects_forbidden_staged_path(tmp_path):
    repo = _init(tmp_path)
    (repo / "pom.xml").write_text("<project/>", encoding="utf-8")
    _git(repo, "add", "pom.xml")
    with pytest.raises(RuleViolation) as exc:
        Repo(repo).commit("feat-1: 调整\n\n正文说明。", forbidden=["pom.xml"])
    assert exc.value.rule == "forbidden-path"


def test_commit_succeeds_with_valid_message(tmp_path):
    repo = _init(tmp_path)
    (repo / "b.txt").write_text("2", encoding="utf-8")
    _git(repo, "add", "b.txt")
    short = Repo(repo).commit("feat-1: 新增 b\n\n添加 b.txt 用于测试。", forbidden=["pom.xml"])
    assert len(short) >= 7


def test_bring_in_is_empty_for_clean_branch(tmp_path):
    repo = _init(tmp_path)
    _git(repo, "checkout", "-q", "-b", "feature/dev/lsh/1-x")
    (repo / "c.txt").write_text("3", encoding="utf-8")
    _git(repo, "add", "c.txt")
    _git(repo, "commit", "-q", "-m", "feat-1: c\n\nc")
    assert Repo(repo).bring_in_commits("feature/dev/lsh/1-x", "dev", base="dev") == []


def test_bring_in_lists_base_commits_missing_from_target(tmp_path):
    repo = _init(tmp_path)
    _git(repo, "checkout", "-q", "-b", "test")
    (repo / "t.txt").write_text("t", encoding="utf-8")
    _git(repo, "add", "t.txt")
    _git(repo, "commit", "-q", "-m", "feat-2: t

t")
    test_tip = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", "-b", "feature/test/lsh/1-x")
    (repo / "c.txt").write_text("c", encoding="utf-8")
    _git(repo, "add", "c.txt")
    _git(repo, "commit", "-q", "-m", "feat-1: c

c")
    assert Repo(repo).bring_in_commits("feature/test/lsh/1-x", "dev", base="test") == [test_tip]


def test_merge_conflict_aborts_and_lists_files(tmp_path):
    repo = _init(tmp_path)
    _git(repo, "checkout", "-q", "-b", "feature/dev/lsh/1-x")
    (repo / "a.txt").write_text("from-feature", encoding="utf-8")
    _git(repo, "commit", "-qam", "feat-1: f\n\nf")
    _git(repo, "checkout", "-q", "dev")
    (repo / "a.txt").write_text("from-dev", encoding="utf-8")
    _git(repo, "commit", "-qam", "feat-2: d\n\nd")
    with pytest.raises(RepoError) as exc:
        Repo(repo).merge("feature/dev/lsh/1-x", "dev", None, forbidden_targets=["test", "prod"])
    assert "a.txt" in str(exc.value)
    assert _git(repo, "status", "--porcelain") == ""


def test_cherry_pick_brings_content_not_hash(tmp_path):
    repo = _init(tmp_path)
    _git(repo, "checkout", "-q", "-b", "feature/prod/lsh/1-hot")
    (repo / "fix.txt").write_text("fixed", encoding="utf-8")
    _git(repo, "add", "fix.txt")
    _git(repo, "commit", "-q", "-m", "fix-1: 热修

修正。")
    hot = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", "dev")
    _git(repo, "checkout", "-q", "-b", "feature/test/lsh/1-sync")
    new = Repo(repo).cherry_pick([hot])
    assert len(new) == 1
    assert _git(repo, "rev-parse", "HEAD") != hot
    assert (repo / "fix.txt").read_text(encoding="utf-8") == "fixed"


def test_cherry_pick_conflict_aborts_and_lists_files(tmp_path):
    repo = _init(tmp_path)
    _git(repo, "checkout", "-q", "-b", "feature/prod/lsh/1-hot")
    (repo / "a.txt").write_text("hot", encoding="utf-8")
    _git(repo, "commit", "-qam", "fix-1: h

h")
    hot = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", "dev")
    (repo / "a.txt").write_text("other", encoding="utf-8")
    _git(repo, "commit", "-qam", "feat-2: o

o")
    with pytest.raises(RepoError) as exc:
        Repo(repo).cherry_pick([hot])
    assert "a.txt" in str(exc.value)
    assert _git(repo, "status", "--porcelain") == ""


def test_create_branch_is_independent_of_target(tmp_path):
    repo = _init(tmp_path)
    _git(repo, "remote", "add", "origin", str(repo))
    _git(repo, "fetch", "-q", "origin")
    Repo(repo).create_branch("feature/dev/lsh/1-x", target="dev")
    assert _git(repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}", check=False) == ""
    assert _git(repo, "rev-list", "--count", "origin/dev..HEAD") == "0"


def test_push_to_non_matching_remote_is_refused(tmp_path):
    repo = _init(tmp_path)
    _git(repo, "checkout", "-q", "-b", "test")
    with pytest.raises(RuleViolation) as exc:
        Repo(repo).push("test")
    assert exc.value.rule == "push-target"


def test_merge_to_test_is_refused_before_touching_git(tmp_path):
    repo = _init(tmp_path)
    with pytest.raises(RuleViolation) as exc:
        Repo(repo).merge("feature/dev/lsh/1-x", "test", None, forbidden_targets=["test", "prod"])
    assert exc.value.rule == "direct-merge"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_git_repo.py -q`
Expected: FAIL，`ModuleNotFoundError: No module named 'runtime.git_host.repo'`

- [ ] **Step 3: Implement `runtime/git_host/repo.py`**

所有 git 调用用列表参数，不拼 shell 字符串。`bring_in_commits` 用 `git rev-list --cherry-pick --right-only target...source` 得到 source 侧独有的提交，再与 `git log` 比较得出「不属于源分支自身」的部分；实现时按这个定义写，并以测试为准。
`merge` 冲突检测用 `git merge --no-ff` 的返回码，非 0 时取 `git diff --name-only --diff-filter=U` 列出冲突文件，然后 `git merge --abort`。

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_git_repo.py -q`
Expected: PASS（6 passed）

- [ ] **Step 5: Commit**

```bash
git add runtime/git_host/repo.py tests/test_git_repo.py
git commit -m "feat: 本地 git 操作封装与规则接入"
```

---

### Task 4: 平台基类与令牌头

**Files:**
- Create: `runtime/git_host/base.py`
- Test: `tests/test_git_host_base.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `class HostError(Exception)`，属性 `status: int | None`
  - `@dataclass MergeRequest(number: str, url: str, state: str, mergeable: bool | None)`
  - `class GitHost(ABC)`：
    - `__init__(self, base_url: str, project_path: str, token: str, session=None)`
    - `abstract create_mr(source: str, target: str, title: str) -> MergeRequest`
    - `abstract get_mr(number: str) -> MergeRequest`
    - `abstract auth_headers() -> dict[str, str]`
    - `_request(method: str, path: str, *, json=None, params=None) -> dict`：统一异常为 `HostError`，异常消息只含方法、路径、状态码，不含令牌与请求体
    - `_redact(text: str) -> str`：把 `self.token` 替换为 `***`

- [ ] **Step 1: Write the failing test**

`tests/test_git_host_base.py`：

```python
import pytest

from runtime.git_host.base import GitHost, HostError

FAKE = "fake-secret-token-12345"


class _Resp:
    def __init__(self, status, body):
        self.status_code = status
        self._body = body

    def json(self):
        return self._body


class _Session:
    def __init__(self, status=200, body=None, raise_exc=None):
        self.status = status
        self.body = body or {}
        self.raise_exc = raise_exc
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if self.raise_exc:
            raise self.raise_exc
        return _Resp(self.status, self.body)


class _Concrete(GitHost):
    def create_mr(self, source, target, title):
        raise NotImplementedError

    def get_mr(self, number):
        raise NotImplementedError

    def auth_headers(self):
        return {"X-Test": self.token}


def test_request_builds_url_and_headers():
    sess = _Session(body={"ok": 1})
    host = _Concrete("http://h", "grp/demo", FAKE, session=sess)
    assert host._request("GET", "/x") == {"ok": 1}
    method, url, kwargs = sess.calls[0]
    assert url == "http://h/x"
    assert kwargs["headers"]["X-Test"] == FAKE


def test_http_error_message_omits_token():
    sess = _Session(status=401, body={"message": "unauthorized"})
    host = _Concrete("http://h", "grp/demo", FAKE, session=sess)
    with pytest.raises(HostError) as exc:
        host._request("POST", "/merge_requests", json={"title": "x"})
    assert exc.value.status == 401
    assert FAKE not in str(exc.value)


def test_network_error_is_wrapped_and_redacted():
    import requests

    sess = _Session(raise_exc=requests.ConnectionError(f"failed token={FAKE}"))
    host = _Concrete("http://h", "grp/demo", FAKE, session=sess)
    with pytest.raises(HostError) as exc:
        host._request("GET", "/x")
    assert FAKE not in str(exc.value)
    assert "***" in str(exc.value)


def test_redact_replaces_token():
    host = _Concrete("http://h", "grp/demo", FAKE, session=_Session())
    assert host._redact(f"a {FAKE} b") == "a *** b"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_git_host_base.py -q`
Expected: FAIL，`ModuleNotFoundError: No module named 'runtime.git_host.base'`

- [ ] **Step 3: Implement `runtime/git_host/base.py`**

`_request` 的超时：读请求 30 秒、写请求 60 秒，写请求**不重试**。异常处理：`requests.RequestException` 与 HTTP ≥ 400 都转 `HostError`，消息经 `_redact`，格式 `"{method} {path} 失败（HTTP {status}）：{平台 message 前 200 字符}"`，不含请求体。

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_git_host_base.py -q`
Expected: PASS（4 passed）

- [ ] **Step 5: Commit**

```bash
git add runtime/git_host/base.py tests/test_git_host_base.py
git commit -m "feat: git 托管平台基类与错误脱敏"
```

---

### Task 5: GitLab 适配器

**Files:**
- Create: `runtime/git_host/gitlab.py`
- Test: `tests/test_git_host_gitlab.py`

**Interfaces:**
- Consumes: `GitHost`、`HostError`、`MergeRequest`（Task 4）
- Produces: `class GitLabHost(GitHost)`，`create_mr` 调 `POST /api/v4/projects/{url-encoded project_path}/merge_requests`，`get_mr` 调 `GET .../merge_requests/{number}`；`auth_headers` 返回 `{"PRIVATE-TOKEN": token}`

- [ ] **Step 1: Write the failing test**

`tests/test_git_host_gitlab.py`：

```python
import pytest

from runtime.git_host.base import HostError
from runtime.git_host.gitlab import GitLabHost

FAKE = "fake-gitlab-token-999"


class _Resp:
    def __init__(self, status, body):
        self.status_code = status
        self._body = body

    def json(self):
        return self._body


class _Sess:
    def __init__(self, status=201, body=None):
        self.status = status
        self.body = body or {}
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return _Resp(self.status, self.body)


def test_create_mr_uses_encoded_project_path():
    sess = _Sess(body={"iid": 1819, "web_url": "http://g/mr/1819", "state": "opened", "merge_status": "can_be_merged"})
    host = GitLabHost("http://g", "hexincloud/hexincloud", FAKE, session=sess)
    mr = host.create_mr("feature/test/lsh/1-x", "test", "FMS 补全")
    method, url, kwargs = sess.calls[0]
    assert method == "POST"
    assert url == "http://g/api/v4/projects/hexincloud%2Fhexincloud/merge_requests"
    assert kwargs["json"] == {"source_branch": "feature/test/lsh/1-x", "target_branch": "test", "title": "FMS 补全"}
    assert kwargs["headers"]["PRIVATE-TOKEN"] == FAKE
    assert mr.number == "1819" and mr.mergeable is True


def test_get_mr_reads_status():
    sess = _Sess(status=200, body={"iid": 7, "web_url": "u", "state": "merged", "merge_status": "cannot_be_merged"})
    host = GitLabHost("http://g", "a/b", FAKE, session=sess)
    mr = host.get_mr("7")
    assert mr.state == "merged" and mr.mergeable is False


def test_existing_mr_is_reported_not_duplicated():
    sess = _Sess(status=409, body={"message": ["Another open merge request already exists"]})
    host = GitLabHost("http://g", "a/b", FAKE, session=sess)
    with pytest.raises(HostError) as exc:
        host.create_mr("feature/test/lsh/1-x", "test", "t")
    assert exc.value.status == 409


def test_forbidden_is_reported_as_permission():
    sess = _Sess(status=403, body={"message": "403 Forbidden"})
    host = GitLabHost("http://g", "a/b", FAKE, session=sess)
    with pytest.raises(HostError) as exc:
        host.create_mr("feature/test/lsh/1-x", "test", "t")
    assert exc.value.status == 403
    assert FAKE not in str(exc.value)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_git_host_gitlab.py -q`
Expected: FAIL，`ModuleNotFoundError: No module named 'runtime.git_host.gitlab'`

- [ ] **Step 3: Implement `runtime/git_host/gitlab.py`**

`quote(project_path, safe="")` 编码路径。`mergeable` 映射：`merge_status == "can_be_merged"` → True，`"cannot_be_merged"` → False，其它 → None。
`create_mr` 的 409 由 `HostError.status` 原样透出，由调用方（Task 7）决定如何提示。

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_git_host_gitlab.py -q`
Expected: PASS（4 passed）

- [ ] **Step 5: Commit**

```bash
git add runtime/git_host/gitlab.py tests/test_git_host_gitlab.py
git commit -m "feat: GitLab MR 适配器"
```

---

### Task 6: GitHub 与 Gitee 适配器

**Files:**
- Create: `runtime/git_host/github.py`
- Create: `runtime/git_host/gitee.py`
- Test: `tests/test_git_host_github_gitee.py`

**Interfaces:**
- Consumes: `GitHost`、`HostError`、`MergeRequest`（Task 4）
- Produces:
  - `class GitHubHost(GitHost)`：`create_mr` → `POST {base}/repos/{owner}/{repo}/pulls`，body `{"head","base","title"}`，`number` 取 `number`，`mergeable` 取 `mergeable`（None 表示未计算）；`get_mr` → `GET .../pulls/{number}`；`auth_headers` → `{"Authorization": "Bearer <token>", "Accept": "application/vnd.github+json"}`
  - `class GiteeHost(GitHost)`：`create_mr` → `POST {base}/api/v5/repos/{owner}/{repo}/pulls`，body `{"head","base","title","access_token"}` 不采用；令牌**只放 Header** `Authorization: token <token>`；`number` 取 `number`；`mergeable` 取 `mergeable`

- [ ] **Step 1: Write the failing test**

`tests/test_git_host_github_gitee.py`：

```python
from runtime.git_host.github import GitHubHost
from runtime.git_host.gitee import GiteeHost

FAKE = "fake-platform-token-777"


class _Resp:
    def __init__(self, status, body):
        self.status_code = status
        self._body = body

    def json(self):
        return self._body


class _Sess:
    def __init__(self, status=201, body=None):
        self.status = status
        self.body = body or {}
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return _Resp(self.status, self.body)


def test_github_pr_uses_bearer_and_head_base():
    sess = _Sess(body={"number": 42, "html_url": "https://github.com/o/r/pull/42", "state": "open", "mergeable": True})
    host = GitHubHost("https://api.github.com", "o/r", FAKE, session=sess)
    pr = host.create_mr("feature/dev/lsh/1-x", "dev", "t")
    method, url, kwargs = sess.calls[0]
    assert method == "POST" and url == "https://api.github.com/repos/o/r/pulls"
    assert kwargs["json"] == {"head": "feature/dev/lsh/1-x", "base": "dev", "title": "t"}
    assert kwargs["headers"]["Authorization"] == f"Bearer {FAKE}"
    assert pr.number == "42" and pr.mergeable is True


def test_github_unknown_mergeable_is_none():
    sess = _Sess(status=200, body={"number": 1, "html_url": "u", "state": "open"})
    host = GitHubHost("https://api.github.com", "o/r", FAKE, session=sess)
    assert host.get_mr("1").mergeable is None


def test_gitee_pr_puts_token_only_in_header():
    sess = _Sess(body={"number": 9, "html_url": "https://gitee.com/o/r/pulls/9", "state": "open", "mergeable": False})
    host = GiteeHost("https://gitee.com", "o/r", FAKE, session=sess)
    pr = host.create_mr("feature/test/lsh/1-x", "test", "t")
    method, url, kwargs = sess.calls[0]
    assert url == "https://gitee.com/api/v5/repos/o/r/pulls"
    assert "access_token" not in kwargs["json"]
    assert kwargs["headers"]["Authorization"] == f"token {FAKE}"
    assert pr.number == "9" and pr.mergeable is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_git_host_github_gitee.py -q`
Expected: FAIL，`ModuleNotFoundError: No module named 'runtime.git_host.github'`

- [ ] **Step 3: Implement `runtime/git_host/github.py` and `runtime/git_host/gitee.py`**

两者都继承 `GitHost`，只覆盖 `auth_headers` 与路径。`mergeable` 直接取平台布尔，缺失为 None。Gitee 路径中的 `owner/repo` 不做 URL 编码（平台不要求）。

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_git_host_github_gitee.py -q`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add runtime/git_host/github.py runtime/git_host/gitee.py tests/test_git_host_github_gitee.py
git commit -m "feat: GitHub 与 Gitee PR 适配器"
```

---

### Task 7: 适配器工厂与平台选择

**Files:**
- Modify: `runtime/git_host/__init__.py`
- Test: `tests/test_git_host_factory.py`

**Interfaces:**
- Consumes: `GitLabHost`（Task 5）、`GitHubHost`（Task 6）、`GiteeHost`（Task 6）、`load_git_host_config`、`read_token`（Task 2）
- Produces: `get_host(project_id: str, home: Path | None = None) -> GitHost`，按 `kind` 选择类，令牌经 `read_token` 获取

- [ ] **Step 1: Write the failing test**

`tests/test_git_host_factory.py`：

```python
import pytest

from runtime.git_host import get_host
from runtime.git_host.config import GitHostConfigError
from runtime.git_host.github import GitHubHost
from runtime.git_host.gitee import GiteeHost
from runtime.git_host.gitlab import GitLabHost


def _project(home, kind, token_key="TOKEN_KEY", env_line="TOKEN_KEY=fake-x"):
    proj = home / "projects" / "demo"
    proj.mkdir(parents=True)
    (proj / "git_hosts.yaml").write_text(
        f"""user_tag: lsh
repo_path: C:/x
host:
  kind: {kind}
  base_url: http://h
  project_path: a/b
  token_key: {token_key}
branches: {{dev: dev, test: test, prod: prod}}
rules:
  forbid_commit_paths: []
""",
        encoding="utf-8",
    )
    (proj / ".env").write_text(env_line + "\n", encoding="utf-8")
    return home


@pytest.mark.parametrize("kind,cls", [("gitlab", GitLabHost), ("github", GitHubHost), ("gitee", GiteeHost)])
def test_factory_picks_class_by_kind(tmp_path, kind, cls):
    home = _project(tmp_path, kind)
    assert isinstance(get_host("demo", home=home), cls)


def test_factory_fails_when_token_missing(tmp_path):
    home = _project(tmp_path, "gitlab", token_key="MISSING_KEY", env_line="OTHER=1")
    with pytest.raises(GitHostConfigError, match="MISSING_KEY"):
        get_host("demo", home=home)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_git_host_factory.py -q`
Expected: FAIL，`ImportError: cannot import name 'get_host'`

- [ ] **Step 3: Implement `get_host` in `runtime/git_host/__init__.py`**

`base_url` 直接取配置值；GitHub 的 `base_url` 默认 `https://api.github.com`，Gitee 默认 `https://gitee.com`，由配置覆盖。

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_git_host_factory.py -q`
Expected: PASS（4 passed）

- [ ] **Step 5: Commit**

```bash
git add runtime/git_host/__init__.py tests/test_git_host_factory.py
git commit -m "feat: git 托管适配器工厂"
```

---

### Task 8: 命令行入口

**Files:**
- Create: `scripts/git_host.py`
- Test: `tests/test_git_host_cli.py`

**Interfaces:**
- Consumes: `load_git_host_config`、`save_user_tag`（Task 2）、`Repo`（Task 3）、`get_host`（Task 7）、`RuleViolation`（Task 1）、`HostError`（Task 4）
- Produces: `main(argv: list[str] | None = None, host_fn=None, repo_fn=None) -> int`
  - 子命令：`commit -m MSG`、`push`、`merge --from BRANCH --to TARGET [--confirm-bring-in]`、`mr create --from BRANCH --to TARGET --title T`、`mr status NUMBER`、`set-user-tag TAG`、`branch create --name NAME --target T`（从 `origin/T` 切出，先 fetch）、`verify-flow --prod-branch P --test-branch T --target dev|test`（只读，输出三份清单，不合并）、`hotfix sync --fix-branch F --task N`（从 `origin/test` 切同步分支，cherry-pick 热修提交；冲突停止，不合并 F 本身）
  - 退出码：0 成功；1 规则违反或平台错误；2 参数或配置错误

- [ ] **Step 1: Write the failing test**

`tests/test_git_host_cli.py`：

```python
import pytest

from runtime.git_host.base import HostError, MergeRequest
from runtime.git_host.rules import RuleViolation
from scripts.git_host import main


class _FakeRepo:
    def __init__(self):
        self.calls = []
        self.bring_in = []

    def commit(self, message, forbidden):
        self.calls.append(("commit", message))
        return "abc1234"

    def push(self, branch):
        self.calls.append(("push", branch))

    def bring_in_commits(self, source, target, base):
        return list(self.bring_in)

    def merge(self, source, target, source_base, forbidden_targets, confirm_bring_in=False):
        self.calls.append(("merge", source, target, confirm_bring_in))


class _FakeHost:
    def create_mr(self, source, target, title):
        return MergeRequest(number="1819", url="http://g/mr/1819", state="opened", mergeable=True)

    def get_mr(self, number):
        return MergeRequest(number=number, url="u", state="merged", mergeable=None)


@pytest.fixture
def wired(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_TOOLS_HOME", str(tmp_path))
    return _FakeRepo()


def test_commit_subcommand_calls_repo(wired, tmp_path, capsys):
    rc = main(["--project", "demo", "commit", "-m", "feat-1: x\n\ny"],
              repo_fn=lambda *a, **k: wired, host_fn=lambda *a, **k: _FakeHost())
    assert rc == 0
    assert wired.calls == [("commit", "feat-1: x\n\ny")]


def test_merge_to_test_is_rejected_with_rule_name(wired, capsys):
    rc = main(["--project", "demo", "merge", "--from", "feature/dev/lsh/1-x", "--to", "test"],
              repo_fn=lambda *a, **k: wired, host_fn=lambda *a, **k: _FakeHost())
    assert rc == 1
    assert "[direct-merge]" in capsys.readouterr().out


def test_merge_with_bring_in_needs_confirmation(wired, capsys):
    wired.bring_in = ["abc1234"]
    args = ["--project", "demo", "merge", "--from", "feature/test/lsh/1-x", "--to", "dev"]
    rc = main(args, repo_fn=lambda *a, **k: wired, host_fn=lambda *a, **k: _FakeHost())
    assert rc == 1
    assert "abc1234" in capsys.readouterr().out
    rc = main(args + ["--confirm-bring-in"], repo_fn=lambda *a, **k: wired, host_fn=lambda *a, **k: _FakeHost())
    assert rc == 0


def test_mr_create_prints_url(wired, capsys):
    rc = main(["--project", "demo", "mr", "create", "--from", "feature/test/lsh/1-x",
               "--to", "test", "--title", "t"],
              repo_fn=lambda *a, **k: wired, host_fn=lambda *a, **k: _FakeHost())
    assert rc == 0
    assert "http://g/mr/1819" in capsys.readouterr().out


def test_platform_error_exits_one_without_token(wired, capsys):
    class _Failing(_FakeHost):
        def create_mr(self, *a):
            raise HostError("POST /x 失败（HTTP 403）", status=403)
    rc = main(["--project", "demo", "mr", "create", "--from", "feature/test/lsh/1-x",
               "--to", "test", "--title", "t"],
              repo_fn=lambda *a, **k: wired, host_fn=lambda *a, **k: _Failing())
    assert rc == 1
    assert "403" in capsys.readouterr().out


def test_set_user_tag_persists(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DATA_TOOLS_HOME", str(tmp_path))
    proj = tmp_path / "projects" / "demo"
    proj.mkdir(parents=True)
    (proj / "git_hosts.yaml").write_text("user_tag:\n", encoding="utf-8")
    assert main(["--project", "demo", "set-user-tag", "zhang"]) == 0
    assert "user_tag: zhang" in (proj / "git_hosts.yaml").read_text(encoding="utf-8")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_git_host_cli.py -q`
Expected: FAIL，`ModuleNotFoundError: No module named 'scripts.git_host'`

- [ ] **Step 3: Implement `scripts/git_host.py`**

沿用 `scripts/run.py` 的 `sys.path` 引导与 UTF-8 输出。
`RuleViolation` 与 `HostError` 统一打印为 `[<rule>] <message>` 或 `[HTTP <status>] <message>`，消息已在 Task 4 脱敏。
`merge` 对 `--to test|prod` 不调用 `Repo.merge`，直接抛 `RuleViolation("direct-merge")`，让规则模块决定，不在 CLI 里写分支判断。
`set-user-tag` 只在 `user_tag` 为空时写入；已有值时拒绝并提示（改名需要手工编辑，避免误覆盖）。

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_git_host_cli.py -q`
Expected: PASS（5 passed）

- [ ] **Step 5: Commit**

```bash
git add scripts/git_host.py tests/test_git_host_cli.py
git commit -m "feat: git 托管命令行入口"
```

---

### Task 9: 技能与安装接入

**Files:**
- Create: `skills/git-workflow/SKILL.md`
- Modify: `scripts/install.py`（`SKILLS` 追加 `git-workflow`）
- Modify: `tests/test_skills.py`
- Modify: `tests/test_install.py`（`NAMES` 追加 `git-workflow`）

**Interfaces:**
- Consumes: `scripts/git_host.py` 的子命令（Task 8）
- Produces: 第五个技能 `git-workflow`，被 Claude / Cursor / Codex 加载

- [ ] **Step 1: Write the failing test**

在 `tests/test_skills.py` 中：

```python
def test_git_skill_requires_user_tag_and_confirmation():
    text = (SKILLS / "git-workflow" / "SKILL.md").read_text(encoding="utf-8")
    assert "user_tag" in text
    assert "回显" in text
    assert "确认" in text
    assert "git_host.py" in text


def test_git_skill_never_asks_for_token_in_chat():
    text = (SKILLS / "git-workflow" / "SKILL.md").read_text(encoding="utf-8")
    assert "不要" in text and "令牌" in text
```

把 `test_skill_has_frontmatter_and_sections` 的参数列表追加 `"git-workflow"`。

在 `tests/test_install.py` 中，把 `NAMES` 替换为下面的完整元组（以此为准，不保留旧元组）：

```python
NAMES = ("data-gen-core", "db-access", "adapter-bootstrap", "report-writer", "git-workflow")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_skills.py tests/test_install.py -q`
Expected: FAIL，`FileNotFoundError: .../git-workflow/SKILL.md`

- [ ] **Step 3: Write `skills/git-workflow/SKILL.md` and update `install.py`**

frontmatter：`name: git-workflow`，`description` 写明触发词「提交」「推送」「拉取」「合并」「建 MR」「开 PR」「分支」，并声明「合并到 test/prod 只能建 MR」。

正文四段（适用场景 / 前置检查 / 执行 / 失败处理），另加「路径」段，与其它技能相同。关键规则必须写进文本：

- 第一次使用时若 `git_hosts.yaml` 的 `user_tag` 为空，询问用户并调用 `set-user-tag`，之后沿用
- **写操作前回显**：平台、项目、源分支、目标分支、MR 标题、将带入的提交数；等用户明确说「确认」或「执行」再运行。推送、建 MR 影响他人可见内容，不得直接执行
- 令牌缺失时只报键名（如 `GITLAB_TOKEN_XXX`），**不要**让用户把令牌贴进对话
- 合并到 test/prod 一律引导为 `mr create`，不提供直接合并的选项
- 规则拒绝时原样告诉用户规则名与原因，不绕过
- 平台返回 409（MR 已存在）时报告已有编号，不重复创建

`scripts/install.py` 的 `SKILLS` 列表追加 `"git-workflow"`。

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_skills.py tests/test_install.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add skills/git-workflow/SKILL.md scripts/install.py tests/test_skills.py tests/test_install.py
git commit -m "feat: git-workflow 技能与安装接入"
```

---

### Task 10: 文档与全量验证

**Files:**
- Modify: `README.md`
- Modify: `docs/usage.md`
- Modify: `.claude-plugin/plugin.json`、`.claude-plugin/marketplace.json`、`.cursor-plugin/plugin.json`、`.codex-plugin/plugin.json`（版本与描述）
- Modify: `skills/_references/trigger-routing.md`（新增 git 意图行，消歧顺序加一条）

**Interfaces:**
- Consumes: Task 1–9 全部产物

- [ ] **Step 1: Update trigger routing and docs**

`trigger-routing.md` 新增一行：

```
| 代码托管 | 提交、推送、拉取、合并、建 MR、开 PR、分支 | git, push, merge, mr, pull request | `git-workflow` |
```

消歧顺序在「报告」之后插入：「含提交 / 推送 / 合并 / 建 MR → `git-workflow`」。

`docs/usage.md` 新增「十一、代码托管」章节，内容：令牌放项目 `.env`、`git_hosts.yaml` 字段表、支持的三个平台、规则列表（与 spec §6 一致）、常用命令示例。

- [ ] **Step 2: Bump version and run full verification**

把四个清单的版本从 `1.2.0` 改为 `1.3.0`，描述加入「代码托管」。

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: 全部通过（约 170 个）

Run: `.venv/Scripts/python.exe scripts/check_secrets.py`
Expected: `未发现敏感信息`

Run: `.venv/Scripts/python.exe scripts/git_host.py --help`
Expected: 打印用法，退出码 0

- [ ] **Step 3: Commit**

```bash
git add README.md docs/usage.md skills/_references/trigger-routing.md .claude-plugin .cursor-plugin .codex-plugin
git commit -m "docs: 代码托管能力说明，版本升至 1.3.0"
```

---

## 端到端验收（需要你确认后做）

以下步骤会真的访问平台，**实施前必须得到你的明确同意**：

1. 在一个测试分支上执行 `mr create` 到 test，确认 MR 创建成功、编号与链接正确
2. 对已存在的 MR 再次执行 `mr create`，确认返回 409 且不重复创建
3. 用一个无效令牌执行，确认报错只显示键名与状态码，不泄露令牌
4. 用 `git_hosts.yaml` 把 `kind` 改为 `github`，确认 GitHub 适配器能查询公开仓库的 PR 列表（只读）
