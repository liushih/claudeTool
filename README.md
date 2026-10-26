# claudeTool

hexincloud 项目的独立工具集，放在仓库外，可跨机器复用。

## 新机器上手

需要 Python 3.11+、Node.js（仅浏览器工具用）。

```powershell
git clone <本仓库地址> C:\project\claudeTool
cd C:\project\claudeTool
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

`setup.ps1` 会建三个虚拟环境（根目录的工具包 runtime，加上两个老工具）、装依赖、从 `.env.example` 生成 `.env`。生成后需要手工填账号密码，见「凭据」一节。

前提：`hexincloud` 仓库与本目录同级（`C:\project\hexincloud`）；不在同级时设置 `HEXIN_REPO`。

之后按下一节把 skill 装进 AI 工具。工具包本身不需要单独「注册」，`~/.hexin-tools` 在第一次接入业务时自动生成。

## 目录

| 目录 | 用途 |
|------|------|
| `hexin-db-tools/` | 三环境库结构/数据比对、SQL 脚本执行核查、飞书台账审计。只读为主 |
| `hexin-data-gen/` | 通过接口造 B2D 提货单等业务数据，走真实业务链路 |
| `hexin-e2e/` | Playwright 浏览器驱动，封装登录、进页面、等接口返回 |
| `hxpaths.py` | 共享路径解析，被上面两个 Python 工具引用 |

## 常用命令

```bash
# 三环境结构比对
hexin-db-tools/.venv/Scripts/python.exe hexin-db-tools/schema_diff.py

# 脚本 × 台账 × 三环境三方比对
hexin-db-tools/.venv/Scripts/python.exe hexin-db-tools/audit_db.py

# 只读 SQL 查询
hexin-db-tools/.venv/Scripts/python.exe hexin-db-tools/pg_query.py dev "select 1"

# 批量造提货单
hexin-data-gen/.venv/Scripts/python.exe hexin-data-gen/batch_run.py --help

# 浏览器冒烟
cd hexin-e2e && node smoke.mjs
```

## 数据工具包（skills + runtime）

用白话触发连库与批量造数，规则本地累积，不重复推导。

Claude Code 走插件市场，装好后 skill 出现在 Settings → Skills 的 "From marketplaces you added" 一栏：

```text
/plugin marketplace add liushih/claudeTool
/plugin install hexin-tools@hexin-tools
```

插件只分发规则，不装 Python 依赖。仍然要把仓库 clone 到本机并跑一次 `setup.ps1`，否则 skill 里的命令会因缺包失败。

仓库是私有的，只有被授权的 GitHub 账号能装。

Cursor 和 Codex 没有这个市场，仍用安装脚本生成规则文件：

```powershell
# 安装到 Cursor / Codex（项目级）
powershell -ExecutionPolicy Bypass -File .\install.ps1 -Target cursor,codex -Scope project -ProjectDir C:\project\hexincloud

# 卸载（Cursor / Codex 需要带 -ProjectDir）
powershell -ExecutionPolicy Bypass -File .\install.ps1 -Remove -Target claude
powershell -ExecutionPolicy Bypass -File .\install.ps1 -Remove -Target cursor,codex -Scope project -ProjectDir C:\project\hexincloud
```

| 项 | 位置 |
|---|---|
| 规则源文件 | `skills/` |
| 执行引擎 | `runtime/` |
| 本地数据（适配层、脚本、凭据） | `%USERPROFILE%\.hexin-tools`，可用 `HEXIN_DATA_HOME` 覆盖 |
| 执行入口（造数） | `python scripts\run.py --project <项目ID> --entity <业务对象> --count <数量>` |
| 执行入口（SQL） | `python scripts\query.py --project <项目ID> --env dev --sql "<SQL>"` |
| 敏感扫描 | `python scripts\check_secrets.py` |

本地数据目录不进 git。设计见 `docs/superpowers/specs/`，实现计划见 `docs/superpowers/plans/`。

`setup.ps1` 会把本仓库路径写进 `%USERPROFILE%\.hexin-tools\config.yaml` 的 `tools_dir`，skill 靠它定位执行入口。仓库换位置后重跑一次 `setup.ps1`，或设置 `HEXIN_TOOLS`。

## 路径配置

脚本默认按目录关系推断，不需要改代码。需要覆盖时设置环境变量：

| 变量 | 默认值 |
|------|--------|
| `HEXIN_REPO` | `..\hexincloud` |
| `HEXIN_SKILL_SCRIPTS` | `$HEXIN_REPO\dev-overlay\.agents\skills\hx-sql-feishu-progress\scripts` |
| `HEXIN_DB_ENV` | `hexin-db-tools\.env` |
| `PW_PROFILE` | `..\pw-profile` |
| `HEXIN_BASE` / `HEXIN_BASE_URL` | 接口地址，见各工具 `.env` |

## 凭据

以下文件不进仓库，换机器时手工带或重新填写：

- `hexin-db-tools/.env` —— prod/dev/test 三套库账号
- `hexin-data-gen/.env` —— 接口地址、clientId、账号
- `hexin-e2e/.env` —— 浏览器登录账号（`HEXIN_PASSWORD`）
- `hexin-data-gen/.token.json` —— 登录令牌缓存，可删，下次自动登录
- `pw-profile/` —— 浏览器登录态，不拷，首次用会重新登录

## 不在仓库里的东西

- `apache-jmeter-5.6.3/`（150M）—— 需要时从官网下同名版本解压到本目录
- `pw-profile/`、`.venv/`、`node_modules/` —— `setup.ps1` 重建

## 一次性脚本（只在本地，不入库）

2026-10 SQL 交付批次的收尾脚本（`mark_*`、`update_*`、`register_*` 等）已从仓库移除，只保留在本机：

- 目标行（`TARGETS`）硬编码了具体脚本路径、批次日期和人员信息，属于内部资料
- 跑完即归档，不需要跨机器复用
- 写台账的能力来自 `hexincloud/dev-overlay/.agents/skills/hx-sql-feishu-progress/scripts/feishu_sheet.py`，跟着主仓库走

再遇到同类任务请**新写脚本**，不要复用或修改这些归档件。

## 其他注意

- 这些脚本对 dev/test/prod 以只读为主；写库一律走正常业务流程，不要用脚本直接改数据。
