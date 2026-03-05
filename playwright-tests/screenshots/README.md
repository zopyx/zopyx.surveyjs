# Playwright Screenshot Automation

This directory contains Playwright tests specifically for capturing automated screenshots of the SurveyJS Plone add-on.

## Quick Start

```bash
cd playwright-tests

# Install dependencies (if not already done)
npm install

# Install Playwright browsers
npx playwright install chromium

# Run all screenshots
npm run screenshots

# Or run directly
npx playwright test --config=screenshot.config.ts
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PLONE_URL` | `http://localhost:8082/demo` | Base URL of Plone instance |
| `PLONE_ADMIN_USER` | `admin` | Admin username |
| `PLONE_ADMIN_PASS` | `admin` | Admin password |
| `SCREENSHOT_DIR` | `./screenshots/output` | Output directory for screenshots |

## Screenshot Categories

### Survey Views (`survey-screenshots.spec.ts`)
- `@@view-main` - Landing page for survey
- `@@viewer` - Public survey form
- `@@editor` - SurveyJS Creator
- `@@results` - Submissions list
- `@@ai` - AI form generator
- `@@form-versions` - Version management

### PSF Views (`psf-screenshots.spec.ts`)
- `@@pfs` - Privacy Forms Studio landing
- `@@survey-overview` - All forms overview
- `@@survey-templates-overview` - Templates
- `@@survey-monitor` - Monitoring dashboard

### Control Panel (`controlpanel-screenshots.spec.ts`)
- `@@forms-settings` - Main settings form
- `@@overview-controlpanel` - Site setup overview

## Running Specific Screenshots

```bash
# Run only survey screenshots
npx playwright test screenshots/survey-screenshots.spec.ts --config=screenshot.config.ts

# Run only PSF screenshots
npx playwright test screenshots/psf-screenshots.spec.ts --config=screenshot.config.ts

# Run only control panel
npx playwright test screenshots/controlpanel-screenshots.spec.ts --config=screenshot.config.ts

# Run with headed browser (to see what's happening)
npx playwright test --config=screenshot.config.ts --headed

# Run specific test by title
npx playwright test -g "viewer" --config=screenshot.config.ts
```

## Output Structure

```
screenshots/output/
├── survey-view-main-2024-01-15.png
├── survey-viewer-2024-01-15.png
├── survey-editor-2024-01-15.png
├── psf-pfs-admin-2024-01-15.png
├── controlpanel-forms-settings-2024-01-15.png
└── report/
    └── index.html
```

## Customization

### Adding New Screenshots

1. Create a new spec file in `screenshots/` or add to existing
2. Use the `ScreenshotHelper` class for consistent naming

```typescript
import { test } from '@playwright/test';
import { ScreenshotHelper } from '../utils/screenshot-helpers';

test('my new view', async ({ page }, testInfo) => {
  const screenshots = new ScreenshotHelper(page, testInfo, 'custom');
  await page.goto('/@@my-view');
  await screenshots.capture('my-view', { fullPage: true });
});
```

### Responsive Screenshots

Capture at multiple viewport sizes:

```typescript
await screenshots.captureResponsive('my-view', { fullPage: true });
// Generates: my-view-desktop.png, my-view-laptop.png, my-view-tablet.png, my-view-mobile.png
```

### Hide UI Elements

For cleaner documentation screenshots:

```typescript
await screenshots.hidePloneUI();
await screenshots.capture('clean-view');
```

### Highlight Elements

For documentation with emphasis:

```typescript
await screenshots.highlightElement('.important-button');
await screenshots.capture('with-highlight');
await screenshots.unhighlightElement('.important-button');
```

## CI/CD Integration

For automated screenshot generation in CI:

```yaml
# Example GitHub Actions step
- name: Generate Screenshots
  run: |
    cd playwright-tests
    npx playwright test --config=screenshot.config.ts
  env:
    PLONE_URL: http://localhost:8080/Plone
    PLONE_ADMIN_USER: admin
    PLONE_ADMIN_PASS: secret
    
- name: Upload Screenshots
  uses: actions/upload-artifact@v4
  with:
    name: screenshots
    path: playwright-tests/screenshots/output/
```

## Troubleshooting

### Screenshots are blank/white
- Increase `actionTimeout` and `navigationTimeout` in config
- Add more `page.waitForTimeout()` after navigation
- Check if elements need to be waited for explicitly

### Authentication fails
- Delete `screenshots/.auth/` directory to force re-auth
- Check credentials in environment variables
- Verify login form selectors match your Plone theme

### Elements not found
- Check if the survey/content exists at the test path
- Adjust selectors in test files to match your theme
- Use Playwright codegen to find correct selectors:
  ```bash
  npx playwright codegen http://localhost:8082/demo
  ```
