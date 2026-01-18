import { test, expect } from '@playwright/test';

test('welcome page shows demo links', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Privacy Forms Studio' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Event registration' })).toBeVisible();
});

test('event registration viewer loads', async ({ page }) => {
  await page.goto('/en/demos/event-registration/@@viewer');
  await expect(page.locator('#surveyContainer')).toHaveCount(1);
  await expect(page.locator('.survey-actions')).toHaveCount(0);
});

test('german demo survey is reachable', async ({ page }) => {
  await page.goto('/de/demos/event-registration-de/@@viewer');
  await expect(page).toHaveTitle(/Veranstaltungsanmeldung/);
});
