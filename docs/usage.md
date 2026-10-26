# 使用说明

面向日常使用者。装好之后，日常只需要用白话触发，不需要手写命令。

- [一、三个技能怎么选](#一三个技能怎么选)
- [二、第一次接入业务](#二第一次接入业务)
- [三、适配层写法](#三适配层写法)
- [四、批量造数](#四批量造数)
- [五、结果校验](#五结果校验)
- [六、数据库访问](#六数据库访问)
- [七、坑库](#七坑库)
- [八、配置与路径](#八配置与路径)
- [九、常见问题](#九常见问题)

---

## 一、三个技能怎么选

| 意图 | 说法 | 技能 |
|---|---|---|
| 造数 | 造、生成、批量、压测数据、补数据、跑一批 | `data-gen-core` |
| 连库 | 查库、查一下、连、SQL、改数据 | `db-access` |
| 接入 | 接入、新业务、第一次、打通、适配 | `adapter-bootstrap` |
| 沉淀 | 记下来、加到坑里、更新规则 | 写 `pitfalls.md` |

同时命中多个时按这个顺序：

1. 含「接入 / 新业务」→ 走接入，即使同时提到造数
2. 有造数动词且带业务名词 → 批量造数
3. 只有动词没有名词（「造点数据」）→ 追问是哪个业务
4. 有 SQL 关键字或表名 → 数据库访问
5. 都不命中 → 直说没听懂，不猜

## 二、第一次接入业务

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
%USERPROFILE%\.hexin-tools\projects\<项目ID>\
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

| 变量 | 默认值 | 说明 |
|---|---|---|
| `HEXIN_TOOLS` | `~/.hexin-tools/config.yaml` 的 `tools_dir` | 技能定位执行入口 |
| `HEXIN_DATA_HOME` | `%USERPROFILE%\.hexin-tools` | 适配层、台账、坑库、凭据 |
| `HEXIN_REPO` | `..\hexincloud` | 业务主仓库位置 |
| `HEXIN_DB_ENV` | `hexin-db-tools\.env` | 三环境库账号文件 |
| `HEXIN_SKILL_SCRIPTS` | `$HEXIN_REPO\dev-overlay\...\scripts` | 飞书台账脚本 |
| `PW_PROFILE` | `..\pw-profile` | 浏览器登录态 |

`setup.ps1` 会把仓库路径写进 `config.yaml`。仓库换位置后重跑一次 `setup.ps1`，
或者设置 `HEXIN_TOOLS`。

## 九、常见问题

**技能装好了但列表里没有**

Claude Code 的插件内容在启动时加载。装完或更新后重启一次应用。
仍然没有时检查 `%USERPROFILE%\.claude\plugins\installed_plugins.json` 里有没有
`hexin-tools@hexin-tools`，以及 `cache\hexin-tools\hexin-tools\<版本>\` 目录是否存在。

**改了技能规则但不生效**

同上，重启后才会读到新内容。

**提示 No module named 'xxx'**

先跑一次 `setup.ps1`，或手动 `pip install -r requirements.txt`。
插件缓存里没有虚拟环境，依赖装在 clone 下来的仓库里。

**提示找不到工具目录**

检查 `%USERPROFILE%\.hexin-tools\config.yaml` 的 `tools_dir`，或设置 `HEXIN_TOOLS`。

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
