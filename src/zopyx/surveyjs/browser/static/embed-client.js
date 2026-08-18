/**
 * Direct DOM Embedding Client for zopyx.surveyjs
 * Security-first implementation with Shadow DOM isolation
 * 
 * This file provides the standalone embed client that can be loaded
 * directly from the Plone server for direct DOM embedding of surveys.
 * 
 * Usage:
 *   <script src="https://plone-site.com/path/to/survey/@@embed-loader"></script>
 *   <surveyjs-embed 
 *     survey-url="https://plone-site.com/path/to/survey"
 *     token="YOUR_EMBED_TOKEN">
 *   </surveyjs-embed>
 */

(function() {
  'use strict';

  // Embedded CSS reset and base styles
  const EMBED_CSS = `
    :host {
      display: block;
      width: 100%;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    }
    .surveyjs-embed-container {
      width: 100%;
      min-height: 400px;
    }
    .surveyjs-embed-container * {
      box-sizing: border-box;
    }
    .surveyjs-error {
      color: #d32f2f;
      padding: 20px;
      text-align: center;
      background: #ffebee;
      border-radius: 8px;
      margin: 10px 0;
    }
    .surveyjs-success {
      color: #388e3c;
      padding: 20px;
      text-align: center;
      background: #e8f5e9;
      border-radius: 8px;
      margin: 10px 0;
    }
    .surveyjs-loading {
      padding: 40px;
      text-align: center;
      color: #666;
    }
    .surveyjs-spinner {
      display: inline-block;
      width: 40px;
      height: 40px;
      border: 3px solid #f3f3f3;
      border-top: 3px solid #3498db;
      border-radius: 50%;
      animation: spin 1s linear infinite;
    }
    @keyframes spin {
      0% { transform: rotate(0deg); }
      100% { transform: rotate(360deg); }
    }
  `;

  /**
   * Secure API client for communicating with Plone backend
   */
  class SecureAPIClient {
    constructor(baseUrl, token, origin) {
      this.baseUrl = baseUrl.replace(/\/$/, '');
      this.token = token;
      this.origin = origin;
    }

    /**
     * Fetch form configuration from server
     */
    async getFormConfig() {
      const response = await fetch(`${this.baseUrl}/@@embed-config`, {
        method: 'GET',
        credentials: 'include',
        headers: {
          'Accept': 'application/json',
          'X-Embed-Token': this.token,
          'Origin': this.origin,
        },
      });

      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.message || `Failed to load form: ${response.status}`);
      }

      return response.json();
    }

    /**
     * Submit form data to server
     */
    async submitForm(data, sessionId, csrfToken) {
      const formData = new FormData();
      formData.append('pollResult', JSON.stringify(data));
      formData.append('_authenticator', csrfToken);

      const response = await fetch(`${this.baseUrl}/@@save-poll`, {
        method: 'POST',
        credentials: 'include',
        body: formData,
        headers: {
          'X-Embed-Token': this.token,
          'X-Session-ID': sessionId,
          'Origin': this.origin,
        },
      });

      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.message || `Submission failed: ${response.status}`);
      }

      return response.json();
    }
  }

  /**
   * Web Component for embedding SurveyJS forms
   */
  class SurveyJSEmbed extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: 'open' });
      
      // Inject styles
      const style = document.createElement('style');
      style.textContent = EMBED_CSS;
      this.shadowRoot.appendChild(style);
      
      // Create container
      this.container = document.createElement('div');
      this.container.className = 'surveyjs-embed-container';
      this.shadowRoot.appendChild(this.container);
      
      // State
      this.survey = null;
      this.config = null;
      this.api = null;
    }

    static get observedAttributes() {
      return ['survey-url', 'token'];
    }

    async connectedCallback() {
      const baseUrl = this.getAttribute('survey-url');
      const token = this.getAttribute('token');
      
      if (!baseUrl || !token) {
        this.showError('Missing required attributes: survey-url, token');
        return;
      }

      // Show loading state
      this.showLoading();

      try {
        // Initialize API client
        this.api = new SecureAPIClient(baseUrl, token, window.location.origin);
        
        // Load form configuration
        this.config = await this.api.getFormConfig();
        
        // Initialize SurveyJS
        await this.initializeSurvey(this.config.form_json);
      } catch (error) {
        console.error('Survey embed error:', error);
        this.showError(error.message || 'Failed to load survey. Please try again.');
      }
    }

    async initializeSurvey(formJson) {
      // Ensure SurveyJS is loaded
      if (typeof Survey === 'undefined') {
        await this.loadSurveyJS();
      }

      // Create survey model
      this.survey = new Survey.Model(formJson);
      
      // Apply theme if available
      if (typeof SurveyTheme !== 'undefined' && SurveyTheme.LayeredDarkPanelless) {
        this.survey.applyTheme(SurveyTheme.LayeredDarkPanelless);
      }
      
      // Handle completion
      this.survey.onComplete.add(async (sender) => {
        this.showLoading('Submitting...');
        try {
          await this.api.submitForm(
            sender.data,
            this.config.session_id,
            this.config.csrf_token
          );
          this.showSuccess('Thank you for your submission!');
        } catch (error) {
          console.error('Submission error:', error);
          this.showError('Submission failed. Please try again.');
          // Re-render form
          this.survey.render(this.container);
        }
      });

      // Render
      this.survey.render(this.container);
    }

    loadSurveyJS() {
      return new Promise((resolve, reject) => {
        // Check if already loading
        if (window.__surveyJSLoading) {
          const checkInterval = setInterval(() => {
            if (typeof Survey !== 'undefined') {
              clearInterval(checkInterval);
              resolve();
            }
          }, 100);
          return;
        }

        window.__surveyJSLoading = true;

        // Load from CDN with fallback
        const script = document.createElement('script');
        script.src = 'https://unpkg.com/survey-core@3.0.0/survey.core.min.js';
        script.crossOrigin = 'anonymous';
        script.onload = () => {
          // Load theme
          const themeScript = document.createElement('script');
          themeScript.src = 'https://unpkg.com/survey-core@3.0.0/themes/index.min.js';
          themeScript.crossOrigin = 'anonymous';
          themeScript.onload = () => {
            window.__surveyJSLoading = false;
            resolve();
          };
          themeScript.onerror = () => {
            window.__surveyJSLoading = false;
            resolve(); // Continue without theme
          };
          document.head.appendChild(themeScript);
        };
        script.onerror = () => {
          window.__surveyJSLoading = false;
          reject(new Error('Failed to load SurveyJS'));
        };
        document.head.appendChild(script);
      });
    }

    showLoading(message = 'Loading survey...') {
      this.container.innerHTML = `
        <div class="surveyjs-loading">
          <div class="surveyjs-spinner"></div>
          <p>${this.escapeHtml(message)}</p>
        </div>
      `;
    }

    showError(message) {
      this.container.innerHTML = `
        <div class="surveyjs-error">
          <strong>Error</strong>
          <p>${this.escapeHtml(message)}</p>
        </div>
      `;
    }

    showSuccess(message) {
      this.container.innerHTML = `
        <div class="surveyjs-success">
          <strong>Success</strong>
          <p>${this.escapeHtml(message)}</p>
        </div>
      `;
    }

    escapeHtml(text) {
      if (!text) return '';
      const div = document.createElement('div');
      div.textContent = text;
      return div.innerHTML;
    }
  }

  // Register custom element
  if (!customElements.get('surveyjs-embed')) {
    customElements.define('surveyjs-embed', SurveyJSEmbed);
  }

  // Export for module systems
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { SurveyJSEmbed, SecureAPIClient };
  }
})();
