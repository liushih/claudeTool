# 适配层契约（adapter.yaml）

位置：`<数据目录>/projects/<项目ID>/adapter.yaml`，同目录 `.env` 提供值。

## 顶层字段

| 字段 | 必填 | 说明 |
|---|---|---|
| `version` | 是 | 当前只接受 `1` |
| `project` | 否 | 项目标识，缺省用目录名 |
| `envs` | 是 | 环境 → `{ base_url, db_prefix, database? }` |
| `auth` | 否 | `{ type: none \| custom, impl? }` |
| `entities` | 是 | 业务对象 → 定义，不能为空 |
| `pitfalls` | 否 | 坑列表，也可放同目录 `pitfalls.md` |

## entity

| 字段 | 必填 | 说明 |
|---|---|---|
| `description` | 否 | 业务名称 |
| `stop_at` | 否 | 目标状态 |
| `id_rule` | 否 | 幂等键模板，可用 `{run_id}` `{idx:04d}` |
| `steps` | 是 | 至少一步 |
| `verify` | 否 | `{ sql, expect }`，执行后校验 |

## step

`call`、`poll`、`impl` 三者**必须且只能有一个**。

| 字段 | 说明 |
|---|---|
| `id` | 步骤名，产出写入 `ctx.values[<id>]` |
| `call` | `"POST /path"` 或 `"GET /path"` |
| `poll` | 同上，循环直到 `until` 为真 |
| `until` | **Python 表达式**，可用 `resp`（响应）与 `ctx`（上下文） |
| `timeout` | 轮询超时秒数，默认 60 |
| `before` | 先执行的步骤 id 列表 |
| `impl` | `"scripts/x.py:func"`，调用 `func(ctx, None)` |
| `body` | 请求体，支持 `${ctx.xxx}` 与 `${prev.<step>.<field>}` |
| `params` | 查询参数，替换规则同 `body` |

## 四条规则

1. 只写结构，值一律 `${VAR}`；值只来自同目录 `.env`
2. `pitfalls.md` 只追加，条目带 `id`
3. 所有文件带 `version`，便于迁移
4. 声明式优先，表达不了才写 `impl`

## 示例

见 `skills/_TEMPLATE/adapter.example.yaml`。
