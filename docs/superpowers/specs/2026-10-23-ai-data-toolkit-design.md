# AI 数据工具包 设计稿

日期：2026-10-23
状态：待评审

## 1. 目标

一套可分发的能力包，让用户用白话触发数据库操作与业务数据生成，并且规则随使用累积、不重复推导。

成功标准：

1. 新机器安装后，说「连 dev 库查最近 10 条提货单」能直接出结果
2. 说「造 100 张提货单」能跑，中断后可用同一批次号续跑
3. 同类任务第二次执行时，需要人工回答的内容不超过第一次的 20%
4. 仓库内无密码、内网地址、人员姓名
5. 同一句话在 Claude / Cursor / Codex 中均可触发

## 2. 范围

三个能力域，共用同一份项目上下文：

| 能力域 | 触发场景 | 职责 |
|---|---|---|
| `db-access` | 连库查询、改数据 | 建立连接、生成并执行 SQL、回显 |
| `data-gen` | 批量造业务数据 | 按适配层声明的业务链批量执行 |
| `adapter-bootstrap` | 新业务首次接入 | 边跑边记，产出或更新本地适配层 |

不做：

- 不判断业务数据是否合理，只保证调用成功、状态到达目标值
- 不替用户决定走接口还是 SQL
- 不涉及发布流程
- 不做跨项目数据迁移
- **不纳入浏览器操作**（后续按需扩展）

硬原则：适配层缺失时 `data-gen` 必须停下转 bootstrap，不允许现场推导。

## 3. 三层结构与位置

| 层 | 位置 | 进 git | 内容 |
|---|---|---|---|
| 规则与引擎 | `C:\project\claudeTool` | 是（公开/私有仓库） | skill 源文件、通用 runtime、安装脚本 |
| 业务代码 | 目标业务仓库 | 是（公司仓库） | 只放生成的工具入口文件，不放工具实现 |
| 项目适配 | `%USERPROFILE%\.hexin-tools\projects\<项目ID>` | 否 | adapter.yaml、项目脚本、坑、凭据 |

判定标准：代码中出现该项目的接口路径、字段名、枚举 → 项目层；只涉及循环、并发、记账、重试 → 引擎层。

`HEXIN_DATA_HOME` 可覆盖本地根目录。

## 4. 仓库结构

```
claudeTool/
  runtime/
    runner.py         批量执行：并发、台账、断点续跑、按 adapter 驱动
    ledger.py         CSV 台账读写
    http_client.py    请求、重试、超时
    verify.py         按 adapter 的 verify 段校验
  skills/
    data-gen-core/SKILL.md
    db-access/SKILL.md
    adapter-bootstrap/SKILL.md
    _references/
      adapter-contract.md    适配层字段定义
      runtime-contract.md    adapter 如何驱动 runtime
      trigger-routing.md     白话 → 意图路由
      pitfalls.md            通用坑库
    _TEMPLATE/
      adapter.example.yaml
      pitfalls.example.md
      env.example
  scripts/
    install.py        生成 Claude / Cursor / Codex 适配文件
    check_secrets.py  提交前扫描
  install.ps1         包装 install.py
```

## 5. 本地结构

```
%USERPROFILE%\.hexin-tools\
  config.yaml                 默认项目、默认环境
  projects\<项目ID>\
    adapter.yaml              业务链声明
    pitfalls.md               该项目踩的坑
    .env                      凭据
    scripts\                  项目特有脚本
    tmp\                      一次性探针，可清空
```

## 6. adapter.yaml 契约

YAML 格式，配套 `adapter.example.yaml` 逐字段注释。

```yaml
version: 1
project: <项目ID>

envs:
  dev:
    base_url: ${HEXIN_BASE_URL}
    db_prefix: DEV
  test:
    base_url: ${HEXIN_BASE_URL_TEST}
    db_prefix: TEST

auth:
  type: aes_rsa            # none | bearer | aes_rsa | custom
  login: POST /auth/login
  impl: scripts/auth_hexin.py

entities:
  <entity_id>:
    description: <业务名称>
    stop_at: <目标状态>
    id_rule: "<幂等键模板>"
    steps:
      - id: fetch_stage_token
        call: GET /item-stage/items
      - id: create
        call: POST /path
        before: [fetch_stage_token]
      - id: wait_packages
        poll: GET /path
        until: "field != null"
        timeout: 60
      - id: custom
        impl: scripts/chain.py:func
    verify:
      sql: "select status from t where no = :no"
      expect: <目标值>

pitfalls:
  - id: P1
    applies_to: [create]
    summary: <一句话>
```

四条规则：

1. 只写结构，值一律 `${VAR}`，值只来自同目录 `.env`
2. `pitfalls.md` 只追加，条目带 id，供 skill 引用
3. 所有文件带 `version`，便于迁移
4. 声明式优先；表达不了的步骤用 `impl:` 引用项目脚本

## 7. 触发词路由

| 意图 | 中文触发 | 英文触发 | 目标 |
|---|---|---|---|
| 造数 | 造、生成、批量、压测数据、补数据 | generate, seed, batch, mock | data-gen |
| 连库 | 查库、连、SQL、改数据、只读 | query, select, connect, update | db-access |
| 接入 | 接入、新业务、第一次、打通 | onboard, integrate | adapter-bootstrap |
| 沉淀 | 记下来、加到坑里 | remember, add pitfall | 写 pitfalls |

消歧顺序（命中即停）：

1. 含「新业务/接入」→ bootstrap
2. 含造数动词且带业务名词 → data-gen
3. 只有动词无名词 → 询问业务
4. 含 SQL 关键字或表名 → db-access
5. 都不命中 → 直说没听懂，不猜

触发词必须带领域名词或明确动词，`连接` 这类泛词单独出现不触发。

## 8. 权限与安全

写操作流程：判断环境 → 未指明则问一次 → 生成 SQL 并回显（环境/库/语句/预计行数）→ 直接执行 → 返回影响行数。

回显不阻塞口令。危险语句（DROP / TRUNCATE / 无 WHERE 的 DELETE）额外打印警示后照常执行。

凭据：

- 用户口述 → AI 写入 `projects/<id>/.env`
- AI 不把值打印回来，只确认写入的键
- 换项目各自一份；轮换只改一处
- 口述的密码会留在本地会话记录中，敏感凭据建议用完轮换

仓库零敏感三道防线：

1. `.gitignore`：`.env`、`*.local.yaml`、`projects/`、`*.token.json`
2. `check_secrets.py` 扫描密码模式、token 前缀、私钥块、内网 IP
3. 可选 pre-commit hook

## 9. 跨工具生成

一份正文，三种 frontmatter。正文为纯 markdown，不含工具专有语法。

| 工具 | 生成位置 | 内容 |
|---|---|---|
| Claude | `~/.claude/skills/<name>/SKILL.md` | 正文 + name / description |
| Cursor | `<目标仓库>/.cursor/rules/<name>.mdc` | 正文 + description / globs / alwaysApply |
| Codex | `<目标仓库>/AGENTS.md` 托管块 | 索引 + 指向 references 的路径 |

命令：

```bash
python scripts/install.py --target claude,cursor,codex --scope global
python scripts/install.py --target cursor,codex --scope project --project-dir <仓库>
python scripts/install.py --remove
```

工程约束：

1. 幂等：生成文件带版本头；AGENTS.md 用 begin/end 托管块
2. 生成文件禁止手改，改源文件后重跑
3. 正文中的 `{{TOOLS_DIR}}` 安装时替换，仓库不出现绝对路径

## 10. 沉淀闭环

| 沉淀物 | 位置 | 写入条件 |
|---|---|---|
| 业务链 | `adapter.yaml` | 跑通一次 |
| 项目坑 | `projects/<id>/pitfalls.md` | 失败修复后立即追加 |
| 通用坑 | 仓库 `_references/pitfalls.md` | 跨 2 个项目复现，人工确认后 |

坑的固定四段：现象、原因、绕法、适用步骤。追加前按 summary 去重。

通用坑自动上提不允许，因为仓库对外发布。

## 11. 失败处理

| 情况 | 动作 |
|---|---|
| 无 adapter.yaml | 停，转 bootstrap |
| 适配层缺字段 | 停，指出字段 |
| .env 缺键 | 停，引导录入 |
| 认证失败 | 报错并指向凭据位置，不盲目重试 |
| 业务接口报错 | 先查 pitfalls，无匹配则记录并询问 |
| 网络超时 | 读请求自动重试 2 次后停；写请求不重试 |
| 批量部分失败 | 记台账、给续跑命令，不报成功 |

三条底线：写失败不自动补偿；不静默重试写请求；不把「跑完了」当「跑对了」。

## 12. 验证与试点

| # | 验证 |
|---|---|
| 1 | 干净环境安装后查询 dev 库 |
| 2 | 批量造数后中断续跑 |
| 3 | 第二次执行统计人工输入量 |
| 4 | check_secrets.py 通过 |
| 5 | Cursor / Codex 各自触发一次 |

试点三阶段：抽象现有造数工具为 core + 适配层并在 Claude 跑通 → 生成 Cursor/Codex 规则验证触发 → 选一条新业务走 bootstrap 验证第二次不问细节。

不在 prod 验证。

## 13. 决策记录

| 决策 | 结论 | 依据 |
|---|---|---|
| 数据库写权限 | 完全听用户口令 | 用户明确选择 |
| 适配层位置 | 本地，不进 git | 仓库零业务信息 |
| 凭据录入 | 用户口述，AI 写文件 | 用户明确选择 |
| 适配层生成 | 边跑边记 | 纯读代码推不准异步/枚举 |
| 安装形态 | 仓库 + 安装脚本 | 跨工具、离线可用 |
| 适配层格式 | YAML + 注释齐全的示例 | 结构与可读性平衡 |
| 浏览器操作 | 暂不纳入 | 当前接口链路够用 |
| 与内部技能体系合并 | 不合并，保持独立 | 本包需对外分发 |
