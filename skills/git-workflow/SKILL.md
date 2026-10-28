---
name: git-workflow
description: >-
  代码托管操作：提交、推送、拉取、合并、建 MR/PR、开分支、热修同步。用户说「提交一下」「推到 dev」
  「开个 MR」「建分支」「同步热修」时使用。合并到 test 或 prod 只能建 MR，不能直接合并。写操作前必须回显并等待确认。
---

# Git 托管操作

## 适用场景

- 提交、推送改动（提交信息须符合团队格式）
- 从 dev、test、prod 切新分支
- 合并到 dev（本地合并，合并前核对将带入的内容）
- 建 MR/PR 到 test、prod、dev（支持 GitHub、Gitee、GitLab）
- 热修复同步：把 prod 的热修复同步到 test 衍生分支，再合到 test 和 dev

不适用：

- 造数、查库 → 用 `data-gen-core` 或 `db-access`
- 只看提交历史、不改仓库 → 直接用 `git log`

## 前置检查

1. 读 `<数据目录>/projects/<项目ID>/git_hosts.yaml`
2. 若 `user_tag` 为空：**询问用户**一次，然后用 `set-user-tag <标识>` 写入配置，之后沿用，不再询问
3. 确认项目 ID；无法确定就问，不猜
4. 确认目标：dev、test 还是 prod

任一项缺失就停止，说明缺什么。

## 路径

命令里的 `<TOOLS_DIR>` 是工具仓库根目录，按顺序确定：环境变量 `DATA_TOOLS_DIR` → `~/.data-tools/config.yaml` 的 `tools_dir` → 问用户仓库在哪，不要猜。通过 `install.ps1` 渲染安装时命令里已是绝对路径，可跳过。

解释器用仓库内 `.venv/Scripts/python.exe`；不存在时用 `python`，并先 `pip install -r requirements.txt`。

## 执行

所有操作通过命令行入口 `git_host.py`：

```bash
"<TOOLS_DIR>/.venv/Scripts/python.exe" "<TOOLS_DIR>/scripts/git_host.py" --project <项目ID> commit -m "feat-<任务号>: <描述>\n\n<正文>"
"<TOOLS_DIR>/.venv/Scripts/python.exe" "<TOOLS_DIR>/scripts/git_host.py" --project <项目ID> push --branch <分支>
"<TOOLS_DIR>/.venv/Scripts/python.exe" "<TOOLS_DIR>/scripts/git_host.py" --project <项目ID> mr create --from <源分支> --to <目标> --title "<标题>"
"<TOOLS_DIR>/.venv/Scripts/python.exe" "<TOOLS_DIR>/scripts/git_host.py" --project <项目ID> branch create --name <分支名> --target <dev|test|prod>
"<TOOLS_DIR>/.venv/Scripts/python.exe" "<TOOLS_DIR>/scripts/git_host.py" --project <项目ID> merge --from <源分支> --to dev [--confirm-bring-in]
"<TOOLS_DIR>/.venv/Scripts/python.exe" "<TOOLS_DIR>/scripts/git_host.py" --project <项目ID> verify-flow --prod-branch prod --test-branch <test衍生分支> --target dev
"<TOOLS_DIR>/.venv/Scripts/python.exe" "<TOOLS_DIR>/scripts/git_host.py" --project <项目ID> hotfix sync --fix-branch <热修分支> --task <任务号>
```

### 写操作前必须回显并等待确认

推送、建 MR、合并、热修同步都会影响他人可见的内容。执行前先回显：

- 平台、项目、源分支、目标分支
- MR 标题（如有）
- 将带入的提交数与文件数（合并到 dev 时，用 `verify-flow` 或 `merge` 的预检得到）

**只有用户明确说「确认」或「执行」，才运行写命令。** 不得因为用户只说了「推到 dev」就直接执行。

只读命令（`verify-flow`、`mr status`）可以直接执行。

## 硬规则

以下规则由工具强制执行。被拒绝时，**原样告诉用户规则名与原因**，不绕过、不换个方式硬做：

| 规则 | 说明 |
|---|---|
| `direct-merge` | 合到 test、prod 只能建 MR：`mr create --to test` 或 `--to prod` |
| `prod-derived` | prod 衍生分支不能直接合到 test 或 dev，要先经过 test 衍生的同步分支 |
| `net-increment` | 合到 dev 时若带入了非本分支的内容，先列清单，用户确认后加 `--confirm-bring-in` |
| `branch-naming` | 分支名须为 `feature/<目标>/<用户标识>/<任务号>-<描述>` |
| `commit-message` | 提交首行须为 `feat-<任务号>: <描述>` 或 `fix-<任务号>: <描述>`，且必须有正文 |
| `forbidden-path` | 本地环境配置（如 `pom.xml`、`vite.config.ts`）不得提交 |
| `push-target` | 本地分支名为 test、dev、prod 时不得推送；推送只到同名远端分支 |

### 从哪里切分支

- 改动最终进 dev：从 `origin/dev` 切
- 改动最终进 test：从 `origin/test` 切
- 改动最终进 prod：从 `origin/prod` 切（热修复）

**不要从 test 切分支去合 dev**，除非用户明确确认要带入 test 的内容。

### 热修复流程

1. 从 `origin/prod` 切热修复分支，修复，提交
2. 热修复分支开 MR 到 prod
3. 从 `origin/test` 切同步分支，执行 `hotfix sync`（用 cherry-pick 搬热修复的提交，不合并热修复分支本身）
4. 同步分支开 MR 到 test
5. 同步分支合到 dev 前，用 `verify-flow` 核对，确认只带入热修复的改动

## 令牌

- 令牌只从项目 `.env` 读取，`git_hosts.yaml` 的 `token_key` 指定键名
- 令牌缺失时只报键名（如 `GITLAB_TOKEN_XXX`），由用户自己去 `.env` 里填
- 不要让用户把令牌贴进对话。如果用户已经贴进来，提醒他去吊销并换一个
- 不要在任何命令行参数、日志、报告中输出令牌

## 失败处理

| 情况 | 动作 |
|---|---|
| 缺 `git_hosts.yaml` | 报路径，引导补配置，不现场猜仓库与平台 |
| 缺令牌 | 报键名，引导用户在项目 `.env` 中填写，不要求粘贴 |
| 令牌无效（401/403） | 报「令牌无效或权限不足」，不重试 |
| 平台返回 409 或 422（MR 已存在） | 报告已有编号和链接，**不重复创建** |
| 网络不通 | 报错并提示检查代理，不静默重试写请求 |
| 合并或 cherry-pick 冲突 | 停止，列出冲突文件，不尝试自动解决；由用户处理后重新开始 |
| 规则拒绝 | 原样告诉用户规则名与原因，不绕过 |
