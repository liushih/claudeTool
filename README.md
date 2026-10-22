# claudeTool

hexincloud 项目的独立工具集，放在仓库外，可跨机器复用。

## 新机器上手

```powershell
git clone <本仓库地址> C:\project\claudeTool
cd C:\project\claudeTool
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

`setup.ps1` 会建两个虚拟环境、装依赖、从 `.env.example` 生成 `.env`。生成后需要手工填账号密码，见「凭据」一节。

前提：`hexincloud` 仓库与本目录同级（`C:\project\hexincloud`）；不在同级时设置 `HEXIN_REPO`。

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
