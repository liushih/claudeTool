# claudeTool

用白话让 AI 帮你连库、造数、写报告、管代码托管。支持 Claude Code、Cursor、Codex。

业务规则存在本机适配层，凭据只存本机，都不进仓库。

## 能做什么

| 你说 | 它做 |
| --- | --- |
| 查一下 dev 库最近 3 条提货单 | 连库执行 SQL，返回结果 |
| 在 dev 造 100 张提货单，跑到 UPLOADED | 并发造数，逐单记台账 |
| 同一批次重跑，把失败的补上 | 跳过已完成，只补失败 |
| 写这周的周报，顺便出 Word | 采集提交与禅道任务，生成并渲染 |
| 把这个改动提交并推到 dev | 检查提交规范，回显后推送 |
| 接入 XX 新业务 | 陪你跑通，生成该业务的规则和坑库 |

## 快速开始

需要 Windows、Python 3.11+、Git。

**1. 初始化**

```powershell
git clone https://github.com/liushih/claudeTool.git C:\project\claudeTool
cd C:\project\claudeTool
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

建虚拟环境、装依赖，并记录工具目录。

**2. 装进 AI 工具**

Claude Code：

```text
/plugin marketplace add liushih/claudeTool
/plugin install data-tools@data-tools
```

装完重启一次应用。

Cursor / Codex：

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -Target cursor,codex -Scope project -ProjectDir C:\你的业务仓库
```

**3. 接入第一个业务**

新开会话，直接说：

```text
接入 B2D 提货单业务
```

按提示给接口地址、账号即可。接入完成后就能直接说「造 100 张提货单」。

> 插件只分发规则，不带 Python 依赖，所以仓库必须 clone 到本机并跑过 `setup.ps1`。

## 五个技能

| 技能 | 触发词 |
| --- | --- |
| `adapter-bootstrap` 接入业务 | 接入、新业务、第一次、打通 |
| `data-gen-core` 批量造数 | 造 N 条、批量、压测数据、补数据 |
| `db-access` 查改库 | 查一下、连 dev 库、改成、看 redis / mongo |
| `report-writer` 写报告 | 日报、周报、月报、述职 |
| `git-workflow` 代码托管 | 提交、推送、建 MR、开分支、同步热修 |

## 配置

通常不用改。需要时用环境变量覆盖：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DATA_TOOLS_DIR` | `~/.data-tools/config.yaml` 的 `tools_dir` | 工具目录 |
| `DATA_TOOLS_HOME` | `%USERPROFILE%\.data-tools` | 适配层、台账、坑库、凭据 |

每个项目一份独立目录：`~/.data-tools/projects/<项目ID>/`，里面是 `adapter.yaml`、`.env`、`pitfalls.md`。

## 文档

- [使用说明](docs/usage.md)：适配层写法、造数参数、数据库、报告、代码托管、常见问题
- [设计文档](docs/superpowers/specs/) · [实现计划](docs/superpowers/plans/)
- [贡献指南](CONTRIBUTING.md)

## 开发

```powershell
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe scripts/check_secrets.py
```

| 目录 | 用途 |
| --- | --- |
| `skills/` | 技能规则、契约文档、模板 |
| `runtime/` | 执行引擎 |
| `scripts/` | 命令行入口 |
| `hexin-*` | 旧工具，用法见各自目录 |

提交前先读 [CONTRIBUTING.md](CONTRIBUTING.md)：只有通用能力进 git，项目衍生物不进。

## License

MIT，见 [LICENSE](LICENSE)。
