<h1 align="center">
  claudeTool
  <br>
</h1>

<h3 align="center">
  面向业务系统的 AI 数据工具集 · 白话连库与批量造数
</h3>

<p align="center">
  <a href="./docs/usage.md">使用说明</a> ·
  <a href="./docs/superpowers/specs/">设计文档</a> ·
  <a href="./docs/superpowers/plans/">实现计划</a> ·
  <a href="./LICENSE">MIT</a>
</p>

## Preview

| 你说 | 技能做 |
| --- | --- |
| 查一下 dev 库最近 3 条提货单 | 连库执行 SQL，返回单号与状态 |
| 在 dev 造 100 张提货单，跑到 UPLOADED | 按本地规则并发造数，逐单记台账 |
| 同一批次重跑，把失败的补上 | 跳过已完成，只补失败 |
| 接入 XX 新业务 | 陪跑并生成该业务的规则与坑库 |

业务规则不写在提示词里：每个项目的字段、枚举、时序存在本机适配层，用一次记一次。
凭据同样只存本机，不进仓库。

每个项目一份适配层，互相独立。仓库自带的示例和旧工具面向 hexincloud，
接入其他项目只需新建 `<数据目录>/projects/<新项目ID>/`。

## Install

支持 Claude Code、Cursor、Codex。需要 Windows、Python 3.11+、Git。

#### 我应当怎样选择安装方式

| 工具 | 方式 | 适合 |
| --- | --- | --- |
| Claude Code | 插件市场 | 日常使用，更新跟着仓库走 |
| Cursor / Codex | 安装脚本 | 项目级规则，跟着业务仓库走 |
| 任意终端 | 命令行直接调用 | 脚本化、CI、临时排查 |

#### 第一步：初始化

```powershell
git clone https://github.com/liushih/claudeTool.git C:\project\claudeTool
cd C:\project\claudeTool
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

`setup.ps1` 建虚拟环境、装依赖、生成 `.env`，并把工具目录写进
`%USERPROFILE%\.hexin-tools\config.yaml`。

#### 第二步：装进 AI 工具

Claude Code 走插件市场：

```text
/plugin marketplace add liushih/claudeTool
/plugin install hexin-tools@hexin-tools
```

装好后 skill 出现在 Settings → Skills 的 "From marketplaces you added" 一栏。

Cursor / Codex 用安装脚本：

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -Target cursor,codex -Scope project -ProjectDir C:\project\hexincloud
```

插件只分发规则，不带 Python 依赖，仓库仍需 clone 到本机并跑过 `setup.ps1`。
仓库是私有的，只有被授权的 GitHub 账号能装。

#### 第三步：接入第一条业务

新开一个会话，直接说：

```text
接入 B2D 提货单业务
```

#### 安装说明和常见问题，请到 [使用说明](./docs/usage.md) 查看

## Configuration

不需要改代码，必要时用环境变量覆盖：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `HEXIN_TOOLS` | `~/.hexin-tools/config.yaml` 的 `tools_dir` | 技能定位执行入口 |
| `HEXIN_DATA_HOME` | `%USERPROFILE%\.hexin-tools` | 适配层、台账、坑库、凭据 |
| `HEXIN_REPO` | `..\hexincloud` | 业务主仓库位置 |
| `HEXIN_DB_ENV` | `hexin-db-tools\.env` | 三环境库账号文件 |
| `HEXIN_SKILL_SCRIPTS` | `$HEXIN_REPO\dev-overlay\...\scripts` | 飞书台账脚本 |
| `PW_PROFILE` | `..\pw-profile` | 浏览器登录态 |

仓库换位置后重跑一次 `setup.ps1`，或设置 `HEXIN_TOOLS`。

凭据只存在本机，不进仓库：`hexin-db-tools/.env`、`hexin-data-gen/.env`、
`hexin-e2e/.env`、`~/.hexin-tools/projects/<项目ID>/.env`。

## Features

- 项目无关：接口用 `adapter.yaml` 描述，每个项目一份，互不影响
- 当前支持 HTTP JSON 接口 + PostgreSQL；其他数据库需扩 `runtime/db.py`
- 规则本地化：字段、枚举、时序沉淀在 `~/.hexin-tools`，不重复推导
- 缺失即停：没有适配层就转「接入」，不现场猜接口
- 断点续跑：同一批次号重跑只补失败和没跑到的
- 结果校验：`verify` SQL 不通过不计成功
- 写请求不重试：超时不自动重发，避免重复建单
- 台账脱敏：错误信息里的令牌写入前替换
- 跨工具：Claude Code 走插件市场，Cursor / Codex 走生成的规则文件
- 提交前自查：`check_secrets.py` 扫明文凭据、令牌、私钥、私网地址

### FAQ

见 [使用说明 · 常见问题](./docs/usage.md#九常见问题)

## Development

```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe scripts/check_secrets.py
```

目录：

| 路径 | 用途 |
| --- | --- |
| `skills/` | 三个技能的规则文件、契约文档与模板 |
| `runtime/` | 执行引擎：适配层加载、HTTP、台账、校验、数据库 |
| `scripts/` | 命令行入口：`run.py`、`query.py`、`install.py`、`check_secrets.py` |
| `tests/` | 单元测试与本地端到端冒烟 |

旧工具 `hexin-db-tools/`、`hexin-data-gen/`、`hexin-e2e/` 仍在仓库内，用法见各自目录。

## Contributions

Issue 和 PR 都欢迎。提交前请跑一次 `check_secrets.py`。

## Acknowledgement

- [superpowers](https://github.com/obra/superpowers)：技能的组织方式与工作流参考
- [PyYAML](https://github.com/yaml/pyyaml)、[requests](https://github.com/psf/requests)、[psycopg](https://github.com/psycopg/psycopg)、[cryptography](https://github.com/pyca/cryptography)

## License

MIT License. See [LICENSE](./LICENSE) for details.
