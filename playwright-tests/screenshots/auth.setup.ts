import { test as setup, expect } from '@playwright/test';
import path from 'path';
import fs from 'fs';

const authFile = path.join(__dirname, '.auth', 'admin.json');

// Ensure auth directory exists
fs.mkdirSync(path.dirname(authFile), { recursive: true });

const adminUser = process.env.PLONE_ADMIN_USER || 'admin2';
const adminPass = process.env.PLONE_ADMIN_PASS || '2admin';

setup('authenticate as admin', async ({ browser, baseURL }) => {
  // Create context with specific origin to ensure cookies work correctly
  const context = await browser.newContext({
    baseURL: baseURL,
  });
  
  const page = await context.newPage();
  
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
  
  // Submit login form. Use the exact login button id: the header search
  // gadget form (with its own submit button) comes first in the DOM, so a
  // generic 'button[type="submit"]' click hits Search instead of logging in.
  await page.click('#buttons-login');
  
  // Wait for navigation - successful redirect goes to /demo or /demo/en
  await page.waitForURL(/\/demo(\/en)?$/, { timeout: 10000 });
  await page.waitForLoadState('networkidle');
  
  // Get cookies and update domain to include port if needed
  const cookies = await context.cookies();
  const modifiedCookies = cookies.map(cookie => {
    // For localhost cookies, we need to ensure they work with the port
    if (cookie.domain === 'localhost') {
      // Keep as localhost but ensure it works for all ports
      return cookie;
    }
    return cookie;
  });
  
  // Save storage state manually
  const storageState = await context.storageState();
  storageState.cookies = modifiedCookies;
  
  fs.writeFileSync(authFile, JSON.stringify(storageState, null, 2));
  
  console.log(`Authentication state saved to ${authFile}`);
  console.log(`Cookies saved: ${modifiedCookies.map(c => c.name).join(', ')}`);
  
  await context.close();
});
