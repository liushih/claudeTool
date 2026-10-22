/**
 * hexincloud 本地联调浏览器驱动（可见 Chrome + 条件等待，不用固定 sleep）。
 *
 * 用法：
 *   import { openBrowser, loginIfNeeded, gotoB2dSend, waitApi, waitToast } from './browser.mjs';
 *   const { ctx, page } = await openBrowser();
 *   await loginIfNeeded(page);
 *   await gotoB2dSend(page);
 *   const resp = await waitApi(page, '/wms/pickingPlan/list', () => page.getByRole('button', { name: '搜索' }).click());
 */

import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const HERE = dirname(fileURLToPath(import.meta.url));
try { process.loadEnvFile(resolve(HERE, '.env')); } catch { /* 无 .env 时用系统环境变量 */ }

export const BASE = process.env.HEXIN_BASE || 'http://localhost';
const PROFILE = process.env.PW_PROFILE || resolve(HERE, '..', 'pw-profile');

/** 启动/复用可见 Chrome（固定 profile，登录态可保留） */
export async function openBrowser({ headless = false } = {}) {
  const ctx = await chromium.launchPersistentContext(PROFILE, {
    headless,
    channel: 'chrome',
    viewport: null,
    acceptDownloads: true,
    args: ['--start-maximized', '--no-first-run', '--no-default-browser-check']
  });
  const page = ctx.pages()[0] ?? (await ctx.newPage());
  page.setDefaultTimeout(15000);
  return { ctx, page };
}

/** 登录页才登录；已登录直接返回。密码取自 HEXIN_PASSWORD，不写进代码 */
export async function loginIfNeeded(page, user = process.env.HEXIN_USER || 'admin', password = process.env.HEXIN_PASSWORD) {
  await page.goto(BASE, { waitUntil: 'domcontentloaded' });
  // SPA 客户端跳转有延迟，先等落在登录页或首页再判断
  await page.waitForURL(/\/(login|index)/, { timeout: 20000 }).catch(() => {});
  if (!page.url().includes('/login')) return false;
  if (!password) throw new Error('缺少登录密码：在 hexin-e2e/.env 设置 HEXIN_PASSWORD');
  const tab = page.getByRole('button', { name: '使用账号密码登录' });
  if (await tab.count()) await tab.click();
  await page.getByPlaceholder('手机号').fill(user);
  await page.getByPlaceholder('密码').fill(password);
  await page.getByRole('button', { name: '登 录' }).click();
  // 注意不能用 /\/index/：登录页 URL 的 redirect 参数里也含 /index
  await page.waitForURL(u => new URL(u).pathname === '/index', { timeout: 20000 });
  await page.waitForFunction(() => !!localStorage.getItem('Admin-Token'), null, { timeout: 20000 });
  return true;
}

/** 进入 B2D 出库并切到待发货，等列表接口返回后才继续 */
export async function gotoB2dSend(page) {
  await page.goto(`${BASE}/wms/outbound/outboundB2d`, { waitUntil: 'domcontentloaded' });
  await page.waitForURL(/\/(login|wms\/outbound)/, { timeout: 20000 }).catch(() => {});
  if (page.url().includes('/login')) {
    await loginIfNeeded(page);
    await page.goto(`${BASE}/wms/outbound/outboundB2d`, { waitUntil: 'domcontentloaded' });
  }
  const tab = page.getByRole('tab', { name: /待发货/ });
  await tab.waitFor({ state: 'visible' });
  await Promise.all([
    waitApi(page, '/wms/pickingPlan/list'),
    tab.click()
  ]);
}

/** 执行 action 并等指定接口返回（替代 waitForTimeout） */
export async function waitApi(page, urlPart, action, timeout = 20000) {
  const [resp] = await Promise.all([
    page.waitForResponse(r => r.url().includes(urlPart), { timeout }),
    Promise.resolve().then(action)
  ]);
  return resp;
}

/** 等 Toast 出现并返回文案 */
export async function waitToast(page, textRe, timeout = 12000) {
  const msg = page.locator('.el-message').filter({ hasText: textRe }).last();
  await msg.waitFor({ state: 'visible', timeout });
  return (await msg.innerText()).trim();
}

/** 按行内文本定位待发货行 */
export function findRow(page, rowText) {
  return page.locator('table tbody tr')
    .filter({ has: page.locator('input.standard-checkbox') })
    .filter({ hasText: rowText })
    .first();
}

/** 行「更多」→「修改物流方式」，等上下文接口返回 */
export async function openLogisticsDialog(page, rowText) {
  const row = findRow(page, rowText);
  await row.waitFor({ state: 'visible' });
  await row.getByRole('button', { name: '更多' }).click();
  const item = page.locator('button').filter({ hasText: /^\s*修改物流方式\s*$/ }).last();
  await item.waitFor({ state: 'visible' });
  await waitApi(page, '/b2dLogistics/context', () => item.click());
  await page.locator('[data-testid="b2d-update-logistics-dialog"]').waitFor({ state: 'visible' });
}

/** 行「日志」，等日志树接口返回 */
export async function openRowLog(page, rowText) {
  const row = findRow(page, rowText);
  await waitApi(page, '/log/operlog/treeByBizKey',
    () => row.getByRole('button', { name: '日志' }).click());
  const drawer = page.locator('.el-drawer:visible').first();
  await drawer.waitFor({ state: 'visible' });
  return drawer;
}

/** 展开抽屉内所有可展开日志 */
export async function expandAllLogs(drawer) {
  const btns = drawer.locator('.field-change-toggle-btn').filter({ hasText: '展开' });
  for (let i = 0; i < (await btns.count()); i++) {
    await btns.nth(i).click().catch(() => {});
  }
}

/** 关闭当前弹框（有脏数据确认时点确认） */
export async function closeDialog(page) {
  const dlg = page.locator('[data-testid="b2d-update-logistics-dialog"]');
  if (!(await dlg.count())) return;
  await dlg.getByRole('button', { name: '取消' }).click();
  const box = page.locator('.el-message-box');
  if (await box.count()) await box.getByRole('button', { name: '确认' }).click();
}
