# Playwright Screenshot Automation Documentation

## Table of Contents
- [Overview](#overview)
- [Architecture](#architecture)
- [Setup and Installation](#setup-and-installation)
- [Configuration](#configuration)
- [Authentication System](#authentication-system)
- [Running Tests](#running-tests)
- [Screenshot Album Gallery](#screenshot-album-gallery)
- [Adding New Screenshot Tests](#adding-new-screenshot-tests)
- [Screenshots Reference](#screenshots-reference)
- [Troubleshooting](#troubleshooting)
- [Best Practices](#best-practices)

---

## Overview

The Playwright screenshot automation system provides automated visual regression testing and documentation screenshot generation for the zopyx.surveyjs Plone add-on. It captures consistent, high-quality screenshots of surveys, control panels, and Plone Survey Forms (PSF) interfaces across different view modes and device sizes.

### Key Features
- **Automated Authentication**: Secure login with persistent session storage
- **Multiple View Modes**: Desktop and mobile (iPhone 14 Pro Max) screenshots
- **Consistent Captures**: Disabled animations, fixed viewports, deterministic timing
- **Organized Output**: Structured screenshot directories with descriptive naming
- **Sequential Execution**: Tests run in order to avoid conflicts

---

## Architecture

### Directory Structure

```
playwright-tests/
├── screenshots/
│   ├── .auth/
│   │   └── admin.json          # Stored authentication state
│   ├── output/                  # Generated screenshots
│   │   ├── surveys/
│   │   ├── controlpanels/
│   │   └── psf/
│   ├── auth.setup.ts            # Authentication setup fixture
│   ├── survey-screenshots.spec.ts
│   ├── controlpanel-screenshots.spec.ts
│   └── psf-screenshots.spec.ts
├── screenshot.config.ts         # Playwright configuration
└── package.json
```

### Test Execution Flow

```
┌─────────────────────────────────────────────────────────────────┐
│  1. Setup Project (auth.setup.ts)                                │
│     - Launch browser                                             │
│     - Navigate to login page                                     │
│     - Handle demo auto-fill interference                         │
│     - Authenticate as admin                                      │
│     - Fix cookie domain for localhost:8082                       │
│     - Save storage state to .auth/admin.json                     │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  2. Screenshot Tests (dependent on setup)                        │
│     - Load stored authentication state                           │
│     - Navigate to target pages                                   │
│     - Wait for elements to be ready                              │
│     - Capture screenshots                                        │
│     - Save to organized output directories                       │
└─────────────────────────────────────────────────────────────────┘
```

---

## Setup and Installation

### Prerequisites
- Node.js 18+ and npm
- Plone instance running locally
- Demo site initialized with sample content

### Installation

```bash
cd playwright-tests

# Install dependencies
npm install

# Install Playwright browsers
npx playwright install chromium
```

### Plone Setup

Ensure your Plone instance is running and the demo site is initialized:

```bash
# Start Plone
bin/instance start

# Wait for startup, then initialize demo content
./bin/instance run src/zopyx/surveyjs/core/init_plone.py
```

**Important**: The initialization script creates an admin user `admin2` with password `2admin`. These credentials are hardcoded in both the initialization script and the Playwright authentication setup.

---

## Configuration

### Main Configuration File

**`playwright-tests/screenshot.config.ts`**

```typescript
import { defineConfig, devices } from '@playwright/test';
import path from 'path';

const ploneUrl = process.env.PLONE_URL || 'http://localhost:8082/demo';
const screenshotDir = process.env.SCREENSHOT_DIR || './screenshots/output';

export default defineConfig({
  testDir: './screenshots',
  outputDir: path.join(screenshotDir, 'test-results'),
  
  // Sequential execution - required for shared auth state
  fullyParallel: false,
  workers: 1,
  
  // Retry configuration
  retries: 0,
  
  // Reporting
  reporter: [
    ['list'], 
    ['html', { outputFolder: path.join(screenshotDir, 'report') }]
  ],
  
  // Default test settings
  use: {
    baseURL: ploneUrl,
    viewport: { width: 1920, height: 1080 },
    deviceScaleFactor: 1,
    screenshot: 'off',  // We handle screenshots manually
    animations: 'disabled',  // Ensure consistent captures
    actionTimeout: 10000,
    navigationTimeout: 30000,
    trace: 'on-first-retry',
  },
  
  // Project configurations
  projects: [
    {
      name: 'setup',
      testMatch: /auth\.setup\.ts/
    },
    {
      name: 'screenshots-chromium',
      use: { 
        ...devices['Desktop Chrome'], 
        storageState: './screenshots/.auth/admin.json' 
      },
      dependencies: ['setup'],
    },
    {
      name: 'screenshots-mobile',
      use: { 
        ...devices['iPhone 14 Pro Max'], 
        storageState: './screenshots/.auth/admin.json' 
      },
      dependencies: ['setup'],
    },
  ],
});
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PLONE_URL` | `http://localhost:8082/demo` | Base URL of the Plone site |
| `SCREENSHOT_DIR` | `./screenshots/output` | Output directory for screenshots |
| `PLONE_ADMIN_USER` | `admin2` | Admin username for authentication |
| `PLONE_ADMIN_PASS` | `2admin` | Admin password for authentication |

### NPM Scripts

```bash
# Run all screenshot tests
npm run screenshots

# Run with visible browser (for debugging)
npm run screenshots:headed

# Run in debug mode with step-through
npm run screenshots:debug

# Run with interactive UI mode
npm run screenshots:ui

# Run specific test suites
npm run screenshots:survey     # Survey screenshots only
npm run screenshots:psf        # Plone Survey Form screenshots only
npm run screenshots:cp         # Control panel screenshots only
```

---

## Authentication System

### The Challenge

The Plone login page includes JavaScript that auto-fills demo credentials (`forms`/`formsarecool`) for demonstration purposes. This interferes with Playwright's standard `fill()` method, causing authentication failures.

### The Solution

**`auth.setup.ts`** uses JavaScript injection to bypass the auto-fill:

```typescript
// Disable auto-fill and set values via JavaScript
await page.evaluate(({user, pass}) => {
  const nameField = document.querySelector('input[name="__ac_name"]') as HTMLInputElement;
  const passField = document.querySelector('input[name="__ac_password"]') as HTMLInputElement;
  if (nameField) {
    nameField.value = user;
    nameField.dispatchEvent(new Event('input', { bubbles: true }));
  }
  if (passField) {
    passField.value = pass;
    passField.dispatchEvent(new Event('input', { bubbles: true }));
  }
}, { user: adminUser, pass: adminPass });
```

### Cookie Domain Fix

For localhost authentication to persist, cookies must include the port number:

```typescript
// Fix cookie domain to include port
const cookies = await context.cookies();
const fixedCookies = cookies.map(c => ({
  ...c,
  domain: c.domain === 'localhost' ? 'localhost:8082' : c.domain
}));
await context.clearCookies();
await context.addCookies(fixedCookies);
```

### Authentication State Storage

After successful login, the authentication state is saved to `screenshots/.auth/admin.json` and loaded for all subsequent tests:

```typescript
// In screenshot.config.ts
use: { 
  storageState: './screenshots/.auth/admin.json' 
}
```

---

## Running Tests

### Full Test Suite

```bash
cd playwright-tests
npm run screenshots
```

### Specific Projects

```bash
# Desktop screenshots only
npx playwright test --config=screenshot.config.ts --project=screenshots-chromium

# Mobile screenshots only  
npx playwright test --config=screenshot.config.ts --project=screenshots-mobile
```

### Debug Mode

When tests fail, use debug mode to inspect the browser state:

```bash
# Run with visible browser
npm run screenshots:headed

# Run with step-through debugging
npm run screenshots:debug

# Run with interactive UI
npm run screenshots:ui
```

### Viewing Results

Screenshots are saved to:
- **Surveys**: `playwright-tests/screenshots/output/surveys/`
- **Control Panels**: `playwright-tests/screenshots/output/controlpanels/`
- **Plone Survey Forms**: `playwright-tests/screenshots/output/psf/`

HTML report is available at:
```
playwright-tests/screenshots/output/report/index.html
```

### Screenshot Album Gallery

The screenshot album provides a beautiful, interactive gallery to browse all screenshots:

**Features:**
- 📸 Thumbnail grid organized by category
- 🔍 Real-time search filtering
- ✨ "Latest Only" filter to see current versions
- 💻 Full-size lightbox with keyboard navigation (← → ESC)
- ⬇️ Download individual screenshots
- 📱 Responsive design

**Generate the album:**
```bash
# Generate HTML album from screenshots
make screenshots-album

# Or directly:
cd playwright-tests && npx tsx generate-album.ts
```

**View the album:**
```bash
# Serve with local HTTP server
make screenshots-view

# Or manually:
cd playwright-tests/screenshots/output && npx serve -p 3000
# Open http://localhost:3000
```

**Generated output:**
```
playwright-tests/screenshots/output/
├── index.html              # Album gallery (auto-generated)
├── survey-list-2024-...png
├── survey-list-latest.png  # Symlink to latest
├── metadata-basics-...png
└── ...
```

**Screenshot Groups:**
| Group | Description |
|-------|-------------|
| 📋 Survey Management | Survey list, add/edit forms |
| 📝 Forms | Form views and interactions |
| ⚡ Survey Actions | Viewer, editor, results, dashboard, metadata |
| ✅ Validation | Form validation states |
| 🎯 Demos | Demo surveys |

---

## Adding New Screenshot Tests

### Basic Test Structure

```typescript
import { test, expect } from '@playwright/test';
import path from 'path';

// Screenshot output configuration
const SCREENSHOT_DIR = './screenshots/output/custom';

function screenshotPath(name: string): string {
  return path.join(SCREENSHOT_DIR, `${name}.png`);
}

test('my new screenshot', async ({ page }) => {
  // Navigate to target page
  await page.goto('/demo/path/to/page');
  
  // Wait for content to be ready
  await page.waitForSelector('.my-content-class');
  
  // Optional: wait for any animations
  await page.waitForTimeout(500);
  
  // Capture screenshot
  await page.screenshot({
    path: screenshotPath('my-screenshot-name'),
    fullPage: false  // or true for full page
  });
});
```

### Best Practices for Test Writing

1. **Use specific selectors**: Avoid brittle selectors
   ```typescript
   // Good
   await page.locator('#surveyContainer').first().waitFor();
   
   // Avoid
   await page.locator('div').waitFor();
   ```

2. **Handle multiple matches**: Use `.first()` when multiple elements match
   ```typescript
   await expect(page.locator('#surveyContainer').first()).toBeVisible();
   ```

3. **Wait for readiness**: Always wait for elements before screenshot
   ```typescript
   await page.waitForLoadState('networkidle');
   await page.waitForSelector('.sd-container-modern');
   ```

4. **Consistent timing**: Use fixed delays for animations
   ```typescript
   await page.waitForTimeout(500);  // Allow render/animation to complete
   ```

5. **Organized naming**: Use descriptive, consistent names
   ```typescript
   // Format: {component}-{view}-{context}
   'survey-viewer-desktop.png'
   'survey-editor-mobile.png'
   ```

### Hiding Plone UI Elements

The `ScreenshotHelper` provides methods to hide Plone chrome for cleaner screenshots:

#### Hide Plone UI (toolbar, messages, footer)
```typescript
await screenshots.hidePloneUI();
await screenshots.capture('clean-view', { fullPage: true });
```

#### Hide only footer
```typescript
await screenshots.hideFooter();
await screenshots.capture('no-footer', { fullPage: true });
```

#### Capture content-only (automatically hides UI)
```typescript
// Hides toolbar, footer, header, and messages automatically
await screenshots.captureContentOnly('my-screenshot');
```

#### Capture specific element only
```typescript
// Screenshot just the survey form, no surrounding page
await screenshots.capture('survey-only', {
  element: '#surveyContainer'
});
```

#### Hide specific elements
```typescript
await screenshots.capture('custom', {
  fullPage: true,
  hideElements: [
    '#edit-zone',      // Plone toolbar
    '#portal-footer',  // Footer
    '.banner',         // Custom banner
  ]
});
```

#### Clip to region
```typescript
await screenshots.capture('clipped', {
  clip: {
    x: 0,
    y: 80,      // Skip top 80px (toolbar)
    width: 1920,
    height: 900 // Stop before footer
  }
});
```

### Example: Adding a New Survey Screenshot

```typescript
// In survey-screenshots.spec.ts

const TEST_SURVEY_PATH = '/demo/en/demos/your-survey';

test('survey-your-feature-desktop', async ({ page }) => {
  await page.goto(`${TEST_SURVEY_PATH}/@@viewer`);
  
  await expect(page.locator('#surveyContainer').first()).toBeVisible();
  await page.waitForTimeout(500);
  
  await page.screenshot({
    path: screenshotPath('survey-your-feature-desktop'),
  });
});
```

---

## Screenshots Reference

### Survey Screenshots

| Screenshot Name | Description | View Mode |
|-----------------|-------------|-----------|
| `survey-viewer-desktop` | SurveyJS viewer with live form | `@@viewer` |
| `survey-editor-desktop` | SurveyJS form builder | `@@edit` |
| `survey-json-desktop` | Raw JSON configuration | `@@json` |
| `survey-test-desktop` | Test/sandbox mode | `@@test` |
| `survey-summary-desktop` | Summary/analytics view | `@@summary` |
| `survey-actions-desktop` | Action buttons panel | `@@actions` |
| `survey-entries-desktop` | Form entries list | `@@entries` |
| `survey-view-main-desktop` | Main view rendering | `view` |

### Control Panel Screenshots

| Screenshot Name | Description |
|-----------------|-------------|
| `controlpanel-forms-settings-desktop` | Forms configuration settings |
| `controlpanel-overview-desktop` | Control panel overview page |

### Mobile Variants

All desktop screenshots have mobile equivalents with `-mobile` suffix, captured at iPhone 14 Pro Max viewport size (430×932).

---

## Troubleshooting

### Authentication Issues

**Problem**: Tests fail with "Unauthorized" errors

**Solutions**:
1. Check Plone is running: `bin/instance status`
2. Verify admin credentials in `init_plone.py` match `auth.setup.ts`
3. Delete auth state and re-run: `rm screenshots/.auth/admin.json`
4. Check cookie domain includes port in auth.setup.ts

### Demo Auto-fill Interference

**Problem**: Login page fills wrong credentials automatically

**Solution**: Already handled in auth.setup.ts via JavaScript injection. If still failing:
```typescript
// Add to auth.setup.ts before login
await page.evaluate(() => {
  // Disable demo auto-fill script
  window.DEMO_AUTO_FILL_DISABLED = true;
});
```

### Element Not Found Errors

**Problem**: `locator resolved to 2 elements` or similar

**Solution**: Use `.first()` or more specific selectors:
```typescript
// Instead of:
await page.locator('.sd-container-modern');

// Use:
await page.locator('.sd-container-modern').first();
// or
await page.locator('#surveyContainer .sd-container-modern');
```

### Screenshots Differ Between Runs

**Problem**: Screenshots have slight variations

**Solutions**:
1. Ensure `animations: 'disabled'` in config
2. Add consistent `waitForTimeout()` before screenshots
3. Use `fullPage: false` for consistent viewport captures
4. Check for dynamic content (timestamps, random IDs)

### Browser/Node Modules Issues

**Problem**: `Cannot find module` or browser launch errors

**Solution**:
```bash
cd playwright-tests
rm -rf node_modules package-lock.json
npm install
npx playwright install chromium
```

### Port Conflicts

**Problem**: Plone not accessible on expected port

**Solution**:
1. Check Plone is listening on correct port: `netstat -an | grep 8082`
2. Update `PLONE_URL` environment variable if needed
3. Check firewall/proxy settings

---

## Best Practices

### 1. Deterministic Captures
- Always disable animations in config
- Use fixed `waitForTimeout()` values
- Avoid screenshots of content with random elements (timestamps, UUIDs)

### 2. Test Independence
- Don't rely on state from previous tests
- Each test should be able to run standalone
- Use `test.beforeEach()` for common setup

### 3. Selector Stability
- Prefer ID selectors (`#elementId`)
- Use data-testid attributes when available
- Avoid text-based selectors (may change with i18n)

### 4. Output Organization
- Group screenshots by feature/component
- Use consistent naming conventions
- Version control screenshots for baseline comparisons

### 5. CI/CD Integration
```bash
# Example CI script
npm run screenshots
# Compare against baselines
# Fail build on significant differences
```

---

## Implementation Notes

### Why Sequential Execution?

Tests run with `workers: 1` and `fullyParallel: false` because:
1. Authentication state is shared across tests
2. Prevents race conditions with cookie/session handling
3. Consistent server-side state for deterministic captures

### Why JavaScript for Login?

The demo site's auto-fill script runs on DOMContentLoaded, overwriting Playwright's `fill()` values. JavaScript injection after page load bypasses this.

### Cookie Domain Workaround

Playwright's storage state doesn't include port numbers in cookie domains, but `localhost:8082` requires the port for proper cookie matching. The auth.setup.ts fixes this by manually updating cookie domains before saving state.

---

## Related Documentation

- [Playwright Documentation](https://playwright.dev/docs/intro)
- [EMBEDDING.md](./EMBEDDING.md) - SurveyJS embedding guide
- [DEVELOP.rst](./DEVELOP.rst) - Development setup
- [README.md](./README.md) - Project overview
