/**
 * Survey Actions panel screenshots
 * Tests all actions from the survey_actions panel including Metadata fieldsets
 */

import { test, expect } from '@playwright/test';
import { ScreenshotHelper, SCREENSHOT_TIMEOUT } from '../utils/screenshot-helpers';

// Test survey path relative to baseURL
const TEST_SURVEY_PATH = '/en/demos/prefilled';

test.describe('Survey Actions Panel', () => {
  let screenshots: ScreenshotHelper;

  test.beforeEach(({ page }, testInfo) => {
    screenshots = new ScreenshotHelper(page, testInfo, 'survey');
  });

  test('@@viewer - View survey form', async ({ page, baseURL }) => {
    await page.goto(`${baseURL}${TEST_SURVEY_PATH}/@@viewer`);
    await page.waitForLoadState('networkidle');
    await screenshots.waitForSurveyJS();
    await screenshots.capture('action-viewer');
  });

  test('@@survey-metadata - Metadata settings', async ({ page, baseURL }) => {
    await page.goto(`${baseURL}${TEST_SURVEY_PATH}/@@survey-metadata`);
    await page.waitForLoadState('networkidle');
    
    // Wait for SurveyJS form to load
    await expect(page.locator('.sd-container-modern')).toBeVisible({ timeout: SCREENSHOT_TIMEOUT });
    await page.waitForTimeout(SCREENSHOT_TIMEOUT);
    
    await screenshots.capture('action-metadata');
  });

  test('@@editor - Visual Editor', async ({ page, baseURL }) => {
    await page.goto(`${baseURL}${TEST_SURVEY_PATH}/@@editor`);
    await page.waitForLoadState('networkidle');
    await expect(page.locator('.svc-creator')).toBeVisible({ timeout: SCREENSHOT_TIMEOUT });
    await page.waitForTimeout(SCREENSHOT_TIMEOUT);
    await screenshots.capture('action-editor');
  });

  test('@@results - Results view', async ({ page, baseURL }) => {
    await page.goto(`${baseURL}${TEST_SURVEY_PATH}/@@results`);
    await page.waitForLoadState('networkidle');
    await expect(page.locator('#content-core')).toBeVisible({ timeout: SCREENSHOT_TIMEOUT });
    await page.waitForTimeout(SCREENSHOT_TIMEOUT);
    await screenshots.capture('action-results');
  });

  test('@@dashboard - Dashboard view', async ({ page, baseURL }) => {
    await page.goto(`${baseURL}${TEST_SURVEY_PATH}/@@dashboard`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(8000); // 8 seconds for dashboard charts to fully render
    await screenshots.capture('action-dashboard');
  });

  test('@@form-versions - Versions management', async ({ page, baseURL }) => {
    await page.goto(`${baseURL}${TEST_SURVEY_PATH}/@@form-versions`);
    await page.waitForLoadState('networkidle');
    await expect(page.locator('#content-core')).toBeVisible({ timeout: SCREENSHOT_TIMEOUT });
    await page.waitForTimeout(SCREENSHOT_TIMEOUT);
    await screenshots.capture('action-versions');
  });

  test('@@ai - AI Generator', async ({ page, baseURL }) => {
    await page.goto(`${baseURL}${TEST_SURVEY_PATH}/@@ai`);
    await page.waitForLoadState('networkidle');
    await expect(page.locator('#content-core')).toBeVisible({ timeout: SCREENSHOT_TIMEOUT });
    await page.waitForTimeout(SCREENSHOT_TIMEOUT);
    await screenshots.capture('action-ai-generator');
  });

  test('@@pdf-form - PDF Form', async ({ page, baseURL }) => {
    await page.goto(`${baseURL}${TEST_SURVEY_PATH}/@@pdf-form`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(SCREENSHOT_TIMEOUT);
    await screenshots.capture('action-pdf-form');
  });

  test('@@pdf-importer - Form from PDF', async ({ page, baseURL }) => {
    await page.goto(`${baseURL}${TEST_SURVEY_PATH}/@@pdf-importer`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(SCREENSHOT_TIMEOUT);
    await screenshots.capture('action-pdf-importer');
  });

  test('@@chatbot - Documentation Chatbot', async ({ page, baseURL }) => {
    await page.goto(`${baseURL}${TEST_SURVEY_PATH}/@@chatbot`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(SCREENSHOT_TIMEOUT);
    await screenshots.capture('action-chatbot');
  });
});

test.describe('Survey Metadata - All Fieldsets', () => {
  let screenshots: ScreenshotHelper;

  test.beforeEach(({ page }, testInfo) => {
    screenshots = new ScreenshotHelper(page, testInfo, 'survey-metadata');
  });

  // Use test.describe.serial to run these tests sequentially (not in parallel)
  // since they interact with the same page navigation
  test.describe.serial('Metadata fieldsets navigation', () => {
    
    test('Metadata - Basics fieldset', async ({ page, baseURL }) => {
      await page.goto(`${baseURL}${TEST_SURVEY_PATH}/@@survey-metadata`);
      await page.waitForLoadState('networkidle');
      
      // Wait for SurveyJS form to load
      await expect(page.locator('.sd-container-modern')).toBeVisible({ timeout: SCREENSHOT_TIMEOUT });
      await page.waitForTimeout(SCREENSHOT_TIMEOUT);
      
      // Basics is the default page, just capture
      await screenshots.capture('metadata-basics');
    });

    test('Metadata - Dates fieldset', async ({ page, baseURL }) => {
      // Navigate to page first (if not already there from previous test)
      const currentUrl = page.url();
      if (!currentUrl.includes('@@survey-metadata')) {
        await page.goto(`${baseURL}${TEST_SURVEY_PATH}/@@survey-metadata`);
        await page.waitForLoadState('networkidle');
        await expect(page.locator('.sd-container-modern')).toBeVisible({ timeout: SCREENSHOT_TIMEOUT });
        await page.waitForTimeout(SCREENSHOT_TIMEOUT);
      }
      
      // Click on "Dates" in the navigation - use more reliable selector
      const datesNav = page.getByRole('menuitemradio', { name: 'Dates' });
      await datesNav.waitFor({ state: 'visible', timeout: SCREENSHOT_TIMEOUT });
      await datesNav.click();
      await page.waitForTimeout(1000);
      
      await screenshots.capture('metadata-dates');
    });

    test('Metadata - Actions fieldset', async ({ page, baseURL }) => {
      const currentUrl = page.url();
      if (!currentUrl.includes('@@survey-metadata')) {
        await page.goto(`${baseURL}${TEST_SURVEY_PATH}/@@survey-metadata`);
        await page.waitForLoadState('networkidle');
        await expect(page.locator('.sd-container-modern')).toBeVisible({ timeout: SCREENSHOT_TIMEOUT });
        await page.waitForTimeout(SCREENSHOT_TIMEOUT);
      }
      
      const actionsNav = page.getByRole('menuitemradio', { name: 'Actions' });
      await actionsNav.waitFor({ state: 'visible', timeout: SCREENSHOT_TIMEOUT });
      await actionsNav.click();
      await page.waitForTimeout(1000);
      
      await screenshots.capture('metadata-actions');
    });

    test('Metadata - Mail fieldset', async ({ page, baseURL }) => {
      const currentUrl = page.url();
      if (!currentUrl.includes('@@survey-metadata')) {
        await page.goto(`${baseURL}${TEST_SURVEY_PATH}/@@survey-metadata`);
        await page.waitForLoadState('networkidle');
        await expect(page.locator('.sd-container-modern')).toBeVisible({ timeout: SCREENSHOT_TIMEOUT });
        await page.waitForTimeout(SCREENSHOT_TIMEOUT);
      }
      
      const mailNav = page.getByRole('menuitemradio', { name: 'Mail', exact: true });
      await mailNav.waitFor({ state: 'visible', timeout: SCREENSHOT_TIMEOUT });
      await mailNav.click();
      await page.waitForTimeout(1000);
      
      await screenshots.capture('metadata-mail');
    });

    test('Metadata - Mail notifications fieldset', async ({ page, baseURL }) => {
      const currentUrl = page.url();
      if (!currentUrl.includes('@@survey-metadata')) {
        await page.goto(`${baseURL}${TEST_SURVEY_PATH}/@@survey-metadata`);
        await page.waitForLoadState('networkidle');
        await expect(page.locator('.sd-container-modern')).toBeVisible({ timeout: SCREENSHOT_TIMEOUT });
        await page.waitForTimeout(SCREENSHOT_TIMEOUT);
      }
      
      const notifNav = page.getByRole('menuitemradio', { name: 'Mail notifications' });
      await notifNav.waitFor({ state: 'visible', timeout: SCREENSHOT_TIMEOUT });
      await notifNav.click();
      await page.waitForTimeout(1000);
      
      await screenshots.capture('metadata-mail-notifications');
    });

    test('Metadata - Form settings fieldset', async ({ page, baseURL }) => {
      const currentUrl = page.url();
      if (!currentUrl.includes('@@survey-metadata')) {
        await page.goto(`${baseURL}${TEST_SURVEY_PATH}/@@survey-metadata`);
        await page.waitForLoadState('networkidle');
        await expect(page.locator('.sd-container-modern')).toBeVisible({ timeout: SCREENSHOT_TIMEOUT });
        await page.waitForTimeout(SCREENSHOT_TIMEOUT);
      }
      
      const settingsNav = page.getByRole('menuitemradio', { name: 'Form settings' });
      await settingsNav.waitFor({ state: 'visible', timeout: SCREENSHOT_TIMEOUT });
      await settingsNav.click();
      await page.waitForTimeout(1000);
      
      await screenshots.capture('metadata-form-settings');
    });
  });
});
