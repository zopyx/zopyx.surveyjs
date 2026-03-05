/**
 * Screenshot Helper Utilities
 * Provides consistent screenshot capture with naming conventions
 */

import { Page, TestInfo } from '@playwright/test';

export const SCREENSHOT_TIMEOUT = 2500;
import path from 'path';
import fs from 'fs';

export interface ScreenshotOptions {
  /** Take full page screenshot (default: false) */
  fullPage?: boolean;
  /** Specific element to screenshot */
  element?: string;
  /** Additional suffix for filename */
  suffix?: string;
  /** Custom viewport size for this screenshot */
  viewport?: { width: number; height: number };
  /** Hide elements before screenshot (selectors) */
  hideElements?: string[];
  /** Clip screenshot to specific region */
  clip?: { x: number; y: number; width: number; height: number };
  /** Show Plone UI elements (default: false - UI is hidden) */
  showPloneUI?: boolean;
}

export class ScreenshotHelper {
  private page: Page;
  private testInfo: TestInfo;
  private category: string;
  private outputDir: string;

  constructor(page: Page, testInfo: TestInfo, category: string = 'general') {
    this.page = page;
    this.testInfo = testInfo;
    this.category = category;
    
    // Use environment variable or default
    const baseDir = process.env.SCREENSHOT_DIR || './screenshots/output';
    this.outputDir = path.resolve(baseDir);
    
    // Ensure output directory exists
    fs.mkdirSync(this.outputDir, { recursive: true });
    
    // Output video path if video recording is enabled
    this.logVideoPath();
  }
  
  /**
   * Log the video file path for this test
   */
  private logVideoPath(): void {
    const video = this.page.video();
    if (video) {
      // Generate expected video filename based on test info
      const testName = this.testInfo.title.replace(/[^a-z0-9]+/gi, '-');
      console.log(`[Video] Recording started for test: ${testName}`);
      
      // Video path is available after page closes, so we set up a listener
      video.path().then((videoPath: string) => {
        console.log(`[Video] Saved: ${videoPath}`);
      }).catch(() => {
        // Video path not yet available or error
      });
    }
  }

  /**
   * Generate a clean filename for the screenshot
   */
  private generateFilename(name: string, suffix?: string): string {
    const timestamp = new Date().toISOString().split('T')[0];
    const cleanName = name
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '');

    const parts = [
      this.category,
      cleanName,
      suffix,
      timestamp,
    ].filter(Boolean);

    return `${parts.join('-')}.png`;
  }

  /**
   * Capture a screenshot with consistent naming and options
   * By default, hides Plone UI elements (toolbar, footer, header, messages)
   */
  async capture(name: string, options: ScreenshotOptions = {}): Promise<string> {
    const filename = this.generateFilename(name, options.suffix);
    const filepath = path.join(this.outputDir, filename);

    // Ensure directory exists
    fs.mkdirSync(path.dirname(filepath), { recursive: true });

    // Handle viewport change if specified
    const originalViewport = this.page.viewportSize();
    if (options.viewport) {
      await this.page.setViewportSize(options.viewport);
    }

    // Hide Plone UI by default (unless showPloneUI is true)
    if (!options.showPloneUI) {
      // Use a single JavaScript evaluation to hide all UI elements at once
      await this.page.evaluate(() => {
        const selectors = [
          // Toolbar & messages
          '#edit-zone',
          '.portalMessage',
          '#global-statusmessage',
          '.notifications',
          '.pat-cookietrigger',
          // Footer elements
          '#portal-footer',
          '#portal-footer-wrapper',
          '.portal-footer',
          'footer',
          '#footer',
          '.site-footer',
          '.plone-footer',
          // Header elements
          '#portal-header',
          '#portal-top',
          '.navbar',
          '.site-header',
        ];
        selectors.forEach(selector => {
          document.querySelectorAll(selector).forEach((el: Element) => {
            (el as HTMLElement).style.display = 'none';
          });
        });
      }).catch(() => {
        // Ignore errors
      });
    }

    // Hide additional elements if specified
    const hiddenElements: string[] = [];
    if (options.hideElements) {
      for (const selector of options.hideElements) {
        const elements = await this.page.locator(selector).all();
        for (let i = 0; i < elements.length; i++) {
          const el = elements[i];
          const isVisible = await el.isVisible().catch(() => false);
          if (isVisible) {
            await el.evaluate((node: Element) => {
              (node as HTMLElement).style.visibility = 'hidden';
            });
            hiddenElements.push(`${selector}:nth-of-type(${i + 1})`);
          }
        }
      }
    }

    try {
      // Prepare screenshot options
      const screenshotOpts: Parameters<Page['screenshot']>[0] = {
        path: filepath,
        fullPage: options.fullPage ?? false,
      };

      if (options.clip) {
        screenshotOpts.clip = options.clip;
      }

      // Take screenshot of specific element or full page
      if (options.element) {
        const element = this.page.locator(options.element).first();
        await element.screenshot({ path: filepath });
      } else {
        await this.page.screenshot(screenshotOpts);
      }

      // Attach to test report
      await this.testInfo.attach(filename, {
        path: filepath,
        contentType: 'image/png',
      });

      // Create/update "latest" symlink
      const latestFilename = filename.replace(/-\d{4}-\d{2}-\d{2}\.png$/, '-latest.png');
      const latestPath = path.join(this.outputDir, latestFilename);
      try {
        fs.unlinkSync(latestPath);
      } catch {
        // Ignore if doesn't exist
      }
      try {
        fs.symlinkSync(filename, latestPath);
      } catch (err) {
        console.warn(`Failed to create symlink: ${latestPath}`, err);
      }

      console.log(`Screenshot saved: ${filepath}`);
      return filepath;

    } finally {
      // Restore hidden elements
      for (const selector of hiddenElements) {
        await this.page.locator(selector).evaluate((node: Element) => {
          (node as HTMLElement).style.visibility = '';
        });
      }

      // Restore original viewport
      if (options.viewport && originalViewport) {
        await this.page.setViewportSize(originalViewport);
      }
    }
  }

  /**
   * Capture screenshots at multiple viewport sizes
   */
  async captureResponsive(name: string, options: Omit<ScreenshotOptions, 'viewport'> = {}): Promise<string[]> {
    const viewports = [
      { width: 1920, height: 1080, suffix: 'desktop' },
      { width: 1366, height: 768, suffix: 'laptop' },
      { width: 768, height: 1024, suffix: 'tablet' },
      { width: 375, height: 812, suffix: 'mobile' },
    ];

    const paths: string[] = [];
    for (const vp of viewports) {
      const filepath = await this.capture(name, {
        ...options,
        viewport: { width: vp.width, height: vp.height },
        suffix: options.suffix ? `${options.suffix}-${vp.suffix}` : vp.suffix,
      });
      paths.push(filepath);
    }

    return paths;
  }

  /**
   * Capture element before and after an action
   */
  async captureBeforeAfter(
    name: string,
    action: () => Promise<void>,
    element?: string
  ): Promise<{ before: string; after: string }> {
    const before = await this.capture(`${name}-before`, { element });
    await action();
    await this.page.waitForTimeout(500);
    const after = await this.capture(`${name}-after`, { element });
    
    return { before, after };
  }

  /**
   * Wait for SurveyJS to be fully loaded
   */
  async waitForSurveyJS(): Promise<void> {
    // Wait for SurveyJS container
    await this.page.waitForSelector('#surveyContainer, .sd-container-modern, .svc-creator', {
      state: 'visible',
      timeout: 15000,
    });

    // Wait for any loading indicators to disappear
    await this.page.waitForFunction(() => {
      const loaders = document.querySelectorAll('.loading, .spinner, [class*="loading"]');
      return loaders.length === 0 || Array.from(loaders).every(el => 
        el instanceof HTMLElement && el.offsetParent === null
      );
    }, { timeout: 10000 });

    // Additional wait for animations
    await this.page.waitForTimeout(500);
  }

  /**
   * Hide Plone UI elements for cleaner screenshots
   * @param options - Options for what to hide
   */
  async hidePloneUI(options?: { hideFooter?: boolean }): Promise<void> {
    const selectorsToHide = [
      '#edit-zone',           // Toolbar
      '.portalMessage',       // Status messages
      '#global-statusmessage', // Global messages
      '.notifications',       // Notifications
      '.pat-cookietrigger',   // Cookie notice
    ];

    for (const selector of selectorsToHide) {
      await this.page.locator(selector).evaluate((el: Element) => {
        (el as HTMLElement).style.display = 'none';
      }).catch(() => {
        // Element not found, ignore
      });
    }

    // Hide footer if requested (or by default)
    if (options?.hideFooter !== false) {
      await this.hideFooter();
    }
  }

  /**
   * Hide footer elements
   */
  async hideFooter(): Promise<void> {
    const footerSelectors = [
      '#portal-footer',           // Plone 5/6 footer
      '#portal-footer-wrapper',   // Alternative footer wrapper
      '.portal-footer',           // Generic footer class
      'footer',                   // HTML5 footer element
      '#footer',                  // Common footer ID
      '.site-footer',             // Bootstrap/common footer class
      '.plone-footer',            // Plone-specific footer
    ];

    for (const selector of footerSelectors) {
      await this.page.locator(selector).evaluate((el: Element) => {
        (el as HTMLElement).style.display = 'none';
      }).catch(() => {
        // Element not found, ignore
      });
    }
  }

  /**
   * Capture content-only screenshot (hides Plone chrome)
   * @param name - Screenshot name
   * @param options - Additional screenshot options
   */
  async captureContentOnly(name: string, options: Omit<ScreenshotOptions, 'hideElements'> = {}): Promise<string> {
    // Hide all Plone UI including footer
    await this.hidePloneUI({ hideFooter: true });

    // Also hide common header/nav elements
    const headerSelectors = [
      '#portal-header',           // Plone header
      '#portal-top',              // Top area
      '.navbar',                  // Bootstrap nav
      '.site-header',             // Common header class
    ];

    for (const selector of headerSelectors) {
      await this.page.locator(selector).evaluate((el: Element) => {
        (el as HTMLElement).style.display = 'none';
      }).catch(() => {
        // Element not found, ignore
      });
    }

    // Capture the screenshot
    return this.capture(name, {
      ...options,
      fullPage: options.fullPage ?? true,
    });
  }

  /**
   * Capture just the main content area
   * @param name - Screenshot name
   * @param contentSelector - CSS selector for content area (default: #content or #content-core)
   * @param options - Additional screenshot options
   */
  async captureContentArea(
    name: string,
    contentSelector: string = '#content, #content-core, main, article, [role="main"]',
    options: ScreenshotOptions = {}
  ): Promise<string> {
    // Try to find the content element
    const contentLocators = contentSelector.split(',').map(s => this.page.locator(s.trim()).first());
    
    for (const locator of contentLocators) {
      const isVisible = await locator.isVisible().catch(() => false);
      if (isVisible) {
        // Hide UI chrome first
        await this.hidePloneUI({ hideFooter: true });
        
        // Capture just the content element
        return this.capture(name, {
          ...options,
          element: contentSelector,
        });
      }
    }

    // Fallback to full page if content element not found
    console.warn(`Content element not found: ${contentSelector}, falling back to full page`);
    return this.capture(name, options);
  }

  /**
   * Highlight an element before screenshot (for documentation)
   */
  async highlightElement(selector: string): Promise<void> {
    await this.page.locator(selector).evaluate((el: Element) => {
      const original = (el as HTMLElement).style.boxShadow;
      (el as HTMLElement).style.boxShadow = '0 0 0 4px rgba(255, 0, 0, 0.5)';
      (el as HTMLElement).dataset.originalBoxShadow = original;
    });
    await this.page.waitForTimeout(200);
  }

  /**
   * Remove highlight from element
   */
  async unhighlightElement(selector: string): Promise<void> {
    await this.page.locator(selector).evaluate((el: Element) => {
      const original = (el as HTMLElement).dataset.originalBoxShadow || '';
      (el as HTMLElement).style.boxShadow = original;
    }).catch(() => {
      // Element not found, ignore
    });
  }
}
