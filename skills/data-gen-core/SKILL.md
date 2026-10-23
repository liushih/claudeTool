---
name: data-gen-core
description: >-
  按项目业务流程批量生成合规测试数据。用户说「造 N 条/张 <业务对象>」
  「批量生成测试数据」「压测数据」「补数据」时使用。执行前必须读取本地适配层；
  没有适配层时必须转 adapter-bootstrap，不允许现场推导。
---

# 批量造数

## 适用场景

- 造数：造、生成、批量、压测数据、补数据
- 用户给出业务对象与数量，例如「造 100 张提货单」

不适用：

- 新业务首次接入 → 先用 `adapter-bootstrap`
- 只查询、不产生数据 → 用 `db-access`

## 前置检查

1. 读 `<数据目录>/projects/<项目ID>/adapter.yaml`
2. `entities` 中存在对应业务对象
3. 同目录 `.env` 含 `envs.dev` 引用的全部变量
4. 确认目标环境；用户未说明时问一次

任一项缺失就停止执行并说明缺什么。
**没有适配层时必须转 `adapter-bootstrap`，不允许现场推导。**

## 执行

```bash
python {{TOOLS_DIR}}/scripts/run.py --project <项目ID> --entity <业务对象> \
  --count <数量> --workers 5 [--run-id <批次号>] [--env dev]
```

- 台账：`<数据目录>/projects/<项目ID>/ledger.csv`
- 断点续跑：同一 `--run-id` 重跑会跳过已完成
- 验证：适配层的 `verify` 段在任务结束后由调用方执行

## 失败处理

| 情况 | 动作 |
|---|---|
| 无 `adapter.yaml` | 停，转 `adapter-bootstrap` |
| 业务对象不存在 | 列出可选项并询问 |
| `.env` 缺键 | 报键名，引导录入 |
| 认证失败 | 指向凭据位置，不盲目重试 |
| 网络超时 | 依赖 runtime 重试 2 次，仍失败则停 |
| 批量部分失败 | 报告 done / failed，给续跑命令，不报成功 |
