# claudeTool

hexincloud 项目的独立工具集。把「连库查数」和「按业务流程批量造数」做成 AI 技能，
装进 Claude Code / Cursor / Codex 后用白话直接触发。

规则不写死在提示词里：每个项目的字段、枚举、时序存在本机适配层，用一次记一次；
凭据同样只在本机，不进仓库。

## 能力

| 能力 | 说一句 | 做什么 |
|---|---|---|
| 批量造数 | 「造 100 张提货单」 | 按本地适配层并发跑业务流程，逐单记台账，失败不中断，支持断点续跑 |
| 数据库访问 | 「查一下 dev 库最近 3 条提货单」 | 按项目配置连库执行 SQL；写操作先回显环境与语句 |
| 接入新业务 | 「接入 XX 业务」 | 陪跑并生成适配层 `adapter.yaml` 与坑库 `pitfalls.md` |

适配层缺失时不会现场猜接口，而是停下来转「接入新业务」。

## 快速开始

环境：Windows、Python 3.11+、Git。

**1. 克隆并初始化**

```powershell
git clone https://github.com/liushih/claudeTool.git C:\project\claudeTool
cd C:\project\claudeTool
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

`setup.ps1` 建虚拟环境、装依赖、生成 `.env`，并把工具目录写进
`%USERPROFILE%\.hexin-tools\config.yaml`。生成后需手工填账号密码，见「凭据」。

**2. 装进 AI 工具**

Claude Code 走插件市场，装好后出现在 Settings → Skills 的
"From marketplaces you added" 一栏：

```text
/plugin marketplace add liushih/claudeTool
/plugin install hexin-tools@hexin-tools
```

Cursor 和 Codex 没有市场，用安装脚本生成规则文件：

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -Target cursor,codex -Scope project -ProjectDir C:\project\hexincloud
```

插件只分发规则，不带 Python 依赖。仓库仍需 clone 到本机并跑过 `setup.ps1`。
仓库是私有的，只有被授权的 GitHub 账号能装。

**3. 接入第一条业务**

新开一个会话，直接说：

```text
接入 B2D 提货单业务
```

技能会逐项确认接口、字段、枚举和目标状态，跑通一条后把规则落到
`~/.hexin-tools/projects/<项目ID>/`。

## 使用示例

```text
查一下 dev 库最近 3 条提货单的单号和状态
在 hexincloud 的 dev 环境造 10 张 B2D 提货单，造到 UPLOADED
同一批次重跑一下，把失败的补上
把 dev 库 external_order_no = PB1026114338 的单子状态改回 NEW
```

详细用法、适配层写法与常见问题见 **[使用说明](docs/usage.md)**。

## 目录结构

| 路径 | 用途 |
|---|---|
| `skills/` | 三个技能的规则文件、契约文档与模板 |
| `runtime/` | 执行引擎：适配层加载、HTTP、台账、校验、数据库 |
| `scripts/` | 命令行入口：`run.py`、`query.py`、`install.py`、`check_secrets.py` |
| `tests/` | 67 个测试，含本地端到端冒烟 |
| `hexin-db-tools/` | 三环境库结构/数据比对、SQL 脚本核查。只读为主 |
| `hexin-data-gen/` | 旧版造数脚本，B2D 链路实现 |
| `hexin-e2e/` | Playwright 浏览器驱动 |
| `.claude-plugin/` | Claude Code 插件与市场清单 |

`hexincloud` 仓库默认与本目录同级（`..\hexincloud`），不在同级时设置 `HEXIN_REPO`。

## 配置

不需要改代码，必要时用环境变量覆盖：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `HEXIN_TOOLS` | `~/.hexin-tools/config.yaml` 的 `tools_dir` | 技能定位执行入口 |
| `HEXIN_DATA_HOME` | `%USERPROFILE%\.hexin-tools` | 适配层、台账、坑库、凭据 |
| `HEXIN_REPO` | `..\hexincloud` | 业务主仓库位置 |
| `HEXIN_DB_ENV` | `hexin-db-tools\.env` | 三环境库账号文件 |
| `HEXIN_SKILL_SCRIPTS` | `$HEXIN_REPO\dev-overlay\...\scripts` | 飞书台账脚本 |
| `PW_PROFILE` | `..\pw-profile` | 浏览器登录态 |

仓库换位置后重跑一次 `setup.ps1`，或设置 `HEXIN_TOOLS`。

## 凭据

以下文件不进仓库，换机器时手工填写：

- `hexin-db-tools/.env` —— prod/dev/test 三套库账号
- `hexin-data-gen/.env` —— 接口地址、clientId、账号
- `hexin-e2e/.env` —— 浏览器登录账号
- `~/.hexin-tools/projects/<项目ID>/.env` —— 适配层引用的值
- `~/.hexin-tools/projects/<项目ID>/` —— 适配层与业务脚本，整体不进 git

提交前可以自查：

```bash
.venv/Scripts/python.exe scripts/check_secrets.py
```

它只扫已跟踪文件，检查明文凭据、GitHub 令牌、私钥和私网地址。

## 注意

- 工具对 dev/test/prod 以只读为主；写库走正常业务流程，不要用脚本直接改数据。
- 写请求（POST/PUT）超时不会自动重试，避免重复建单。
- 本机 `~/.hexin-tools` 不跨机器拷贝，每台机器第一次接入时自己生成。

## 文档

- [使用说明](docs/usage.md)
- 设计文档：`docs/superpowers/specs/`
- 实现计划：`docs/superpowers/plans/`

## 许可

MIT
