# Playwright Screenshot Automation

This directory contains Playwright tests specifically for capturing automated screenshots of the SurveyJS Plone add-on.

## Quick Start

### Using Make (Recommended) - From Project Root

```bash
# Install dependencies (if not already done)
make screenshots-setup

# Run all screenshots (auto-starts/stops Plone if needed)
make screenshots

# Run specific categories
make screenshots-survey    # Survey views only
make screenshots-psf       # PSF views only
make screenshots-cp        # Control panel only
make screenshots-headed    # Run with visible browser
```

### Manual - From playwright-tests Directory

```bash
cd playwright-tests

# Install dependencies (if not already done)
npm install

# Install Playwright browsers
npx playwright install chromium

# Run all screenshots (auto-starts/stops Plone if needed)
./run-screenshots-with-plone.sh

# Or run directly (requires Plone to be already running)
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

## Automatic Plone Management

The `make screenshots*` targets automatically handle Plone startup and shutdown:

- **If Plone is NOT running**: The script starts Plone in the background, runs tests, then stops Plone
- **If Plone IS already running**: The script runs tests and leaves Plone running afterward

This is handled by the `run-screenshots-with-plone.sh` wrapper script.

### Running Specific Screenshots

```bash
# Using Make (from project root)
make screenshots-survey    # Survey screenshots only
make screenshots-psf       # PSF screenshots only
make screenshots-cp        # Control panel screenshots only
make screenshots-headed    # With visible browser

# Using npm/scripts (from playwright-tests directory)
npx playwright test screenshots/survey-screenshots.spec.ts --config=screenshot.config.ts
npx playwright test screenshots/psf-screenshots.spec.ts --config=screenshot.config.ts
npx playwright test screenshots/controlpanel-screenshots.spec.ts --config=screenshot.config.ts

# Run with headed browser (to see what's happening)
npx playwright test --config=screenshot.config.ts --headed

# Run specific test by title
npx playwright test -g "viewer" --config=screenshot.config.ts
```

### Raw Screenshot Targets (Plone must be running)

If you want to run screenshots without automatic Plone management:

```bash
make screenshots-raw           # All screenshots
make screenshots-raw-survey    # Survey only
make screenshots-raw-psf       # PSF only
make screenshots-raw-cp        # Control panel only
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

## Makefile Targets Reference

| Target | Description |
|--------|-------------|
| `make screenshots-setup` | Install Playwright dependencies and browsers |
| `make screenshots` | Run all screenshots (auto-manages Plone) |
| `make screenshots-survey` | Survey views only (auto-manages Plone) |
| `make screenshots-psf` | PSF views only (auto-manages Plone) |
| `make screenshots-cp` | Control panel only (auto-manages Plone) |
| `make screenshots-headed` | Run with visible browser (auto-manages Plone) |
| `make screenshots-raw` | Run all (Plone must be running) |
| `make screenshots-raw-*` | Raw variants for survey/psf/cp/headed |
| `make plone-start-for-tests` | Manually start Plone for tests |
| `make plone-stop-for-tests` | Manually stop Plone for tests |
