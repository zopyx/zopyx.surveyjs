/**
 * Control Panel screenshots
 * Captures the @@forms-settings and related configuration views
 */

import { test, expect } from '@playwright/test';
import { ScreenshotHelper } from '../utils/screenshot-helpers';

test.describe('Forms Control Panel', () => {
  let screenshots: ScreenshotHelper;

  test.beforeEach(({ page }, testInfo) => {
    screenshots = new ScreenshotHelper(page, testInfo, 'controlpanel');
  });

  test('@@forms-settings - main settings', async ({ page, baseURL }) => {
    await page.goto(`${baseURL}/@@forms-settings`);
    await page.waitForLoadState('networkidle');

    // Wait for the SurveyJS form to render
    await expect(page.locator('.sd-container-modern, #surveyContainer, .forms-settings')).toBeVisible({ timeout: 15000 });
    await page.waitForTimeout(1000);

    await screenshots.capture('forms-settings', { fullPage: true });
  });

  test('@@forms-settings - AI settings section', async ({ page, baseURL }) => {
    await page.goto(`${baseURL}/@@forms-settings`);
    await page.waitForLoadState('networkidle');

    await expect(page.locator('.sd-container-modern')).toBeVisible({ timeout: 15000 });

    // Try to navigate to AI settings panel if tabs exist
    const aiTab = page.locator('text=AI, text=AI Settings, [data-panel="ai"]').first();
    if (await aiTab.isVisible().catch(() => false)) {
      await aiTab.click();
      await page.waitForTimeout(500);
    }

    await screenshots.capture('forms-settings-ai', { fullPage: true });
  });

  test('@@forms-settings - Email settings section', async ({ page, baseURL }) => {
    await page.goto(`${baseURL}/@@forms-settings`);
    await page.waitForLoadState('networkidle');

    await expect(page.locator('.sd-container-modern')).toBeVisible({ timeout: 15000 });

    // Try to navigate to Email settings panel
    const emailTab = page.locator('text=Email, text=Mail, [data-panel="email"]').first();
    if (await emailTab.isVisible().catch(() => false)) {
      await emailTab.click();
      await page.waitForTimeout(500);
    }

    await screenshots.capture('forms-settings-email', { fullPage: true });
  });

  test('@@forms-settings - Storage settings section', async ({ page, baseURL }) => {
    await page.goto(`${baseURL}/@@forms-settings`);
    await page.waitForLoadState('networkidle');

    await expect(page.locator('.sd-container-modern')).toBeVisible({ timeout: 15000 });

    // Try to navigate to Storage settings panel
    const storageTab = page.locator('text=Storage, text=Database, [data-panel="storage"]').first();
    if (await storageTab.isVisible().catch(() => false)) {
      await storageTab.click();
      await page.waitForTimeout(500);
    }

    await screenshots.capture('forms-settings-storage', { fullPage: true });
  });
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
    await screenshots.capture('site-setup-overview', { fullPage: true });
  });

  test('Add-ons control panel', async ({ page, baseURL }) => {
    await page.goto(`${baseURL}/@@prefs_install_products_form`);
    await page.waitForLoadState('networkidle');

    await expect(page.locator('#content, .addons-list')).toBeVisible();
    await page.waitForTimeout(500);

    await screenshots.capture('addons-controlpanel', { fullPage: true });
  });
});
