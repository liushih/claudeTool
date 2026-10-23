---
name: adapter-bootstrap
description: >-
  接入新的业务流程，边跑边记生成或更新本地适配层。用户说「接入」「新业务」
  「第一次造 X」「打通这个流程」时使用。产出 adapter.yaml 与 pitfalls.md。
---

# 适配层接入

## 适用场景

- 新业务首次造数
- 现有业务新增步骤，或修正已知失败原因

## 前置检查

1. 确认项目 ID 与数据目录（默认 `%USERPROFILE%\.hexin-tools`）
2. 收集：接口地址、认证方式、目标状态
3. 逐项确认：字段映射、枚举取值、异步时序
4. 读 `{{TOOLS_DIR}}/skills/_references/adapter-contract.md` 与 `pitfalls.md`

## 路径

`{{TOOLS_DIR}}` 是工具仓库根目录。Claude 插件安装时改用 `${CLAUDE_PLUGIN_ROOT}`；Cursor / Codex 由 `install.ps1` 渲染成本机绝对路径。

## 执行

1. 从 `{{TOOLS_DIR}}/skills/_TEMPLATE/adapter.example.yaml` 起草 `<数据目录>/projects/<项目ID>/adapter.yaml`
2. 先跑 1 条：`python {{TOOLS_DIR}}/scripts/run.py --project <项目ID> --entity <业务对象> --count 1`
3. 失败就查接口或问用户，不猜字段
4. 跑通后补 `verify` 段，格式见 `{{TOOLS_DIR}}/skills/_TEMPLATE/adapter.example.yaml`
5. 每条坑按四段（现象 / 原因 / 绕法 / 适用）追加到 `pitfalls.md`；追加前先读现有条目，按「现象」去重
6. 用同一批次号重跑，确认幂等

## 失败处理

| 情况 | 动作 |
|---|---|
| 接口返回结构未知 | 打印响应前 500 字符，不猜字段 |
| 枚举取值不明 | 走匹配接口或询问，不硬编码 |
| 连续失败 3 次 | 停下，列出已确认与未确认项 |
| 用户无法提供凭据 | 保留适配层，标记 `.env` 待填 |
