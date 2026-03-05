import { test as setup, expect } from '@playwright/test';
import path from 'path';
import fs from 'fs';

const authFile = path.join(__dirname, '.auth', 'admin.json');

// Ensure auth directory exists
fs.mkdirSync(path.dirname(authFile), { recursive: true });

const adminUser = process.env.PLONE_ADMIN_USER || 'admin2';
const adminPass = process.env.PLONE_ADMIN_PASS || '2admin';

setup('authenticate as admin', async ({ page, baseURL }) => {
  // Navigate to login form
  const loginUrl = `${baseURL}/login_form`;
  await page.goto(loginUrl);
  
  // Wait for page to fully load
  await page.waitForLoadState('networkidle');
  
  // Wait for auto-fill script to complete (it runs on DOMContentLoaded)
  await page.waitForTimeout(2000);
  
  // Set values directly via JavaScript after auto-fill has run
  await page.evaluate(({ user, pass }: { user: string; pass: string }) => {
    const nameField = document.querySelector('input[name="__ac_name"]') as HTMLInputElement;
    const passField = document.querySelector('input[name="__ac_password"]') as HTMLInputElement;
    if (nameField) {
      nameField.value = user;
      nameField.dispatchEvent(new Event('input', { bubbles: true }));
      nameField.dispatchEvent(new Event('change', { bubbles: true }));
    }
    if (passField) {
      passField.value = pass;
      passField.dispatchEvent(new Event('input', { bubbles: true }));
      passField.dispatchEvent(new Event('change', { bubbles: true }));
    }
  }, { user: adminUser, pass: adminPass });
  
  // Submit login form
  await page.click('button[type="submit"]');
  
  // Wait for navigation - successful redirect goes to /demo or /demo/en
  await page.waitForURL(/\/demo(\/en)?$/, { timeout: 10000 });
  await page.waitForLoadState('networkidle');
  
  // Get cookies and modify domain to include port if needed
  const cookies = await page.context().cookies();
  const modifiedCookies = cookies.map(cookie => {
    // If cookie is for localhost without port, also add version with port
    if (cookie.domain === 'localhost' && !cookie.domain.includes(':')) {
      return {
        ...cookie,
        domain: 'localhost',
      };
    }
    return cookie;
  });
  
  // Save storage state manually to ensure cookies are correct
  const storageState = await page.context().storageState();
  storageState.cookies = modifiedCookies;
  
  fs.writeFileSync(authFile, JSON.stringify(storageState, null, 2));
  
  console.log(`Authentication state saved to ${authFile}`);
});
