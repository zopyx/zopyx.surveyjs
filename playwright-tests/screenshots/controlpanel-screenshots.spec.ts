/**
 * Control Panel screenshots
 * Captures the @@forms-settings view for every fieldset (page) plus the
 * related Plone control panels.
 *
 * The Forms control panel is a SurveyJS form with 7 pages and bottom
 * navigation (no TOC in the current build), so each fieldset screenshot
 * navigates to its page by clicking the "Next" button the required number
 * of times. The page order matches forms_settings.json:
 * General, AI, Logging, Mail, Result Storage, Security, Embedding.
 */

import { test, expect, type Page } from '@playwright/test';
import { ScreenshotHelper, SCREENSHOT_TIMEOUT } from '../utils/screenshot-helpers';

const FIELDSETS = [
  { name: 'general', index: 0, title: 'General' },
  { name: 'ai', index: 1, title: 'AI' },
  { name: 'logging', index: 2, title: 'Logging' },
  { name: 'mail', index: 3, title: 'Mail' },
  { name: 'storage', index: 4, title: 'Result Storage' },
  { name: 'security', index: 5, title: 'Security' },
  { name: 'embedding', index: 6, title: 'Embedding' },
];

async function navigateToFieldset(page: Page, index: number) {
  await page.waitForLoadState('networkidle');
  await expect(page.locator('#survey-add-widget.is-ready')).toBeVisible({
    timeout: SCREENSHOT_TIMEOUT,
  });
  for (let i = 0; i < index; i += 1) {
    await page.getByRole('button', { name: 'Next' }).click();
    // Wait for the SurveyJS page transition (hidden pages, animations).
    await page.waitForTimeout(800);
  }
  await page.waitForTimeout(1500);
}

test.describe('Forms Control Panel', () => {
  let screenshots: ScreenshotHelper;

  test.beforeEach(({ page }, testInfo) => {
    screenshots = new ScreenshotHelper(page, testInfo, 'controlpanel');
  });

  for (const fieldset of FIELDSETS) {
    test(`@@forms-settings - ${fieldset.title} fieldset`, async ({ page, baseURL }) => {
      await page.goto(`${baseURL}/@@forms-settings`);
      await navigateToFieldset(page, fieldset.index);
      await screenshots.capture(fieldset.name, { fullPage: true });
    });
  }
});

test.describe('Plone Control Panels', () => {
  let screenshots: ScreenshotHelper;

  test.beforeEach(({ page }, testInfo) => {
    screenshots = new ScreenshotHelper(page, testInfo, 'controlpanel');
  });

  test('Site Setup overview', async ({ page, baseURL }) => {
    await page.goto(`${baseURL}/@@overview-controlpanel`);
    await page.waitForLoadState('networkidle');
    await expect(page.locator('#content, .overview-controlpanel')).toBeVisible();
    await screenshots.capture('overview', { fullPage: true });
  });

  test('Add-ons control panel', async ({ page, baseURL }) => {
    await page.goto(`${baseURL}/@@prefs_install_products_form`);
    await page.waitForLoadState('networkidle');

    await expect(page.locator('#content, .addons-list')).toBeVisible();
    await page.waitForTimeout(SCREENSHOT_TIMEOUT);

    await screenshots.capture('addons', { fullPage: true });
  });
});
