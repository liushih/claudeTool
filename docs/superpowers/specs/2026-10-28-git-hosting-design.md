# 多平台 Git 管理能力设计

**日期**：2026-10-28
**状态**：待审阅
**关联**：`runtime/git_host/`、`scripts/git_host.py`、项目配置 `git_hosts.yaml`

## 1. 背景与目标

工具包已能采集 git 提交用于报告，但不能推送、拉取、合并或建 MR。日常的分支流转（feature → dev/test/prod）
仍靠手工完成，而且容易踩已知的坑：feature/test 分支带进 test 内容、本地环境配置被误提交、prod 衍生分支直合 dev。

本次目标是把这些操作做成工具能力，并把已有的分支与提交规则固化为硬约束：

- 支持 GitHub、Gitee、GitLab 三个平台（含私有化部署）
- 每个项目配置自己的平台与令牌，令牌只存项目 `.env`
- 覆盖：提交、推送、拉取、合并分支、创建 MR/PR
- 规则由工具强制执行，而不是靠记忆提醒

成功标准：

- 用一句白话能完成「把当前改动提交并推到 dev」「把 feature 分支开 MR 到 test」
- 违反记忆规则的操作被拒绝，并说明原因（例如 feature/test 分支直合 dev）
- 令牌不出现在命令行、日志、台账和 git 配置里

## 2. 范围

**做**

- 平台：GitHub、Gitee、GitLab（私有化地址可配）
- 操作：`commit`、`push`、`pull`、`merge`（分支间）、`mr create`（建 MR/PR）、`mr status`
- 分支命名校验与生成：`feature/<目标>/<用户标识>/<任务号>-<描述>`
- 用户标识：首次使用时询问，存本机配置，之后沿用
- 提交信息校验：`feat-/fix-<任务号>: <中文描述>`，正文必须存在

**不做**

- 合并冲突的自动解决（冲突时停止，交给人）
- 删除远端分支（只提示，由人执行）
- 代替审批：test/prod 的 MR 只能创建，合并由有权限的人完成
- Gitee 与 GitHub 的 Webhook、CI 触发
- 多平台同时推送（一个项目一个主平台）

## 3. 总体结构

```
runtime/git_host/
  __init__.py        对外接口：get_host(project, cfg) -> GitHost
  base.py            GitHost 抽象：create_mr / mr_status / token_header
  github.py          GitHub REST（PR）
  gitee.py           Gitee v5 REST（PR）
  gitlab.py          GitLab v4 REST（MR）
  rules.py           分支名、提交信息、合并规则的校验（纯函数）
  repo.py            本地 git 操作封装：commit / push / pull / merge
scripts/git_host.py  命令行入口
```

**拆分原则**：规则校验（`rules.py`）是纯函数，可以不连网测试；平台差异只放在三个适配器里；
本地 git 操作和远端 API 分开，远端失败不影响本地状态。

## 4. 项目配置

位置：`~/.data-tools/projects/<项目ID>/git_hosts.yaml`

```yaml
user_tag: lsh              # 首次使用时询问，之后沿用；用于分支名中的用户标识
repo_path: C:/project/hexincloud
host:
  kind: gitlab             # github | gitee | gitlab
  base_url: http://git.hexincorp.cn:36359
  project_path: hexincloud/hexincloud   # GitLab 为 group/project；GitHub/Gitee 为 owner/repo
  token_key: GITLAB_TOKEN_HEXINCLOUD    # 对应项目 .env 中的键名
branches:
  dev: dev
  test: test
  prod: prod
rules:
  forbid_direct_merge_to: [test, prod]  # 只允许 MR，不允许工具直接合并
  forbid_feature_test_into_dev: true     # 合 dev 前算净增量，禁止整支带入 test 内容
  forbid_commit_paths:                   # 本地环境配置不提交
    - pom.xml
    - vite.config.ts
```

令牌**不在本文件**，只在项目 `.env`：

```
GITLAB_TOKEN_HEXINCLOUD=
```

一个项目可以有多个 host 配置（例如 GitHub 和 GitLab 各一个），用 `host` 列表加 `name` 区分，
本期只实现单主平台，多平台在第 12 节列为后续。

## 5. 令牌处理

- 令牌只从项目 `.env` 读取，`token_key` 指定键名
- 缺失时报错并给出键名，不回退到其它位置或环境变量
- 令牌通过 HTTP Header 发送（GitLab `PRIVATE-TOKEN`，GitHub `Authorization: Bearer`，Gitee `access_token` 参数
  仅在必须时使用，优先 Header）
- 不写入：命令行参数、日志、台账、报告、git 配置、`.superpowers/`
- 错误信息只显示键名和 HTTP 状态码，不回显请求体
- 与 `check_secrets.py` 的检测规则保持一致：提交前扫描仍生效

**你给的示例令牌**（`glpat-…` 形式）已在对话中出现，视为泄露。设计阶段不使用它，
实现阶段也不写入任何文件，测试用虚构令牌。

## 6. 规则（硬约束）

规则在 `rules.py` 中实现为纯函数，每个操作执行前调用，违反则拒绝并说明原因。

| 规则 | 来源记忆 | 行为 |
|---|---|---|
| 分支名 `feature/<目标>/<user_tag>/<任务号>-<描述>` | `branch-naming-and-hygiene` | 创建分支时校验；不符合则拒绝 |
| 一分支一任务 | `branch-naming-and-hygiene` | 同一分支出现两个任务号则拒绝 |
| 提交信息 `feat-/fix-<任务号>: <描述>` | `git-commit-message-style` | 不符合则拒绝；正文为空则警告 |
| 正文必须概述修改 | `git-commit-message-style` | 正文为空时拒绝提交 |
| 本地环境配置不提交 | `local-env-config-not-committed` | `forbid_commit_paths` 命中则拒绝 add |
| dev 可本地合并并推送 | `dev-merge-locally` | 允许 merge + push |
| test/prod 只能开 MR | `dev-merge-locally` | `merge` 目标为 test/prod 时拒绝，改为 `mr create` |
| prod 衍生分支不直接合 test/dev | `prod-branch-not-merged-directly-to-test-dev` | 源分支以 prod 为基底时拒绝合到 test/dev |
| 合 dev 前算净增量 | `merge-feature-test-branch-drags-test-into-dev` | 合并前列出将带入的提交数与文件数，超出源分支自身范围则拒绝 |
| 合并后删源分支 | `branch-naming-and-hygiene` | 只提示，不自动删除 |
| 从目标分支切新分支 | 本次确认 | `branch create` 从 `origin/<目标>` 切出，`--no-track`，不继承其它分支的上游 |
| 推送只到同名远端分支 | 本次确认 | `push` 的远端分支名必须与本地相同；禁止推到 test/dev/prod 同名分支 |
| 目标为 test/prod 只能建 MR | 本次确认 | 需要「合并到 test」时执行 `mr create --to test`，不提供本地合并 |

**分支名中的 `user_tag`**：第一次使用询问，之后写入 `git_hosts.yaml`。规则只校验格式，不预设取值。

## 7. 操作流程

以 `git_host.py` 的子命令为准：

| 子命令 | 作用 | 关键校验 |
|---|---|---|
| `commit -m <消息>` | 提交已暂存改动 | 提交信息格式、正文、禁止路径 |
| `push` | 推送当前分支到同名远端分支 | 分支名格式；远端分支名与本地一致；本地分支名为 test/dev/prod 时拒绝 |
| `branch create --name N --target T` | 从 `origin/T` 切出新分支 | 先 fetch；`--no-track`；切后校验 `origin/T..HEAD` 为空 |
| `pull [--from dev]` | 拉取目标分支 | 本地有未提交改动时拒绝 |
| `merge --from <分支> --to dev` | 本地合并到 dev 后推送 | 净增量、prod 衍生、feature/test 规则 |
| `mr create --from <分支> --to test` | 调平台 API 建 MR | 目标为 test/prod 时必须走这里 |
| `mr status <编号>` | 查 MR 是否可合并 | 只读 |

**失败语义**：本地操作失败时不做远端操作；远端 API 失败时本地状态保持，报告 HTTP 状态与平台返回的错误摘要。

### 7.1 生产热修复流程（统一规则）

**统一规则**：凡是 prod 来源的改动，要进 test 或 dev，都必须经过一个从 `origin/test` 切出的同步分支，
不直接把 prod 分支或热修复分支合进 test/dev。

流程（A 步与 C 步同时进行）：

1. 从 `origin/prod` 切热修复分支 `feature/prod/<user_tag>/<任务号>-<描述>`，修复，提交
2. **A**：同时开两件事
   - 热修复分支开 MR 到 prod（`mr create --to prod`）
   - 从 `origin/test` 切同步分支 `feature/test/<user_tag>/<任务号>-<描述>`（`branch create --target test`）
3. **C**：同步分支不合并热修复分支本身，而是用 `cherry-pick` 搬热修复的提交，把改动按内容带过去
4. 同步分支开 MR 到 test（`mr create --to test`）
5. 同步分支本地合并到 dev 前，`verify-flow` 出清单 C，确认只带入热修复的改动，再执行合并并推送

**B（合并方式）**：热修复合到 prod 的 MR 可以用 merge、fast-forward 或 squash，三种都不影响同步分支。
同步分支只用 `cherry-pick`，不依赖 prod 上的提交哈希，因此不会因 squash 产生重复提交。

**异常处理（来自 A 的决定）**：任一 MR 检测到异常（冲突、被拒、与 prod 不一致），工具停止后续步骤并通知用户。
恢复方式是：重新从对应源头切分支，重新提交，不在原分支上修补。

### 7.2 差异验证（只读）

子命令 `verify-flow --prod-branch P --test-branch T --target dev|test`，只读，不做合并，输出三份清单：

| 清单 | 计算方式 | 期望 |
|---|---|---|
| A. prod 带入 test 衍生分支的内容 | `git rev-list --cherry-pick --right-only origin/test...P` | 只有你要带的 prod 改动 |
| B. test 衍生分支相对 test 的净增量 | `git rev-list --cherry-pick --right-only origin/test...T`，及对应文件 | 只有你的改动，不含 prod 独有提交 |
| C. test 衍生分支相对 dev 的净增量 | `git rev-list --cherry-pick --right-only origin/dev...T`，及对应文件 | 只有你要带进 dev 的改动 |

每份清单都标注提交数与文件数。清单 B、C 中若出现 prod 独有的提交（在 `origin/prod` 中、但不在 `origin/test` 中），
工具必须标红并停止后续合并。

确认 A、B、C 符合预期后，才允许执行第 2 步的合并、第 3 步的 MR 与本地合并。

## 8. 错误处理

| 情况 | 行为 |
|---|---|
| 令牌键缺失 | 报键名，停止 |
| 令牌无效（401/403） | 报「令牌无效或权限不足」，不重试 |
| 网络不通（如 GitHub 直连失败） | 报错并提示代理配置，不静默重试写请求 |
| 冲突 | 停止，列出冲突文件，不尝试自动解决 |
| 规则违反 | 拒绝，给出违反的规则名与对应记忆 |
| 平台返回 MR 已存在 | 报告已有编号，不重复创建 |
| 用户标识未设置 | 询问一次，写入配置后继续 |

写请求（推送、建 MR）超时不自动重试，与造数工具一致，避免重复创建。

## 9. 与现有能力的关系

- 报告采集（`runtime/gitlog.py`）继续只读，不依赖本模块
- 造数与查库不受影响
- `check_secrets.py` 的规则覆盖新增的 `git_hosts.yaml`（它只含键名，不含值，但仍在扫描范围内）

## 10. 测试策略

- `rules.py`：分支名、提交信息、禁止路径、净增量、prod 衍生判断，全部用纯函数单测，覆盖每条规则的通过与拒绝两面
- 三个平台适配器：用本地假 HTTP 服务验证请求路径、Header、响应解析、401/403/409 的处理；不连真实平台
- `repo.py`：临时 git 仓库，验证 commit 规则、merge 净增量计算、冲突停止
- 令牌：断言令牌不出现在异常信息、日志、台账中（用一个虚构值做检查）
- CLI：子命令参数与规则拒绝路径

真实平台的端到端验证需要你确认后再做，设计阶段不向任何平台发请求。

## 11. 验收标准

1. 三个平台都能建 MR/PR，并能查询状态
2. 违反任一硬规则时，操作被拒绝且说明原因
3. 令牌缺失或无效时给出可操作的错误，且令牌不泄露
4. 第一次使用时询问用户标识，之后不再问
5. 所有规则都有对应测试，且不依赖真实平台

## 12. 后续

- 多平台同时配置（一个项目多个 host）
- 冲突辅助解决
- 合并请求的评审意见读取
- 与报告工具联动：报告里带上本周期合并的 MR 列表
