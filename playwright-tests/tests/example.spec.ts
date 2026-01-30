import { test, expect } from '@playwright/test';

test('english demo viewer renders', async ({ page }) => {
  await page.goto('/demo/en/demos/event-registration/@@viewer');
  await expect(page.locator('#surveyContainer')).toHaveCount(1);
  await expect(page.locator('.survey-actions')).toHaveCount(0);
  await expect(page.locator('#surveyAccessError')).toBeHidden();
});
