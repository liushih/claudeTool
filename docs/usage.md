# 使用说明

面向日常使用者。装好之后，日常只需要用白话触发，不需要手写命令。

- [一、四个技能怎么选](#一四个技能怎么选)
- [二、第一次接入业务](#二第一次接入业务)
- [三、适配层写法](#三适配层写法)
- [四、批量造数](#四批量造数)
- [五、结果校验](#五结果校验)
- [六、数据库访问](#六数据库访问)
- [七、坑库](#七坑库)
- [八、配置与路径](#八配置与路径)
- [九、常见问题](#九常见问题)
- [十、写报告](#十写报告)

---

## 一、四个技能怎么选

| 意图 | 说法 | 技能 |
|---|---|---|
| 造数 | 造、生成、批量、压测数据、补数据、跑一批 | `data-gen-core` |
| 连库 | 查库、查一下、连、SQL、改数据 | `db-access` |
| 接入 | 接入、新业务、第一次、打通、适配 | `adapter-bootstrap` |
| 报告 | 日报、周报、月报、述职、汇报材料 | `report-writer` |
| 沉淀 | 记下来、加到坑里、更新规则 | 写 `pitfalls.md` |

同时命中多个时按这个顺序：

1. 含「接入 / 新业务」→ 走接入，即使同时提到造数
2. 含「日报 / 周报 / 月报 / 述职」→ 写报告
3. 有造数动词且带业务名词 → 批量造数
4. 只有动词没有名词（「造点数据」）→ 追问是哪个业务
5. 有 SQL 关键字或表名 → 数据库访问
6. 都不命中 → 直说没听懂，不猜

## 二、第一次接入业务

### 先准备什么

接入前需要两套账号，都放在项目目录的 `.env` 里，不进仓库：

| 配置 | 用途 | 必需 | 权限 |
| --- | --- | --- | --- |
| 系统登录账号 | 调接口造数 | 是 | 能执行目标业务操作即可 |
| 数据库连接 | `verify` 校验结果 | 否 | 只读 |

`.env` 的键名可以自己定，只要 `adapter.yaml` 里引用的 `${VAR}` 对得上。典型内容：

```dotenv
# 接口
ACME_BASE_URL=
ACME_USERNAME=
ACME_PASSWORD=

# 数据库：DEV 对应 adapter 里 envs.dev.db_prefix
DEV_HOST=
DEV_PORT=
DEV_USER=
DEV_PASSWORD=
```

`db_prefix: DEV` 会拼出 `DEV_HOST` / `DEV_PORT` / `DEV_USER` / `DEV_PASSWORD`；
test、prod 环境同理换成 `TEST_` / `PROD_`。

两点建议：

- 接口账号用目标环境（dev/test）的，别拿生产账号造数
- 数据库账号给只读，`verify` 只查不写；生产环境尤其不要带写权限

数据库可以先不配。没有它照样能造数，只是 `verify` 段不生效，只能确认流程走完，
确认不了数据最终状态。

### 接入流程

新业务第一次造数前，必须先有适配层。直接说「接入 XX 业务」即可，技能会：

1. 确认项目 ID 与数据目录
2. 收集接口地址、认证方式、目标状态
3. 逐项确认字段映射、枚举取值、异步时序
4. 起草 `adapter.yaml`，先跑 1 条
5. 失败就查接口或问你，不猜字段
6. 跑通后补 `verify` 段
7. 把踩到的坑写进 `pitfalls.md`

产出都在本机：

```
%USERPROFILE%\.data-tools\projects\<项目ID>\
├── adapter.yaml      业务规则
├── .env              接口地址与账号（不进 git）
├── pitfalls.md       踩坑记录
├── scripts\          需要代码才能做的步骤
└── ledger.csv        运行台账（第一次跑数后生成）
```

接入完成后，之后每次造数都直接复用这份规则。

## 三、适配层写法

### 顶层结构

```yaml
version: 1
project: hexincloud

envs:
  dev:
    base_url: ${HEXIN_BASE_URL}   # 值只写在同目录 .env
    db_prefix: DEV                # 对应 .env 的 DEV_HOST / DEV_PORT / ...
    database: hexin_wms           # 校验时连的库

auth:
  type: none                      # none | custom

entities:
  b2d_pickup_order:
    description: B2D 提货单
    stop_at: UPLOADED
    id_rule: "PB{run_id}{idx:04d}"
    steps:
      - id: create
        call: POST /order/create
        body:
          "externalNo": ${ctx.external_no}
      - id: wait_packages
        poll: GET /order/status
        until: "resp.get('customsMode') != None"
        timeout: 60
    verify:
      sql: "select status from t where no = %(no)s"
      expect: UPLOADED
```

### 步骤的三种类型

`call`、`poll`、`impl` 必须且只能有一个。

| 类型 | 行为 | 失败条件 |
|---|---|---|
| `call` | 发一次请求，结果存进 `ctx.values[<id>]` | HTTP ≥ 400，或网络重试耗尽 |
| `poll` | 循环请求直到 `until` 为真 | 超过 `timeout` 秒 |
| `impl` | 调 `<项目目录>/<文件>:<函数>`，函数签名 `func(ctx, None)` | 文件或函数不存在、函数抛错 |

`until` 是 Python 表达式，可用 `resp` 和 `ctx`。

### 变量替换

| 写法 | 含义 |
|---|---|
| `${ctx.external_no}` | 当前单号 |
| `${prev.create.orderId}` | 某一步的产出字段 |

整个字符串就是一个引用时保留原类型（数字、对象）；否则按字符串拼接。

`body` / `params` 的键名要加引号。YAML 会把 `no`、`yes`、`on`、`off` 解析成布尔，
写成 `no:` 实际是 `false:`，加载时会直接报错提示。

`before` 列出的步骤必须在同一个 `entities` 下先声明，且只会执行一次。

完整的字段表见 `skills/_references/adapter-contract.md`，模板见
`skills/_TEMPLATE/adapter.example.yaml`。

## 四、批量造数

```bash
.venv/Scripts/python.exe scripts/run.py --project hexincloud --entity b2d_pickup_order \
  --count 100 --workers 5 --run-id 1026a
```

| 参数 | 说明 |
|---|---|
| `--count` | 数量，默认 1 |
| `--workers` | 并发数，默认 1 |
| `--run-id` | 批次号；不填按时间生成，例如 `1026114054` |
| `--env` | 环境，默认 `dev` |

### 台账

每次运行往 `<项目目录>\ledger.csv` 追加：

```
run_id,idx,external_no,stage,status,error,updated_at
1026a,0,PB1026a0000,chain,done,,2026-10-26 11:43:55
```

- `stage` 是失败时停留的步骤名
- `error` 写入前会脱敏，令牌不会落盘

### 断点续跑

用同一个 `--run-id` 重跑，`status=done` 的单会被跳过，只补失败和没跑到的。

```bash
.venv/Scripts/python.exe scripts/run.py --project hexincloud --entity b2d_pickup_order \
  --count 100 --workers 5 --run-id 1026a
```

### 失败处理

- 单条失败不影响其他单，退出码为 1
- 写请求（POST/PUT）超时不重试，避免重复建单
- 读请求超时自动重试 2 次
- 业务接口报错时，先查 `pitfalls.md` 有没有同现象

## 五、结果校验

适配层里写 `verify`，`run.py` 每单跑完自动执行：

```yaml
verify:
  sql: "select status from t where no = %(no)s"
  expect: UPLOADED
```

- 占位符用 `%(no)s`，值是单号
- 结果与 `expect` 不一致 → 这单记为 failed
- 没写 `verify` 就不会校验，只按流程是否走完记 done

数据库连接用 `envs.<环境>` 的 `db_prefix`（找 `.env` 里的 `DEV_HOST` 等）
和 `database`。校验跑在项目自己的 `.env` 上，与 `hexin-db-tools/.env` 无关。

## 六、数据库访问

```bash
.venv/Scripts/python.exe scripts/query.py --project hexincloud --env dev \
  --sql "select delivery_no, delivery_status from wms_delivery_order order by id desc limit 3"
```

带参数时用 `%(name)s` 配合 `--param`，不要拼字符串：

```bash
.venv/Scripts/python.exe scripts/query.py --project hexincloud --env dev \
  --sql "select status from t where external_order_no = %(no)s" --param no=PB1026114338
```

规则：

- 只读（`select`）直接执行
- 写操作先回显环境、库、SQL，回显后直接执行，不再二次确认
- `DROP` / `TRUNCATE` / 无 `WHERE` 的 `DELETE` 额外打印一行警示
- 影响行数为 0 会明确报告，不当作成功
- 不自动提交事务

命令行要跟一句「只读」或「可以写」，权限完全按你的口令走。

## 七、坑库

`pitfalls.md` 只追加，不删除。每条四段：

```markdown
### P1 建单前必须先取 stageToken

- 现象：直接传 items 建单，返回「工作区已过期」
- 原因：建单前必须先调 item-stage/items 获取 stageToken
- 绕法：先取 token，再带 token 提交 items
- 适用：create 步骤
```

什么时候写：

- 某次运行失败，查明原因并绕过之后
- 发现了枚举取值、异步时序这类不明显的行为
- 用户说「记下来」

写入前先读现有条目，按「现象」去重。下次造同类数据时，技能会先读这份坑库，不重复试错。

## 八、配置与路径

**工具包**

| 变量 | 默认值 | 说明 |
|---|---|---|
| `DATA_TOOLS_DIR` | `~/.data-tools/config.yaml` 的 `tools_dir` | 技能定位执行入口 |
| `DATA_TOOLS_HOME` | `%USERPROFILE%\.data-tools` | 适配层、台账、坑库、凭据 |

**旧工具（`hexin-db-tools/`、`hexin-data-gen/`、`hexin-e2e/`）**

| 变量 | 默认值 | 说明 |
|---|---|---|
| `HEXIN_REPO` | `..\hexincloud` | 业务主仓库位置 |
| `HEXIN_DB_ENV` | `hexin-db-tools\.env` | 三环境库账号文件 |
| `HEXIN_SKILL_SCRIPTS` | `$HEXIN_REPO\dev-overlay\...\scripts` | 飞书台账脚本 |
| `PW_PROFILE` | `..\pw-profile` | 浏览器登录态 |

`setup.ps1` 会把仓库路径写进 `config.yaml`。仓库换位置后重跑一次 `setup.ps1`，
或者设置 `DATA_TOOLS_DIR`。

## 九、常见问题

**技能装好了但列表里没有**

Claude Code 的插件内容在启动时加载。装完或更新后重启一次应用。
仍然没有时检查 `%USERPROFILE%\.claude\plugins\installed_plugins.json` 里有没有
`data-tools@data-tools`，以及 `cache\data-tools\data-tools\<版本>\` 目录是否存在。

**改了技能规则但不生效**

同上，重启后才会读到新内容。

**提示 No module named 'xxx'**

先跑一次 `setup.ps1`，或手动 `pip install -r requirements.txt`。
插件缓存里没有虚拟环境，依赖装在 clone 下来的仓库里。

**提示找不到工具目录**

检查 `%USERPROFILE%\.data-tools\config.yaml` 的 `tools_dir`，或设置 `DATA_TOOLS_DIR`。

**业务接口报 token 无效**

删掉 `hexin-data-gen\.token.json` 后重跑，会重新登录。

**返回「未定义变量 X」**

适配层里用了 `${X}`，但同目录 `.env` 没有 `X`。补上或改正名字。

**返回「含非字符串键」**

YAML 把 `no` / `yes` / `on` / `off` 解析成了布尔。给键加引号，写成 `"no":`。

**批量跑完一半失败**

用同一个 `--run-id` 重跑，已完成的不再重复。

**数据库连不上**

`db-access` 用的是项目目录下的 `.env`，需要 `DEV_HOST` / `DEV_PORT` /
`DEV_USER` / `DEV_PASSWORD`（对应环境是 TEST_ / PROD_）。这些跟
`hexin-db-tools/.env` 是两套文件，不会自动同步。

**提交前自查敏感信息**

```bash
.venv/Scripts/python.exe scripts/check_secrets.py
```

只扫已跟踪文件，检查明文凭据、GitHub 令牌、私钥和私网地址。

## 十、写报告

### 说法与类型

| 类型 | 说法 | 时间范围 |
|---|---|---|
| 日报 | 写今天的日报 | 当天 |
| 周报 | 出本周周报 | 周一至周日 |
| 月报 | 写这个月的月报 | 自然月 |
| 述职 | 生成 Q3 述职 | 你指定 |

四种报告各自从原始数据生成，周报不汇总日报，月报不汇总周报。

### 生成前会问什么

1. **项目**：你说了就用；没说就按当前工作目录匹配；对不上或命中多个会问，不猜
2. **受众**：直属领导（默认）/ 更高层 / 自己留痕 / 团队共享。选择记在
   `reports/<项目ID>/.audience`，下次直接回车沿用
3. **角色**（述职必问）：开发 / 测试 / 产品 / 其他。记在 `reports/<项目ID>/.role`，
   当次口头指定优先于记忆值
4. **补充**：先报数据（几个提交、几个任务、几个 Bug），再问「有什么没体现在提交和工单里的」

受众决定语气，角色决定重点：

| 角色 | 重点 | 指标 |
|---|---|---|
| 开发 | 交付、质量、技术债 | 提交、修复 Bug、线上问题 |
| 测试 | 覆盖、缺陷拦截、质量门禁 | 发现 Bug、用例覆盖、漏测 |
| 产品 | 需求价值、上线节奏、用户指标 | 需求交付数、验收通过率 |

角色只影响写法。测试角色关心的「我发现的 Bug」目前采集不到，写述职时会向你要，
或者明确标注「本次未统计发现类缺陷」。真要自动采集，需要按角色扩展禅道查询。

### 配置

`~/.data-tools/projects/<项目ID>/report.yaml`：

```yaml
git:
  repos:
    - C:/project/hexincloud
  authors:
    - me@example.com
zentao:
  api: auto          # auto | v1 | v2，当前实现 v2
  base_url: ${ZENTAO_URL}
  account: ${ZENTAO_ACCOUNT}
  product_id: 31
  project_ids: [73]
```

凭据写在同目录 `.env`，与适配层共用。禅道 token 缓存在 `~/.zentao-token.json`，
登录一次后复用。

### 报告存在哪

```
~/.data-tools/reports/<项目ID>/
├── 2026-10-26-daily.md
├── 2026-W44-weekly.md
├── 2026-10-monthly.md
└── 2026-Q3-review.pptx
```

按周期命名，同一周期重跑直接覆盖。汇总数据临时放在同目录 `.collect/` 下。

### 输出 Word / PPT

Markdown 是唯一内容源，Word 和 PPT 都从它渲染：

```bash
.venv/Scripts/python.exe scripts/render.py --input <md> --format docx,pptx --out-dir <目录>
```

### 模板

`~/.data-tools/templates/<项目ID>/<类型>.md`，只定义章节和提示语：

```markdown
## 本周完成
<!-- 写结果，不写过程；按业务主题分组 -->

## 数据支撑
<!-- 提交数、完成任务数、修复 bug 数 -->
```

没有模板时用内置结构：日报「今日完成 / 明日计划 / 风险」，周报「本周完成 / 关键数据 /
问题与风险 / 下周计划」，月报「目标达成 / 关键成果 / 问题与改进 / 下月重点」，
述职「成果 / 问题与反思 / 规划」。

### 数据缺失

禅道连不上或未授权时，报告仍然生成，但开头会写「禅道数据缺失，本次仅基于代码提交」。
某个仓库路径不存在时同样跳过并提示，不会静默少一块。
