// Demo mode (?demo=1): the prototype's review widget stays, and the Settings menu carries the same static Engine mock
// as the prototype (nothing is called; the choice only lives in the page).
import { test, expect } from '@playwright/test';

test('demo · review widget stays; Engine in Settings is a static mock that follows the picked provider', async ({ page }) => {
  await page.goto('/?demo=1', { waitUntil: 'networkidle' });
  await expect(page.locator('#proto-widget-btn')).toBeVisible();          // the prototype's screen switcher is a review tool, not the product
  await expect(page.locator('#proto-widget-card')).toContainText('Novaliners Dev');
  await page.getByRole('button', { name: 'Settings' }).click();
  const engine = page.locator('#engine-settings');
  await expect(engine.getByText('Engine', { exact: true })).toBeVisible();
  await expect(page.getByLabel('Provider')).toHaveValue('vertex');
  await expect(page.getByLabel('Model')).toHaveValue('gemini-3.5-flash-lite');
  await expect(engine.getByText('Engine ready. New answers use this model.')).toBeVisible();
  const calls = [];
  page.on('request', r => { if (/admin\/model|\/health/.test(r.url())) calls.push(r.url()); });
  await page.getByLabel('Provider').focus();                      // as a real user: the select has focus when it changes
  await page.getByLabel('Provider').selectOption('gemini');
  await expect(page.getByLabel('Model')).toHaveValue('gemini-3.5-flash-lite');
  await expect(page.getByLabel('Provider')).toBeFocused();
  await page.getByLabel('Model').selectOption('gemini-pro-latest');
  await expect(page.getByLabel('Model')).toHaveValue('gemini-pro-latest');
  expect(calls).toEqual([]);
});
