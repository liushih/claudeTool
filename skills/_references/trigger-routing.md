# 触发词路由

四个 skill 的 frontmatter 都引用本表。判断顺序：命中即停。

| 意图 | 中文触发 | 英文触发 | 目标 skill |
|---|---|---|---|
| 造数 | 造、生成、批量、压测数据、补数据、跑一批 | generate, seed, batch, mock | `data-gen-core` |
| 连库 | 查库、查一下、连、SQL、改数据、只读 | query, select, connect, update | `db-access` |
| 接入 | 接入、新业务、第一次、打通、适配 | onboard, integrate, wire up | `adapter-bootstrap` |
| 报告 | 日报、周报、月报、述职、汇报材料 | daily, weekly, monthly, review, report | `report-writer` |
| 沉淀 | 记下来、加到坑里、更新规则 | remember, add pitfall | 写 `pitfalls.md` |

## 消歧顺序

1. 含「新业务 / 接入」→ `adapter-bootstrap`（即使同时含造数）
2. 含「日报 / 周报 / 月报 / 述职」→ `report-writer`
3. 含造数动词且带业务名词 → `data-gen-core`
4. 只有动词没有名词（「造点数据」）→ 询问是哪个业务
5. 含 SQL 关键字或表名 → `db-access`
6. 都不命中 → 直说没听懂，不猜

## 约束

- 触发词必须带领域名词或明确动词
- `连接` 这类泛词单独出现不触发
- 同一句话命中多个时，按上面的顺序，不并列执行
