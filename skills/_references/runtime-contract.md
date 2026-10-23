# runtime 契约

`scripts/run.py` 读取 `adapter.yaml`，按 entity 的 steps 顺序执行。

## 步骤语义

| 类型 | 行为 | 失败条件 |
|---|---|---|
| `call` | 替换变量后发出一次请求，结果存 `values[id]` | HTTP ≥ 400，或网络重试耗尽 |
| `poll` | 循环请求，直到 `until` 表达式为真 | 超过 `timeout` 秒 |
| `impl` | 加载 `<数据目录>/projects/<项目ID>/<路径>`，调用 `func(ctx, None)` | 文件或函数不存在，或函数抛错 |

## 变量替换

- `${ctx.external_no}`：取上下文字段
- `${prev.create.orderId}`：取指定步骤的产出字段
- 整个字符串就是一个引用时，保留原始类型（数字、对象）；否则按字符串拼接

## 批量

- `--count` 目标数量，`--workers` 并发数
- 分片规则：`todo[i::workers]`
- 每完成或失败写一行台账；同一 `--run-id` 重跑会跳过 `status=done`
- 单条失败不影响其它单，退出码为 1

## 上下文

```python
{"external_no": "...", "values": {"create": {...}}, "stage": "create"}
```

`stage` 在每步完成后更新，失败时用于定位。

## 不做的事

- 不自动提交数据库事务
- 不自动补偿失败步骤
- 不判断业务数据是否合理
