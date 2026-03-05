/**
 * Survey view screenshots
 * Captures all main survey views: viewer, editor, results, etc.
 */

import { test, expect } from '@playwright/test';
import { ScreenshotHelper, SCREENSHOT_TIMEOUT } from '../utils/screenshot-helpers';

// Test survey path relative to baseURL (e.g. http://localhost:8082/demo)
const TEST_SURVEY_PATH = '/en/demos/event-registration';

test.describe('Survey Main Views', () => {
  let screenshots: ScreenshotHelper;

  test.beforeEach(({ page }, testInfo) => {
    screenshots = new ScreenshotHelper(page, testInfo, 'survey');
  });

  test('@@view-main landing page', async ({ page, baseURL }) => {
    await page.goto(`${baseURL}${TEST_SURVEY_PATH}/@@view-main`);
    await page.waitForLoadState('networkidle');

    // Wait for any dynamic content to settle
    await page.waitForTimeout(SCREENSHOT_TIMEOUT);

    await screenshots.capture('view-main', { fullPage: true });
  });

  test('@@viewer - public survey form', async ({ page, baseURL }) => {
    await page.goto(`${baseURL}${TEST_SURVEY_PATH}/@@viewer`);
    await page.waitForLoadState('networkidle');

    // Wait for SurveyJS to render
    await expect(page.locator('#surveyContainer')).toBeVisible();
    await page.waitForTimeout(SCREENSHOT_TIMEOUT); // Extra time for animations

    await screenshots.capture('viewer', { fullPage: true });
  });

  test('@@editor - SurveyJS Creator', async ({ page, baseURL }) => {
    await page.goto(`${baseURL}${TEST_SURVEY_PATH}/@@editor`);
    await page.waitForLoadState('networkidle');

    // Wait for SurveyJS Creator to load
    await expect(page.locator('.svc-creator')).toBeVisible({ timeout: SCREENSHOT_TIMEOUT });
    await page.waitForTimeout(SCREENSHOT_TIMEOUT); // Creator takes time to fully render

    await screenshots.capture('editor', { fullPage: true });
  });

  test('@@results - submissions list', async ({ page, baseURL }) => {
    await page.goto(`${baseURL}${TEST_SURVEY_PATH}/@@results`);
    await page.waitForLoadState('networkidle');

    // Wait for results table to load
    await expect(page.locator('#content-core')).toBeVisible({ timeout: SCREENSHOT_TIMEOUT });
    await page.waitForTimeout(SCREENSHOT_TIMEOUT);

    await screenshots.capture('results', { fullPage: true });
  });

  test('@@ai - AI form generator', async ({ page, baseURL }) => {
    await page.goto(`${baseURL}${TEST_SURVEY_PATH}/@@ai`);
    await page.waitForLoadState('networkidle');

    await expect(page.locator('#content-core')).toBeVisible({ timeout: SCREENSHOT_TIMEOUT });
    await page.waitForTimeout(SCREENSHOT_TIMEOUT);

    await screenshots.capture('ai-generator', { fullPage: true });
  });

  test('@@form-versions - version management', async ({ page, baseURL }) => {
    await page.goto(`${baseURL}${TEST_SURVEY_PATH}/@@form-versions`);
    await page.waitForLoadState('networkidle');

    await expect(page.locator('#content-core')).toBeVisible({ timeout: SCREENSHOT_TIMEOUT });
    await page.waitForTimeout(SCREENSHOT_TIMEOUT);

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

  test('@@viewer - anonymous view', async ({ page, baseURL }) => {
    await page.goto(`${baseURL}${TEST_SURVEY_PATH}/@@viewer`);
    await page.waitForLoadState('networkidle');

    await expect(page.locator('#surveyContainer')).toBeVisible();
    await page.waitForTimeout(SCREENSHOT_TIMEOUT);

    await screenshots.capture('viewer-anonymous', { fullPage: true });
  });
});
