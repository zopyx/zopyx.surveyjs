/**
 * SurveyJS Embed Library
 *
 * Allows embedding of SurveyJS forms into external websites.
 *
 * Usage:
 * 1. Include this script in your HTML:
 *    <script src="https://your-site.com/++resource++zopyx.surveyjs/embed.js"></script>
 *
 * 2. Add a container div with the survey URL:
 *    <div class="surveyjs-embed"
 *         data-survey-url="https://your-site.com/survey1"
 *         data-height="600px"
 *         data-width="100%">
 *    </div>
 *
 * Options:
 * - data-survey-url: Required. Full URL to the survey
 * - data-height: Optional. Height of the iframe (default: 600px)
 * - data-width: Optional. Width of the iframe (default: 100%)
 * - data-auto-resize: Optional. Auto-resize iframe to content (default: false)
 */

(function() {
  'use strict';

  // Configuration
  const CONFIG = {
    embedClass: 'surveyjs-embed',
    defaultHeight: '600px',
    defaultWidth: '100%',
    embedViewSuffix: '/@@viewer-embed',
    errorStyles: `
      padding: 20px;
      text-align: center;
      border: 2px solid #f44336;
      border-radius: 4px;
      background-color: #ffebee;
      color: #c62828;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    `,
    iframeStyles: `
      border: none;
      width: 100%;
      display: block;
    `
  };

  /**
   * Initialize all survey embeds on the page
   */
  function initializeEmbeds() {
    const containers = document.querySelectorAll('.' + CONFIG.embedClass);

    if (containers.length === 0) {
      console.warn('SurveyJS Embed: No embed containers found. Add elements with class "' + CONFIG.embedClass + '"');
      return;
    }

    containers.forEach(function(container) {
      embedSurvey(container);
    });
  }

  /**
   * Embed a survey into a container
   * @param {HTMLElement} container - The container element
   */
  function embedSurvey(container) {
    // Check if already embedded
    if (container.hasAttribute('data-embedded')) {
      return;
    }

    // Get configuration from data attributes
    const surveyUrl = container.getAttribute('data-survey-url');
    const height = container.getAttribute('data-height') || CONFIG.defaultHeight;
    const width = container.getAttribute('data-width') || CONFIG.defaultWidth;
    const autoResize = container.getAttribute('data-auto-resize') === 'true';

    // Validate survey URL
    if (!surveyUrl) {
      showError(container, 'Missing data-survey-url attribute. Please specify the survey URL.');
      return;
    }

    if (!isValidUrl(surveyUrl)) {
      showError(container, 'Invalid survey URL: ' + surveyUrl);
      return;
    }

    // Construct embed URL
    const embedUrl = getEmbedUrl(surveyUrl);

    // Create and configure iframe
    const iframe = document.createElement('iframe');
    iframe.src = embedUrl;
    iframe.style.cssText = CONFIG.iframeStyles;
    iframe.style.height = height;
    iframe.style.width = width;
    iframe.setAttribute('scrolling', 'auto');
    iframe.setAttribute('allowtransparency', 'true');
    iframe.setAttribute('title', 'Survey Form');

    // Add loading indicator
    container.innerHTML = '<div style="text-align: center; padding: 40px; color: #666;">Loading survey...</div>';

    // Handle iframe load
    iframe.addEventListener('load', function() {
      container.innerHTML = '';
      container.appendChild(iframe);
      container.setAttribute('data-embedded', 'true');

      // Setup auto-resize if enabled
      if (autoResize) {
        setupAutoResize(iframe);
      }
    });

    // Handle iframe errors
    iframe.addEventListener('error', function() {
      showError(container, 'Failed to load survey. Please check the URL and try again.');
    });

    // Check if embedding is allowed
    checkEmbeddingAllowed(embedUrl, function(allowed, error) {
      if (allowed) {
        container.innerHTML = '';
        container.appendChild(iframe);
      } else {
        showError(container, error || 'Survey embedding is not allowed. Please contact the survey administrator.');
      }
    });
  }

  /**
   * Get the embed URL from a survey URL
   * @param {string} surveyUrl - The survey URL
   * @returns {string} The embed URL
   */
  function getEmbedUrl(surveyUrl) {
    // Remove trailing slash
    surveyUrl = surveyUrl.replace(/\/$/, '');

    // Check if URL already contains the embed view
    if (surveyUrl.indexOf('@@viewer-embed') !== -1) {
      return surveyUrl;
    }

    // Append embed view suffix
    return surveyUrl + CONFIG.embedViewSuffix;
  }

  /**
   * Check if embedding is allowed for the survey
   * @param {string} embedUrl - The embed URL
   * @param {Function} callback - Callback function(allowed, error)
   */
  function checkEmbeddingAllowed(embedUrl, callback) {
    // Create a test iframe to check if embedding is allowed
    const testIframe = document.createElement('iframe');
    testIframe.style.display = 'none';
    testIframe.src = embedUrl;

    let loaded = false;
    let timeout = setTimeout(function() {
      if (!loaded) {
        document.body.removeChild(testIframe);
        callback(true); // Assume allowed if we can't check
      }
    }, 3000);

    testIframe.addEventListener('load', function() {
      loaded = true;
      clearTimeout(timeout);
      document.body.removeChild(testIframe);
      callback(true);
    });

    testIframe.addEventListener('error', function() {
      loaded = true;
      clearTimeout(timeout);
      document.body.removeChild(testIframe);
      callback(false, 'Failed to load survey');
    });

    document.body.appendChild(testIframe);
  }

  /**
   * Setup auto-resize for iframe
   * @param {HTMLIFrameElement} iframe - The iframe element
   */
  function setupAutoResize(iframe) {
    // Listen for messages from iframe
    window.addEventListener('message', function(event) {
      // Verify origin matches iframe src origin
      try {
        const iframeUrl = new URL(iframe.src);
        if (event.origin !== iframeUrl.origin) {
          return;
        }

        // Handle resize message
        if (event.data && event.data.type === 'surveyjs-resize') {
          const height = event.data.height;
          if (height && typeof height === 'number') {
            iframe.style.height = height + 'px';
          }
        }
      } catch (e) {
        console.error('SurveyJS Embed: Error handling resize message', e);
      }
    });

    // Request initial size
    try {
      iframe.contentWindow.postMessage({
        type: 'surveyjs-get-height'
      }, '*');
    } catch (e) {
      console.error('SurveyJS Embed: Error requesting height', e);
    }
  }

  /**
   * Show an error message in the container
   * @param {HTMLElement} container - The container element
   * @param {string} message - The error message
   */
  function showError(container, message) {
    container.innerHTML =
      '<div style="' + CONFIG.errorStyles + '">' +
      '<strong>Survey Embed Error</strong><br>' +
      '<span style="font-size: 14px;">' + escapeHtml(message) + '</span>' +
      '</div>';
    container.setAttribute('data-embedded', 'error');
  }

  /**
   * Validate URL
   * @param {string} url - The URL to validate
   * @returns {boolean} True if valid
   */
  function isValidUrl(url) {
    try {
      new URL(url);
      return true;
    } catch (e) {
      return false;
    }
  }

  /**
   * Escape HTML to prevent XSS
   * @param {string} text - The text to escape
   * @returns {string} Escaped text
   */
  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  /**
   * Public API
   */
  window.SurveyJSEmbed = {
    version: '1.0.0',

    /**
     * Manually initialize embeds
     */
    init: function() {
      initializeEmbeds();
    },

    /**
     * Embed a survey into a specific element
     * @param {HTMLElement|string} element - Element or selector
     * @param {Object} options - Embed options
     */
    embed: function(element, options) {
      if (typeof element === 'string') {
        element = document.querySelector(element);
      }

      if (!element) {
        console.error('SurveyJS Embed: Element not found');
        return;
      }

      // Apply options as data attributes
      if (options.surveyUrl) {
        element.setAttribute('data-survey-url', options.surveyUrl);
      }
      if (options.height) {
        element.setAttribute('data-height', options.height);
      }
      if (options.width) {
        element.setAttribute('data-width', options.width);
      }
      if (options.autoResize) {
        element.setAttribute('data-auto-resize', 'true');
      }

      // Add embed class if not present
      if (!element.classList.contains(CONFIG.embedClass)) {
        element.classList.add(CONFIG.embedClass);
      }

      embedSurvey(element);
    }
  };

  // Auto-initialize on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeEmbeds);
  } else {
    initializeEmbeds();
  }

})();
