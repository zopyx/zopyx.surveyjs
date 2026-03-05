import { defineConfig, devices } from '@playwright/test';
import path from 'path';

/**
 * Playwright configuration for automated screenshots.
 * 
 * Usage:
 *   cd playwright-tests && npx playwright test --config=screenshot.config.ts
 * 
 * Environment variables:
 *   - PLONE_URL: Base URL of the Plone instance (default: http://localhost:8082/demo)
 *   - PLONE_ADMIN_USER: Admin username (default: admin)
 *   - PLONE_ADMIN_PASS: Admin password (default: admin)
 *   - SCREENSHOT_DIR: Output directory for screenshots (default: ./screenshots/output)
 */

const ploneUrl = process.env.PLONE_URL || 'http://localhost:8082/demo';
const screenshotDir = process.env.SCREENSHOT_DIR || './screenshots/output';

export default defineConfig({
  testDir: './screenshots',
  outputDir: path.join(screenshotDir, 'test-results'),
  
  // Screenshot tests should be fully sequential to avoid conflicts
  fullyParallel: false,
  workers: 1,
  
  // No retries for screenshots - we want deterministic results
  retries: 0,
  
  reporter: [
    ['list'],
    ['html', { outputFolder: path.join(screenshotDir, 'report') }],
  ],
  
  use: {
    baseURL: ploneUrl,
    
    // Browser settings optimized for consistent screenshots
    viewport: { width: 1920, height: 1080 },
    deviceScaleFactor: 1,
    
    // Screenshot settings
    screenshot: 'off', // We take manual screenshots
    
    // Disable animations for consistent captures
    animations: 'disabled',
    
    // Wait for network to be idle before taking screenshots
    actionTimeout: 10000,
    navigationTimeout: 30000,
    
    trace: 'on-first-retry',
  },

  projects: [
    {
      name: 'setup',
      testMatch: /auth\.setup\.ts/,
    },
    {
      name: 'screenshots-chromium',
      use: { 
        ...devices['Desktop Chrome'],
        // Storage state from auth setup
        storageState: './screenshots/.auth/admin.json',
      },
      dependencies: ['setup'],
    },
    // Optional: Mobile screenshots
    {
      name: 'screenshots-mobile',
      use: { 
        ...devices['iPhone 14 Pro Max'],
        storageState: './screenshots/.auth/admin.json',
      },
      dependencies: ['setup'],
    },
  ],
});
