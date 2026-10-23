---
name: db-access
description: >-
  用自然语言查询或修改数据库。用户说「查一下」「连 dev 库」「把 X 改成 Y」
  「执行这条 SQL」时使用。写入前回显 SQL 与环境，回显不阻塞执行。
---

# 数据库访问

## 适用场景

- 连库查询：查、查一下、连、SQL、select、count
- 修改数据：改、更新、删除、insert、update、delete

## 前置检查

1. 读适配层的 `envs.<环境>` 与同目录 `.env`
2. 确认目标环境（dev / test / prod）；用户未说明时问一次
3. 写操作前回显：环境、库、SQL、预计影响行数

## 路径

`{{TOOLS_DIR}}` 是工具仓库根目录。Claude 插件安装时改用 `${CLAUDE_PLUGIN_ROOT}`；Cursor / Codex 由 `install.ps1` 渲染成本机绝对路径。

## 执行

```bash
python {{TOOLS_DIR}}/scripts/query.py --project <项目ID> --env dev \
  --sql "select status from wms_order where external_order_no = %(no)s" --param no=<单号>
```

- 只读：`select` 直接执行并返回结果
- 写入：回显后直接执行，不再二次确认
- `DROP` / `TRUNCATE` / 无 `WHERE` 的 `DELETE`：额外打印一行警示后照常执行
- 占位符用 `%(name)s`，配合 `--param name=value`；不要拼字符串
- 连接参数只来自 `.env`，不要在命令行明文传密码
- 不自动提交事务，除非用户明确要求

## 失败处理

| 情况 | 动作 |
|---|---|
| 缺连接配置 | 报键名，引导录入 |
| 连接失败 | 报环境与变量名，不打印密码 |
| SQL 报错 | 原样返回错误，不猜测改写 |
| 影响行数为 0 | 明确报告 0 行，不当作写入成功 |
