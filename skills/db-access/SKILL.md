---
name: db-access
description: >-
  用自然语言查询或修改数据库、Redis、MongoDB。用户说「查一下」「连 dev 库」
  「把 X 改成 Y」「看下 redis 的 key」「查 mongo 里的日志」时使用。
  写操作前回显环境与命令，回显不阻塞执行。
---

# 数据库访问

## 适用场景

- SQL：查、查一下、连、SQL、select、count
- 修改数据：改、更新、删除、insert、update、delete
- Redis：缓存、key、redis、hash、GET/SET
- MongoDB：mongo、集合、文档、find、aggregate

## 前置检查

1. 读适配层的 `envs.<环境>` 与同目录 `.env`
2. 确认目标环境（dev / test / prod）；用户未说明时问一次
3. 确认存储类型（PostgreSQL / Redis / MongoDB）；用户说法不明确时问一次
4. 写操作前回显：环境、库或集合、命令、预计影响范围

## 路径

命令里的 `<TOOLS_DIR>` 是工具仓库根目录，按顺序确定：环境变量 `DATA_TOOLS_DIR` → `~/.data-tools/config.yaml` 的 `tools_dir` → 问用户仓库在哪，不要猜。通过 `install.ps1` 渲染安装时命令里已是绝对路径，可跳过。

解释器优先用仓库内 `.venv/Scripts/python.exe`；不存在时用 `python`，并先 `pip install -r requirements.txt`。

## 执行

**PostgreSQL**

```bash
"<TOOLS_DIR>/.venv/Scripts/python.exe" "<TOOLS_DIR>/scripts/query.py" \
  --project <项目ID> --env dev \
  --sql "select status from wms_order where external_order_no = %(no)s" --param no=<单号>
```

**Redis**

```bash
"<TOOLS_DIR>/.venv/Scripts/python.exe" "<TOOLS_DIR>/scripts/redis.py" \
  --project <项目ID> --env dev --cmd "GET user:1"
```

**MongoDB**

```bash
"<TOOLS_DIR>/.venv/Scripts/python.exe" "<TOOLS_DIR>/scripts/mongo.py" \
  --project <项目ID> --env dev --collection logs --find '{"level": "error"}' --limit 20
```

规则（三种存储通用）：

- 只读：`select`、`GET`/`SCAN`/`HGETALL`、`find`/`aggregate`/`count` 直接执行并返回结果
- 写入：回显后直接执行，不再二次确认
- 破坏性操作（`DROP` / `TRUNCATE` / 无 `WHERE` 的 `DELETE` / `FLUSHDB` / `FLUSHALL` /
  无 filter 的 `delete many`）：额外打印一行警示后照常执行
- SQL 占位符用 `%(name)s`，配合 `--param name=value`；不要拼字符串
- Redis 命令用引号整体传入，如 `--cmd "SET k v"`
- Mongo 参数是 JSON：`--find` 传过滤条件，`--aggregate` 传管道数组，
  `--update` 传 `{"filter": {...}, "update": {...}, "many": true}`
- 连接参数只来自 `.env`，不要在命令行明文传密码
- 不自动提交事务，除非用户明确要求

## 失败处理

| 情况 | 动作 |
|---|---|
| 缺连接配置 | 报键名，引导录入 |
| 连接失败 | 报环境与变量名，不打印密码 |
| SQL 报错 | 原样返回错误，不猜测改写 |
| 影响行数为 0 | 明确报告 0 行，不当作写入成功 |
| 环境未配置 `redis_prefix` / `mongo_prefix` | 报缺的字段名，不尝试默认地址 |
| Redis 返回 nil | 明确说「key 不存在」，不当作空字符串 |

