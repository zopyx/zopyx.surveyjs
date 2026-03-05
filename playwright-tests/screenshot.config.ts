import { defineConfig, devices } from '@playwright/test';
import path from 'path';
import { SCREENSHOT_TIMEOUT } from './utils/screenshot-helpers';

/**
 * Playwright configuration for automated screenshots.
 * 
 * Usage:
 *   cd playwright-tests && npx playwright test --config=screenshot.config.ts
 * 
 * Environment variables:
 *   - PLONE_URL: Base URL of the Plone instance (default: http://localhost:8082/demo)
 *   - PLONE_ADMIN_USER: Admin username (default: admin2)
 *   - PLONE_ADMIN_PASS: Admin password (default: 2admin)
 *   - SCREENSHOT_DIR: Output directory for screenshots (default: ./screenshots/output)
 */

const ploneUrl = process.env.PLONE_URL || 'http://localhost:8082/demo';
const screenshotDir = process.env.SCREENSHOT_DIR || './screenshots/output';

// Debug: Log the configuration being used
console.log('[Playwright Config] PLONE_URL:', ploneUrl);
console.log('[Playwright Config] SCREENSHOT_DIR:', screenshotDir);

export default defineConfig({
  testDir: './screenshots',
  outputDir: path.join(screenshotDir, 'test-results'),
  
  // Screenshot tests should be fully sequential to avoid conflicts
  fullyParallel: false,
  workers: 2,
  
  retries: 1,
  
  reporter: [
    ['list'],
    ['html', { outputFolder: path.join(screenshotDir, 'report') }],
  ],
  
  use: {
    baseURL: ploneUrl,
    
    // Browser settings optimized for consistent screenshots
    viewport: { width: 1920, height: 1080 },
    deviceScaleFactor: 1,
    
    screenshot: 'on',
    video: 'off',
    
    // Disable animations for consistent captures
    animations: 'disabled',
    
    // Wait for network to be idle before taking screenshots
    actionTimeout: SCREENSHOT_TIMEOUT,
    navigationTimeout: SCREENSHOT_TIMEOUT,
    
    trace: 'on-first-retry',
  },

  projects: [
    {
      name: 'setup',
      testMatch: /auth\.setup\.ts/,
      use: {
        baseURL: ploneUrl,
      },
    },
    {
      name: 'screenshots-chromium',
      use: { 
        ...devices['Desktop Chrome'],
        // Explicitly set viewport for landscape, min 1400px wide
        viewport: { width: 1920, height: 1080 },
        deviceScaleFactor: 1,
        isMobile: false,
        hasTouch: false,
        // Preserve baseURL from root config
        baseURL: ploneUrl,
        // Storage state from auth setup
        storageState: './screenshots/.auth/admin.json',
      },
      dependencies: ['setup'],
    },
  ],
});
