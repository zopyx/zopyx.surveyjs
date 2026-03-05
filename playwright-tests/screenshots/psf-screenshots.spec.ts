/**
 * PSF (Privacy Forms Studio) landing page screenshots
 * Captures the @@pfs view which is the main entry point
 */

import { test, expect } from '@playwright/test';
import { ScreenshotHelper } from '../utils/screenshot-helpers';

test.describe('PSF Landing Page (@@pfs)', () => {
  let screenshots: ScreenshotHelper;

  test.beforeEach(({ page }, testInfo) => {
    screenshots = new ScreenshotHelper(page, testInfo, 'psf');
  });

  test('@@pfs - authenticated admin view', async ({ page }) => {
    await page.goto('/@@pfs');
    await page.waitForLoadState('networkidle');
    
    // Wait for the cards to be visible
    await expect(page.locator('.pfs-cards, .pfs-card, [class*="card"]')).toBeVisible();
    await page.waitForTimeout(500);
    
    await screenshots.capture('pfs-admin', { fullPage: true });
  });

  test('@@pfs - with template selection visible', async ({ page }) => {
    await page.goto('/@@pfs');
    await page.waitForLoadState('networkidle');
    
    // Check if template section exists
    const templateSection = page.locator('.template-section, select[name="template_uid"]').first();
    
    if (await templateSection.isVisible().catch(() => false)) {
      // Click to open template dropdown if it exists
      await templateSection.click();
      await page.waitForTimeout(500);
      
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

  test('@@pfs - anonymous/not logged in', async ({ page }) => {
    await page.goto('/@@pfs');
    await page.waitForLoadState('networkidle');
    
    // Wait for page to settle - may show login prompt or limited view
    await page.waitForTimeout(1000);
    
    await screenshots.capture('pfs-anonymous', { fullPage: true });
  });
});

test.describe('PSF Related Views', () => {
  let screenshots: ScreenshotHelper;

  test.beforeEach(({ page }, testInfo) => {
    screenshots = new ScreenshotHelper(page, testInfo, 'psf');
  });

  test('@@survey-overview', async ({ page }) => {
    await page.goto('/@@survey-overview');
    await page.waitForLoadState('networkidle');
    
    await expect(page.locator('.survey-overview, table, .overview-list')).toBeVisible({ timeout: 10000 });
    await page.waitForTimeout(500);
    
    await screenshots.capture('survey-overview', { fullPage: true });
  });

  test('@@survey-templates-overview', async ({ page }) => {
    await page.goto('/@@survey-templates-overview');
    await page.waitForLoadState('networkidle');
    
    await expect(page.locator('.templates-overview, .template-list')).toBeVisible({ timeout: 10000 });
    await page.waitForTimeout(500);
    
    await screenshots.capture('templates-overview', { fullPage: true });
  });

  test('@@survey-monitor', async ({ page }) => {
    await page.goto('/@@survey-monitor');
    await page.waitForLoadState('networkidle');
    
    await expect(page.locator('.monitor, .survey-monitor, .stats')).toBeVisible({ timeout: 10000 });
    await page.waitForTimeout(500);
    
    await screenshots.capture('survey-monitor', { fullPage: true });
  });
});
