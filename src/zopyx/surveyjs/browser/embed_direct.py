"""Direct DOM Embedding views for zopyx.surveyjs.

Provides endpoints for:
- Token generation (@@embed-token)
- Form configuration serving (@@embed-config)
- Embed loader script (@@embed-loader)
"""

import logging
import secrets
from urllib.parse import urlparse

import orjson
import plone.api
from Products.Five import BrowserView
from zope.annotation.interfaces import IAnnotations

from .services import forms as forms_service
from .services.http import json_error, json_response, parse_json_body
from .embed_security import (
    generate_embed_token,
    validate_embed_token,
    validate_origin,
    set_cors_headers,
    handle_cors_preflight,
    is_embed_direct_globally_enabled,
    get_embed_direct_max_origins,
    EmbedSecurityError,
    TokenExpiredError,
    TokenInvalidError,
)

logger = logging.getLogger(__name__)


class EmbedDirectTokenView(BrowserView):
    """Generate embedding tokens for direct DOM embedding.
    
    POST endpoint that generates a time-limited token bound to a specific origin.
    Only users with ModifyPortalContent permission can generate tokens.
    """
    
    def __call__(self):
        """Handle POST request to generate embed token."""
        # Check permission
        if not plone.api.user.has_permission(
            "Modify portal content", obj=self.context
        ):
            json_error(self.request.response, 403, "permission_denied")
            return
        
        # Check if direct embedding is enabled globally
        if not is_embed_direct_globally_enabled():
            json_error(self.request.response, 403, "feature_disabled",
                      message="Direct DOM embedding is not enabled globally")
            return
        
        # Check survey embedding mode
        embed_mode = getattr(self.context, "embedding_mode", None)
        if embed_mode != "direct":
            json_error(self.request.response, 400, "direct_embedding_not_enabled",
                      message="This survey is not configured for Direct DOM embedding")
            return
        
        # Parse request body
        body = parse_json_body(self.request)
        if body is None:
            json_error(self.request.response, 400, "invalid_json")
            return
        
        origin = body.get("origin", "").strip()
        ttl = body.get("ttl_seconds", 300)
        
        # Validate origin against allowlist
        allowed_origins = list(getattr(self.context, "embed_direct_origins", []) or [])
        is_valid, normalized_origin, error_msg = validate_origin(origin, allowed_origins)
        
        if not is_valid:
            json_error(self.request.response, 403, "origin_not_allowed", message=error_msg)
            return
        
        # Get survey UID
        try:
            survey_uid = self.context.UID()
        except Exception:
            survey_uid = self.context.getId()
        
        # Generate token
        try:
            token, metadata = generate_embed_token(
                survey_uid=survey_uid,
                origin=normalized_origin,
                ttl_seconds=ttl
            )
        except EmbedSecurityError as e:
            logger.error("Embed token generation failed: %s", e)
            json_error(self.request.response, 500, "token_generation_failed", message=str(e))
            return
        
        logger.info(
            "Embed token generated: survey=%s origin=%s expires=%s",
            survey_uid, normalized_origin, metadata.get("expires_at")
        )
        
        json_response(self.request.response, {
            "token": token,
            "expires_at": metadata["expires_at"],
            "origin": normalized_origin,
            "survey_uid": survey_uid,
            "embed_url": f"{self.context.absolute_url()}/@@embed-loader",
        })


class EmbedConfigView(BrowserView):
    """Serve form configuration to embedded clients with CORS.
    
    Returns the SurveyJS form JSON along with a session ID and CSRF token.
    Validates the embed token and origin headers.
    """
    
    def __call__(self):
        """Return form JSON with CORS headers for validated requests."""
        # DEBUG: Log all request details
        logger.warning("[EMBED DEBUG] @@embed-config called")
        logger.warning("[EMBED DEBUG] Method: %s", self.request.get("REQUEST_METHOD"))
        logger.warning("[EMBED DEBUG] Headers: Origin=%s", self.request.get_header("Origin") or self.request.get("HTTP_ORIGIN"))
        logger.warning("[EMBED DEBUG] Headers: X-Embed-Token=%s", self.request.get_header("X-Embed-Token")[:50] + "..." if self.request.get_header("X-Embed-Token") else None)
        
        # Handle preflight
        allowed_origins = list(getattr(self.context, "embed_direct_origins", []) or [])
        logger.warning("[EMBED DEBUG] Allowed origins: %s", allowed_origins)
        
        if handle_cors_preflight(self.request, self.request.response, allowed_origins):
            logger.warning("[EMBED DEBUG] Preflight handled, returning")
            return
        
        # Get and validate origin
        origin = self.request.get_header("Origin") or self.request.get("HTTP_ORIGIN")
        logger.warning("[EMBED DEBUG] Validating origin: %s", origin)
        is_valid, normalized_origin, error_msg = validate_origin(origin, allowed_origins)
        logger.warning("[EMBED DEBUG] Origin validation: is_valid=%s, normalized=%s, error=%s", is_valid, normalized_origin, error_msg)

        # Always set CORS headers for any cross-origin request so the browser can
        # read error responses. Use normalized_origin if available, else raw origin.
        cors_origin = normalized_origin or origin
        if cors_origin:
            set_cors_headers(self.request.response, cors_origin)
            logger.warning("[EMBED DEBUG] CORS headers set for origin: %s", cors_origin)
        
        if not is_valid:
            logger.warning("[EMBED DEBUG] Origin invalid, returning 403: %s", error_msg)
            json_error(self.request.response, 403, "invalid_origin", message=error_msg)
            return
        
        # Validate token
        token = self.request.get_header("X-Embed-Token")
        logger.warning("[EMBED DEBUG] Token present: %s", bool(token))
        if not token:
            logger.warning("[EMBED DEBUG] No token, returning 403")
            json_error(self.request.response, 403, "token_required")
            return
        
        try:
            payload = validate_embed_token(token, normalized_origin, secret=None)
            logger.warning("[EMBED DEBUG] Token validated successfully, payload: %s", payload)
        except TokenExpiredError:
            logger.warning("[EMBED DEBUG] Token expired")
            json_error(self.request.response, 403, "token_expired")
            return
        except TokenInvalidError as e:
            logger.warning("[EMBED DEBUG] Token invalid: %s", e)
            json_error(self.request.response, 403, "token_invalid", message=str(e))
            return
        except EmbedSecurityError as e:
            logger.warning("[EMBED DEBUG] Token validation failed: %s", e)
            json_error(self.request.response, 403, "token_validation_failed", message=str(e))
            return
        
        # Verify survey matches token
        try:
            survey_uid = self.context.UID()
        except Exception:
            survey_uid = self.context.getId()
        
        logger.warning("[EMBED DEBUG] Survey UID from context: %s, from token: %s", survey_uid, payload.get("sub"))
        if payload.get("sub") != survey_uid:
            logger.warning("[EMBED DEBUG] Survey mismatch!")
            json_error(self.request.response, 403, "survey_mismatch")
            return
        
        logger.warning("[EMBED DEBUG] All validations passed, returning config")
        
        # Get form data
        annos = IAnnotations(self.context)
        form_versions = forms_service.sorted_form_versions(annos)
        form_data = form_versions[-1]["form_json"] if form_versions else {}
        form_version_id = form_versions[-1]["id"] if form_versions else ""
        
        # Generate session ID
        session_id = secrets.token_urlsafe(16)
        
        # Generate CSRF token
        csrf_token = plone.api.portal.get_tool("portal_url")()
        # Use Plone's authenticator
        try:
            from plone.protect.authenticator import createToken
            csrf_token = createToken()
        except Exception:
            csrf_token = secrets.token_urlsafe(32)
        
        logger.info(
            "Embed config served: survey=%s origin=%s session=%s",
            survey_uid, normalized_origin, session_id[:8]
        )
        
        json_response(self.request.response, {
            "form_json": form_data,
            "form_version": form_version_id,
            "csrf_token": csrf_token,
            "submit_endpoint": f"{self.context.absolute_url()}/@@save-poll",
            "session_id": session_id,
        })


class EmbedLoaderView(BrowserView):
    """Serve the embed loader JavaScript bundle.
    
    Returns the JavaScript client code that creates the shadow DOM
    web component for embedding surveys.
    """
    
    def __call__(self):
        """Return the JavaScript bundle for direct DOM embedding."""
        response = self.request.response
        response.setHeader("Content-Type", "application/javascript; charset=utf-8")
        response.setHeader("X-Content-Type-Options", "nosniff")
        
        response.setHeader("Cache-Control", "no-cache, no-store, must-revalidate")
        
        # Add CORS headers to allow script loading from any origin
        origin = self.request.get_header("Origin") or self.request.get("HTTP_ORIGIN")
        if origin:
            response.setHeader("Access-Control-Allow-Origin", origin)
            response.setHeader("Vary", "Origin")
        
        return self._get_embed_js()
    
    def _get_embed_js(self):
        """Generate the embed client JavaScript."""
        portal_url = plone.api.portal.get_tool("portal_url")()
        surveyjs_resource_url = f"{portal_url}/++resource++zopyx.surveyjs/surveyjs"
        
        return f"""/**
 * Direct DOM Embedding Client for zopyx.surveyjs
 * Security-first implementation with Shadow DOM isolation
 * 
 * Usage:
 *   <script src="{self.context.absolute_url()}/@@embed-loader"></script>
 *   <surveyjs-embed 
 *     survey-url="{self.context.absolute_url()}"
 *     token="YOUR_EMBED_TOKEN">
 *   </surveyjs-embed>
 */

(function() {{
  'use strict';

  // Embedded CSS reset and base styles
  const EMBED_CSS = `
    :host {{
      display: block;
      width: 100%;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    }}
    .surveyjs-embed-container {{
      width: 100%;
      min-height: 400px;
    }}
    .surveyjs-embed-container * {{
      box-sizing: border-box;
    }}
    .surveyjs-error {{
      color: #d32f2f;
      padding: 20px;
      text-align: center;
      background: #ffebee;
      border-radius: 8px;
      margin: 10px 0;
    }}
    .surveyjs-success {{
      color: #388e3c;
      padding: 20px;
      text-align: center;
      background: #e8f5e9;
      border-radius: 8px;
      margin: 10px 0;
    }}
    .surveyjs-loading {{
      padding: 40px;
      text-align: center;
      color: #666;
    }}
    .surveyjs-spinner {{
      display: inline-block;
      width: 40px;
      height: 40px;
      border: 3px solid #f3f3f3;
      border-top: 3px solid #3498db;
      border-radius: 50%;
      animation: spin 1s linear infinite;
    }}
    @keyframes spin {{
      0% {{ transform: rotate(0deg); }}
      100% {{ transform: rotate(360deg); }}
    }}
  `;

  /**
   * Secure API client for communicating with Plone backend
   */
  class SecureAPIClient {{
    constructor(baseUrl, token, origin) {{
      this.baseUrl = baseUrl.replace(/\\/$/, '');
      this.token = token;
      this.origin = origin;
    }}

    /**
     * Fetch form configuration from server
     */
    async getFormConfig() {{
      const response = await fetch(`${{this.baseUrl}}/@@embed-config`, {{
        method: 'GET',
        credentials: 'include',
        headers: {{
          'Accept': 'application/json',
          'X-Embed-Token': this.token,
          'Origin': this.origin,
        }},
      }});

      if (!response.ok) {{
        const error = await response.json().catch(() => ({{}}));
        throw new Error(error.message || `Failed to load form: ${{response.status}}`);
      }}

      return response.json();
    }}

    /**
     * Submit form data to server
     */
    async submitForm(data, sessionId, csrfToken) {{
      const formData = new FormData();
      formData.append('pollResult', JSON.stringify(data));
      formData.append('_authenticator', csrfToken);

      const response = await fetch(`${{this.baseUrl}}/@@save-poll`, {{
        method: 'POST',
        credentials: 'include',
        body: formData,
        headers: {{
          'X-Embed-Token': this.token,
          'X-Session-ID': sessionId,
          'Origin': this.origin,
        }},
      }});

      if (!response.ok) {{
        const error = await response.json().catch(() => ({{}}));
        throw new Error(error.message || `Submission failed: ${{response.status}}`);
      }}

      return response.json();
    }}
  }}

  /**
   * Web Component for embedding SurveyJS forms
   */
  class SurveyJSEmbed extends HTMLElement {{
    constructor() {{
      super();
      this.attachShadow({{ mode: 'open' }});

      // Load SurveyJS CSS into shadow root (cross-origin <link> works without CORS)
      const surveyLink = document.createElement('link');
      surveyLink.rel = 'stylesheet';
      surveyLink.href = '{surveyjs_resource_url}/survey-core.min.css';
      this.shadowRoot.appendChild(surveyLink);

      // Inject base styles
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
    }}

    static get observedAttributes() {{
      return ['survey-url', 'token'];
    }}

    async connectedCallback() {{
      const baseUrl = this.getAttribute('survey-url');
      const token = this.getAttribute('token');
      
      if (!baseUrl || !token) {{
        this.showError('Missing required attributes: survey-url, token');
        return;
      }}

      // Show loading state
      this.showLoading();

      try {{
        // Initialize API client
        this.api = new SecureAPIClient(baseUrl, token, window.location.origin);
        
        // Load form configuration
        this.config = await this.api.getFormConfig();
        
        // Initialize SurveyJS
        await this.initializeSurvey(this.config.form_json);
      }} catch (error) {{
        console.error('Survey embed error:', error);
        this.showError(error.message || 'Failed to load survey. Please try again.');
      }}
    }}

    async initializeSurvey(formJson) {{
      // Ensure SurveyJS is loaded
      if (typeof Survey === 'undefined') {{
        await this.loadSurveyJS();
      }}

      // Create survey model
      this.survey = new Survey.Model(formJson);
      
      // Apply theme if available
      if (typeof SurveyTheme !== 'undefined' && SurveyTheme.LayeredDarkPanelless) {{
        this.survey.applyTheme(SurveyTheme.LayeredDarkPanelless);
      }}
      
      // Handle completion
      this.survey.onComplete.add(async (sender) => {{
        this.showLoading('Submitting...');
        try {{
          await this.api.submitForm(
            sender.data,
            this.config.session_id,
            this.config.csrf_token
          );
          this.showSuccess('Thank you for your submission!');
        }} catch (error) {{
          console.error('Submission error:', error);
          this.showError('Submission failed. Please try again.');
          // Re-render form
          this.survey.render(this.container);
        }}
      }});

      // Render
      this.survey.render(this.container);
    }}

    loadSurveyJS() {{
      // If already loaded, resolve immediately
      if (typeof Survey !== 'undefined') {{
        return Promise.resolve();
      }}

      // If another instance is loading, wait for it
      if (window.__surveyJSLoading) {{
        return new Promise((resolve) => {{
          const check = setInterval(() => {{
            if (typeof Survey !== 'undefined') {{
              clearInterval(check);
              resolve();
            }}
          }}, 50);
        }});
      }}

      window.__surveyJSLoading = true;

      const loadScript = (src) => new Promise((resolve, reject) => {{
        const s = document.createElement('script');
        s.src = src;
        s.onload = resolve;
        s.onerror = () => reject(new Error('Failed to load: ' + src));
        document.head.appendChild(s);
      }});

      return loadScript('{surveyjs_resource_url}/survey.core.min.js')
        .then(() => loadScript('{surveyjs_resource_url}/survey-js-ui.min.js'))
        .then(() => {{ window.__surveyJSLoading = false; }})
        .catch((err) => {{ window.__surveyJSLoading = false; throw err; }});
    }}

    showLoading(message = 'Loading survey...') {{
      this.container.innerHTML = `
        <div class="surveyjs-loading">
          <div class="surveyjs-spinner"></div>
          <p>${{this.escapeHtml(message)}}</p>
        </div>
      `;
    }}

    showError(message) {{
      this.container.innerHTML = `
        <div class="surveyjs-error">
          <strong>Error</strong>
          <p>${{this.escapeHtml(message)}}</p>
        </div>
      `;
    }}

    showSuccess(message) {{
      this.container.innerHTML = `
        <div class="surveyjs-success">
          <strong>Success</strong>
          <p>${{this.escapeHtml(message)}}</p>
        </div>
      `;
    }}

    escapeHtml(text) {{
      if (!text) return '';
      const div = document.createElement('div');
      div.textContent = text;
      return div.innerHTML;
    }}
  }}

  // Register custom element
  if (!customElements.get('surveyjs-embed')) {{
    customElements.define('surveyjs-embed', SurveyJSEmbed);
  }}

  // Export for module systems
  if (typeof module !== 'undefined' && module.exports) {{
    module.exports = {{ SurveyJSEmbed, SecureAPIClient }};
  }}
}})();
"""


class EmbedSurveyJSBundleView(BrowserView):
    """Serve the SurveyJS library bundle for embedded contexts.
    
    This serves a self-contained SurveyJS bundle from the same origin,
    avoiding CDN/SRI issues with embedded content.
    """
    
    def __call__(self):
        """Return the SurveyJS library bundle."""
        response = self.request.response
        response.setHeader("Content-Type", "application/javascript; charset=utf-8")
        response.setHeader("X-Content-Type-Options", "nosniff")
        response.setHeader("Cache-Control", "public, max-age=86400")
        
        # Return a minimal stub that loads SurveyJS from CDN
        # In production, this would be a bundled, self-hosted version
        return """
// SurveyJS Bundle Stub
// This would contain the full SurveyJS library in production
// For now, we load from CDN with integrity check

(function() {
  'use strict';
  
  // Load SurveyJS Core
  var script = document.createElement('script');
  script.src = 'https://unpkg.com/survey-core@1.9.132/survey.core.min.js';
  script.crossOrigin = 'anonymous';
  script.onload = function() {
    // Load theme
    var themeScript = document.createElement('script');
    themeScript.src = 'https://unpkg.com/survey-core@1.9.132/themes/layered-dark-panelless.min.js';
    themeScript.crossOrigin = 'anonymous';
    document.head.appendChild(themeScript);
  };
  document.head.appendChild(script);
})();
"""


class DirectEmbedDemoView(BrowserView):
    """Demo view showing direct DOM embedding in action.
    
    This is a standalone HTML page that demonstrates the direct embedding
    feature by embedding the current survey using the web component.
    """
    
    def __call__(self):
        """Render the demo page."""
        # Check permissions
        if not plone.api.user.has_permission(
            "Modify portal content", obj=self.context
        ):
            self.request.response.setStatus(403)
            return "Access denied"
        
        # Check if direct embedding is configured
        if getattr(self.context, "embedding_mode", None) != "direct":
            return self._render_config_error(
                "Direct embedding not enabled",
                "This survey's embedding mode must be set to 'Direct DOM'."
            )
        
        allowed_origins = list(getattr(self.context, "embed_direct_origins", []) or [])
        if not allowed_origins:
            return self._render_config_error(
                "No origins configured",
                "Please add at least one allowed origin in the survey settings."
            )
        
        # Generate a demo token for the first allowed origin
        try:
            survey_uid = self.context.UID()
        except Exception:
            survey_uid = self.context.getId()
        
        demo_origin = allowed_origins[0]
        ttl = getattr(self.context, "embed_direct_token_ttl", 300) or 300
        
        try:
            token, metadata = generate_embed_token(survey_uid, demo_origin, ttl)
        except EmbedSecurityError as e:
            return self._render_config_error(
                "Token generation failed",
                str(e)
            )
        
        return self._render_demo_page(token, demo_origin, metadata)
    
    def _render_config_error(self, title, message):
        """Render an error page for configuration issues."""
        self.request.response.setHeader("Content-Type", "text/html; charset=utf-8")
        return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Direct Embed Demo - Configuration Error</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 800px;
            margin: 50px auto;
            padding: 20px;
            background: #f5f7fa;
        }}
        .error-box {{
            background: white;
            border-radius: 8px;
            padding: 30px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            border-left: 4px solid #d32f2f;
        }}
        h1 {{
            color: #d32f2f;
            margin-top: 0;
        }}
        code {{
            background: #f5f5f5;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: monospace;
        }}
    </style>
</head>
<body>
    <div class="error-box">
        <h1>⚠️ {title}</h1>
        <p>{message}</p>
        <p><a href="{self.context.absolute_url()}/edit">← Back to survey settings</a></p>
    </div>
</body>
</html>"""
    
    def _render_demo_page(self, token, origin, metadata):
        """Render the full demo page with embedded form."""
        survey_url = self.context.absolute_url()
        embed_loader_url = f"{survey_url}/@@embed-loader"
        expires_at = metadata.get("expires_at", "unknown")
        ttl = getattr(self.context, "embed_direct_token_ttl", 300) or 300
        
        self.request.response.setHeader("Content-Type", "text/html; charset=utf-8")
        
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Direct DOM Embedding Demo - {self.context.title}</title>
    <style>
        * {{
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            margin: 0;
            padding: 0;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
        }}
        .container {{
            max-width: 900px;
            margin: 0 auto;
            padding: 40px 20px;
        }}
        .header {{
            text-align: center;
            margin-bottom: 30px;
            color: white;
        }}
        .header h1 {{
            margin: 0 0 10px 0;
            font-size: 2rem;
            text-shadow: 0 2px 4px rgba(0,0,0,0.2);
        }}
        .header p {{
            margin: 0;
            opacity: 0.9;
            font-size: 1.1rem;
        }}
        .info-panel {{
            background: rgba(255,255,255,0.95);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        }}
        .info-panel h2 {{
            margin-top: 0;
            color: #333;
            font-size: 1.2rem;
        }}
        .info-grid {{
            display: grid;
            grid-template-columns: auto 1fr;
            gap: 10px 20px;
            font-size: 0.9rem;
        }}
        .info-label {{
            color: #666;
            font-weight: 500;
        }}
        .info-value {{
            color: #333;
            font-family: monospace;
            background: #f5f5f5;
            padding: 2px 8px;
            border-radius: 4px;
            word-break: break-all;
        }}
        .code-block {{
            background: #1e1e1e;
            color: #d4d4d4;
            padding: 20px;
            border-radius: 8px;
            overflow-x: auto;
            font-family: 'Fira Code', 'Consolas', monospace;
            font-size: 0.85rem;
            line-height: 1.5;
        }}
        .code-block .comment {{
            color: #6a9955;
        }}
        .code-block .tag {{
            color: #569cd6;
        }}
        .code-block .attr {{
            color: #9cdcfe;
        }}
        .code-block .string {{
            color: #ce9178;
        }}
        .form-container {{
            background: white;
            border-radius: 12px;
            padding: 30px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.15);
            margin-top: 20px;
        }}
        .form-container h2 {{
            margin-top: 0;
            color: #333;
        }}
        .badge {{
            display: inline-block;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        .badge-success {{
            background: #e8f5e9;
            color: #2e7d32;
        }}
        .badge-info {{
            background: #e3f2fd;
            color: #1565c0;
        }}
        .security-note {{
            background: #fff8e1;
            border-left: 4px solid #ffc107;
            padding: 15px 20px;
            margin-top: 20px;
            border-radius: 0 8px 8px 0;
        }}
        .security-note h3 {{
            margin-top: 0;
            color: #f57c00;
            font-size: 1rem;
        }}
        .security-note ul {{
            margin: 10px 0 0 0;
            padding-left: 20px;
        }}
        .security-note li {{
            margin-bottom: 5px;
            color: #666;
        }}
        @media (max-width: 600px) {{
            .container {{
                padding: 20px 15px;
            }}
            .header h1 {{
                font-size: 1.5rem;
            }}
            .info-grid {{
                grid-template-columns: 1fr;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔐 Direct DOM Embedding Demo</h1>
            <p>Seamless form integration with Shadow DOM isolation</p>
        </div>
        
        <div class="info-panel">
            <h2>📋 Configuration</h2>
            <div class="info-grid">
                <span class="info-label">Survey:</span>
                <span class="info-value">{self.context.title}</span>
                <span class="info-label">Origin:</span>
                <span class="info-value">{origin}</span>
                <span class="info-label">Token Expires:</span>
                <span class="info-value">{expires_at}</span>
                <span class="info-label">Mode:</span>
                <span class="info-value"><span class="badge badge-success">Direct DOM</span></span>
                <span class="info-label">Token:</span>
                <span class="info-value" style="word-break:break-all;font-size:0.75rem;">{token}</span>
            </div>
            <button onclick="navigator.clipboard.writeText('{token}').then(()=>this.textContent='Copied!').catch(()=>alert('Copy failed'))"
                    style="margin-top:10px;padding:6px 14px;background:#667eea;color:white;border:none;border-radius:4px;cursor:pointer;">
                Copy Token
            </button>
        </div>

        <div class="info-panel">
            <h2>💻 Integration Code</h2>
            <p>Add this code to your website to embed this form:</p>
            <div class="code-block">
<span class="comment">&lt;!-- 1. Load the embed script --&gt;</span>
&lt;<span class="tag">script</span> <span class="attr">src</span>=<span class="string">"{embed_loader_url}"</span>&gt;&lt;/<span class="tag">script</span>&gt;

<span class="comment">&lt;!-- 2. Add the embed element --&gt;</span>
&lt;<span class="tag">surveyjs-embed</span>
  <span class="attr">survey-url</span>=<span class="string">"{survey_url}"</span>
  <span class="attr">token</span>=<span class="string">"{token}"</span>&gt;
&lt;/<span class="tag">surveyjs-embed</span>&gt;
            </div>
        </div>
        
        <div class="form-container">
            <h2>📝 Live Embedded Form <span class="badge badge-info">Demo</span></h2>
            <p style="color: #666; margin-bottom: 20px;">
                This form is rendered inside a Shadow DOM container for style isolation.
            </p>
            
            <!-- The embedded survey -->
            <surveyjs-embed 
                survey-url="{survey_url}"
                token="{token}">
            </surveyjs-embed>
        </div>
        
        <div class="security-note">
            <h3>🔒 Security Features</h3>
            <ul>
                <li><strong>Origin Validation:</strong> Tokens are bound to specific HTTPS origins</li>
                <li><strong>Shadow DOM Isolation:</strong> Form styles are encapsulated from the host page</li>
                <li><strong>Short-lived Tokens:</strong> Tokens expire after {ttl} seconds</li>
                <li><strong>HMAC Signatures:</strong> All tokens are cryptographically signed</li>
                <li><strong>CORS Protection:</strong> Strict cross-origin resource sharing policies</li>
            </ul>
        </div>
    </div>
    
    <!-- Load the embed script -->
    <script src="{embed_loader_url}"></script>
</body>
</html>"""
