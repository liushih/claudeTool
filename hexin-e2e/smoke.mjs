import { openBrowser, loginIfNeeded, gotoB2dSend } from './browser.mjs';

const { ctx, page } = await openBrowser();
try {
  const logged = await loginIfNeeded(page);
  await gotoB2dSend(page);
  const rows = page.locator('table tbody tr').filter({ has: page.locator('input.standard-checkbox') });
  await rows.first().waitFor();
  console.log(JSON.stringify({ logged, url: page.url(), rows: await rows.count() }, null, 2));
} finally {
  await ctx.close();
}
