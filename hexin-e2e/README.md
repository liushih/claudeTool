# hexin-e2e

hexincloud 本地联调的浏览器驱动（可见 Chrome + 条件等待）。

## 配置在哪

| 配置 | 位置 | 作用 |
|------|------|------|
| Playwright MCP 启动参数 | `hexincloud/.mcp.json` → `mcpServers.playwright.args` | `--browser chrome --headed --user-data-dir <claudeTool>/pw-profile`，让 MCP 直接起可见 Chrome，不用再手动连 CDP |
| 浏览器 profile | 默认 `../pw-profile`，可用 `PW_PROFILE` 覆盖 | 复用登录态，第二次起不用重新登录 |
| 等待条件封装 | `browser.mjs` | 用接口响应 / 元素可见 / URL 变化代替固定 sleep |
| 冒烟脚本 | `smoke.mjs` | 验证浏览器能起、能登录、能进 B2D 待发货 |

`.mcp.json` 改完后需要重启一次会话，MCP server 才会用新参数启动。

## 用法

```bash
cd hexin-e2e
node smoke.mjs
```

在自己的脚本里：

```js
import { openBrowser, loginIfNeeded, gotoB2dSend, waitApi, waitToast, openLogisticsDialog, openRowLog } from './browser.mjs';

const { ctx, page } = await openBrowser();
try {
  await loginIfNeeded(page);            // 已登录直接跳过
  await gotoB2dSend(page);              // 等列表接口返回后才继续

  await openLogisticsDialog(page, 'WOS26102101008'); // 等 context 接口返回
  await waitToast(page, /物流方式已修改/);
} finally {
  await ctx.close();
}
```

## 原则

- 不写 `waitForTimeout(2500)`；用 `waitApi`、`locator.waitFor`、`page.waitForURL`。
- 选择器用精确文本或 `data-testid`，避免 `查询` 同时命中侧边栏按钮。
- 单次脚本内把整个流程跑完，避免每个动作都重连浏览器。
- 使用系统 Chrome（`channel: 'chrome'`），`PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1` 安装，不额外下载浏览器。

## 注意

- 同一个 profile 同时只能被一个 Chrome 使用；如果之前手动开过这个 profile，先关掉。
- 本地前端默认 `http://localhost`，后端网关 `http://localhost:8080`。
