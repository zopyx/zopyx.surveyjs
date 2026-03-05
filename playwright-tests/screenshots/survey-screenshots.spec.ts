/**
 * Survey view screenshots
 * Captures all main survey views: viewer, editor, results, etc.
 */

import { test, expect } from '@playwright/test';
import { ScreenshotHelper } from '../utils/screenshot-helpers';

// Test survey path - adjust to an existing survey in your Plone instance
const TEST_SURVEY_PATH = '/demo/en/demos/event-registration';

test.describe('Survey Main Views', () => {
  let screenshots: ScreenshotHelper;

  test.beforeEach(({ page }, testInfo) => {
    screenshots = new ScreenshotHelper(page, testInfo, 'survey');
  });

  test('@@view-main landing page', async ({ page }) => {
    await page.goto(`${TEST_SURVEY_PATH}/@@view-main`);
    await page.waitForLoadState('networkidle');
    
    // Wait for any dynamic content to settle
    await page.waitForTimeout(500);
    
    await screenshots.capture('view-main', { fullPage: true });
  });

  test('@@viewer - public survey form', async ({ page }) => {
    await page.goto(`${TEST_SURVEY_PATH}/@@viewer`);
    await page.waitForLoadState('networkidle');
    
    // Wait for SurveyJS to render
    await expect(page.locator('#surveyContainer, .sd-container-modern')).toBeVisible();
    await page.waitForTimeout(1000); // Extra time for animations
    
    await screenshots.capture('viewer', { fullPage: true });
  });

  test('@@editor - SurveyJS Creator', async ({ page }) => {
    await page.goto(`${TEST_SURVEY_PATH}/@@editor`);
    await page.waitForLoadState('networkidle');
    
    // Wait for SurveyJS Creator to load
    await expect(page.locator('.svc-creator')).toBeVisible({ timeout: 15000 });
    await page.waitForTimeout(2000); // Creator takes time to fully render
    
    await screenshots.capture('editor', { fullPage: true });
  });

  test('@@results - submissions list', async ({ page }) => {
    await page.goto(`${TEST_SURVEY_PATH}/@@results`);
    await page.waitForLoadState('networkidle');
    
    // Wait for results table to load
    await expect(page.locator('.results-table, table, .survey-results')).toBeVisible({ timeout: 10000 });
    await page.waitForTimeout(500);
    
    await screenshots.capture('results', { fullPage: true });
  });

  test('@@ai - AI form generator', async ({ page }) => {
    await page.goto(`${TEST_SURVEY_PATH}/@@ai`);
    await page.waitForLoadState('networkidle');
    
    await expect(page.locator('.ai-generator, [data-testid="ai-generator"]')).toBeVisible({ timeout: 10000 });
    await page.waitForTimeout(500);
    
    await screenshots.capture('ai-generator', { fullPage: true });
  });

  test('@@form-versions - version management', async ({ page }) => {
    await page.goto(`${TEST_SURVEY_PATH}/@@form-versions`);
    await page.waitForLoadState('networkidle');
    
    await expect(page.locator('.version-list, .form-versions')).toBeVisible({ timeout: 10000 });
    await page.waitForTimeout(500);
    
    await screenshots.capture('form-versions', { fullPage: true });
  });
});

test.describe('Survey Anonymous Views', () => {
  // Tests for anonymous/public views (no auth required)
  
  test.use({ storageState: undefined }); // Don't use authenticated state

  let screenshots: ScreenshotHelper;

  test.beforeEach(({ page }, testInfo) => {
    screenshots = new ScreenshotHelper(page, testInfo, 'survey-anon');
  });

  test('@@viewer - anonymous view', async ({ page }) => {
    await page.goto(`${TEST_SURVEY_PATH}/@@viewer`);
    await page.waitForLoadState('networkidle');
    
    await expect(page.locator('#surveyContainer, .sd-container-modern')).toBeVisible();
    await page.waitForTimeout(1000);
    
    await screenshots.capture('viewer-anonymous', { fullPage: true });
  });
});
