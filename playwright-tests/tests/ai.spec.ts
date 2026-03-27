import { test, expect } from '@playwright/test';

const TEST_SURVEY_PATH = '/en/demos/prefilled';

async function loginAsFormsEditor(page, baseURL: string) {
  await page.goto(`${baseURL}/login`);

  const form = page.locator('#login-form form, form#login_form').first();
  await expect(form).toBeVisible();

  await form.locator('input[name="__ac_name"]').fill('forms');
  await form.locator('input[name="__ac_password"]').fill('formsarecool');

  await Promise.all([
    page.waitForLoadState('networkidle'),
    form.locator('input[type="submit"], button[type="submit"]').first().click(),
  ]);
}

test('@@ai view renders for editor', async ({ page, baseURL }) => {
  await loginAsFormsEditor(page, baseURL!);

  await page.goto(`${baseURL}${TEST_SURVEY_PATH}/@@ai`);
  await page.waitForLoadState('networkidle');

  await expect(page.locator('#aiUploadForm')).toBeVisible();
  await expect(page.locator('#aiChatForm')).toBeVisible();
  await expect(page.locator('.ai-header .page-headline')).toHaveText(/AI Assistant/i);
});
