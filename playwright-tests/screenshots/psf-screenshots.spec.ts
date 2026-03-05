/**
 * PSF (Privacy Forms Studio) landing page screenshots
 * Captures the @@pfs view which is the main entry point
 */

import { test, expect } from '@playwright/test';
import { ScreenshotHelper, SCREENSHOT_TIMEOUT } from '../utils/screenshot-helpers';

test.describe('PSF Landing Page (@@pfs)', () => {
  let screenshots: ScreenshotHelper;

  test.beforeEach(({ page }, testInfo) => {
    screenshots = new ScreenshotHelper(page, testInfo, 'psf');
  });

  test('@@pfs - authenticated admin view', async ({ page, baseURL }) => {
    await page.goto(`${baseURL}/@@pfs`);
    await page.waitForLoadState('networkidle');

    // Wait for the card grid to be visible
    await expect(page.locator('.pfs-card-grid').first()).toBeVisible();
    await page.waitForTimeout(SCREENSHOT_TIMEOUT);

    await screenshots.capture('pfs-admin', { fullPage: true });
  });

  test('@@pfs - with template selection visible', async ({ page, baseURL }) => {
    await page.goto(`${baseURL}/@@pfs`);
    await page.waitForLoadState('networkidle');

    // Check if template section exists
    const templateSection = page.locator('.template-section, select[name="template_uid"]').first();

    if (await templateSection.isVisible().catch(() => false)) {
      // Click to open template dropdown if it exists
      await templateSection.click();
      await page.waitForTimeout(SCREENSHOT_TIMEOUT);

      await screenshots.capture('pfs-templates', { fullPage: true });
    } else {
      test.skip(true, 'No templates available');
    }
  });
});

test.describe('PSF Anonymous View', () => {
  test.use({ storageState: undefined });

  let screenshots: ScreenshotHelper;

  test.beforeEach(({ page }, testInfo) => {
    screenshots = new ScreenshotHelper(page, testInfo, 'psf-anon');
  });

  test('@@pfs - anonymous/not logged in', async ({ page, baseURL }) => {
    await page.goto(`${baseURL}/@@pfs`);
    await page.waitForLoadState('networkidle');

    // Wait for page to settle - may show login prompt or limited view
    await page.waitForTimeout(SCREENSHOT_TIMEOUT);

    await screenshots.capture('pfs-anonymous', { fullPage: true });
  });
});

test.describe('PSF Related Views', () => {
  let screenshots: ScreenshotHelper;

  test.beforeEach(({ page }, testInfo) => {
    screenshots = new ScreenshotHelper(page, testInfo, 'psf');
  });

  test('@@survey-overview', async ({ page, baseURL }) => {
    await page.goto(`${baseURL}/@@survey-overview`);
    await page.waitForLoadState('networkidle');

    await expect(page.locator('.survey-overview, table, .overview-list')).toBeVisible({ timeout: SCREENSHOT_TIMEOUT });
    await page.waitForTimeout(SCREENSHOT_TIMEOUT);

    await screenshots.capture('survey-overview', { fullPage: true });
  });

  test('@@survey-templates-overview', async ({ page, baseURL }) => {
    await page.goto(`${baseURL}/@@survey-templates-overview`);
    await page.waitForLoadState('networkidle');

    await expect(page.locator('#content-core')).toBeVisible({ timeout: SCREENSHOT_TIMEOUT });
    await page.waitForTimeout(SCREENSHOT_TIMEOUT);

    await screenshots.capture('templates-overview', { fullPage: true });
  });

  test.skip('@@survey-monitor', async ({ page, baseURL }) => {
    await page.goto(`${baseURL}/@@survey-monitor`);
    await page.waitForLoadState('networkidle');

    await expect(page.locator('#content-core')).toBeVisible({ timeout: SCREENSHOT_TIMEOUT });
    await page.waitForTimeout(SCREENSHOT_TIMEOUT);

    await screenshots.capture('survey-monitor', { fullPage: true });
  });
});
