import { test, expect } from '@playwright/test';
import { ai } from '@zerostep/playwright';

test('english demo viewer renders', async ({ page }) => {
  await page.goto('/demo/en/demos/event-registration/@@viewer');
  await expect(page.locator('#surveyContainer')).toHaveCount(1);
  await expect(page.locator('.survey-actions')).toHaveCount(0);
  await expect(page.locator('#surveyAccessError')).toBeHidden();
  await ai('Fill "Full name" with "Andreas Jung".', { page, test });
  await ai('Fill "Email" with "yet@gmx.de".', { page, test });
  await ai('Select "VIP" for "Ticket type".', { page, test });
  await ai('Click "Yes".', { page, test });
  await ai('Scroll down to the submit area.', { page, test });
  await ai('Click the "Complete" button to submit the survey.', { page, test });
  await page.screenshot({ path: 'test-results/english-demo-viewer.png', fullPage: true });
  await page.screenshot({ path: 'test-results/after-complete.png', fullPage: true });
});
