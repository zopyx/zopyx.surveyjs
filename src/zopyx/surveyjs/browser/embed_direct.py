"""Direct DOM Embedding views for zopyx.surveyjs.

Provides endpoints for:
- Token generation (@@embed-token)
- Form configuration serving (@@embed-config)
- Embed loader script (@@embed-loader)
"""

import base64
import hashlib
import html
import json
import logging
import os
import secrets

import plone.api
from Products.Five import BrowserView
from zope.annotation.interfaces import IAnnotations

from ..permissions import ModifyPortalContent
from .services import forms as forms_service
from .services.http import json_error, json_response, parse_json_body
from .embed_security import (
    generate_embed_token,
    validate_embed_token,
    validate_origin,
    set_cors_headers,
    handle_cors_preflight,
    is_embed_direct_globally_enabled,
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
        # Rate limiting check for token generation
        from .services.rate_limit import RateLimitService, RateLimitExceeded
        rate_limiter = RateLimitService(self.context, self.request)
        try:
            settings = rate_limiter._load_settings()
            limit = getattr(settings, "rate_limit_token_gen_per_ip", 20)
            window = getattr(settings, "rate_limit_token_gen_window", 3600)
            rate_limiter.check_rate_limit(
                endpoint="embed_token_gen",
                limit=limit,
                window=window,
                key_type="ip"
            )
        except RateLimitExceeded as e:
            logger.warning(
                "Embed token generation rate limited: ip=%s retry_after=%d",
                rate_limiter._get_client_ip(),
                e.retry_after
            )
            response = json_error(
                self.request.response,
                429,
                "rate_limit_exceeded",
                message="Token generation limit reached. Please try again later."
            )
            response.headers["Retry-After"] = str(e.retry_after)
            return
        finally:
            rate_limiter.close()

        # Check permission
        if not plone.api.user.has_permission(ModifyPortalContent, obj=self.context):
            json_error(self.request.response, 403, "permission_denied")
            return

        # Check if direct embedding is enabled globally
        if not is_embed_direct_globally_enabled():
            json_error(
                self.request.response,
                403,
                "feature_disabled",
                message="Direct DOM embedding is not enabled globally",
            )
            return

        # Check survey embedding mode
        embed_mode = getattr(self.context, "embedding_mode", None)
        if embed_mode != "direct":
            json_error(
                self.request.response,
                400,
                "direct_embedding_not_enabled",
                message="This survey is not configured for Direct DOM embedding",
            )
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
        is_valid, normalized_origin, error_msg = validate_origin(
            origin, allowed_origins
        )

        if not is_valid:
            json_error(
                self.request.response, 403, "origin_not_allowed", message=error_msg
            )
            return

        # Get survey UID
        try:
            survey_uid = self.context.UID()
        except Exception:
            survey_uid = self.context.getId()

        # Generate token
        try:
            token, metadata = generate_embed_token(
                survey_uid=survey_uid, origin=normalized_origin, ttl_seconds=ttl
            )
        except EmbedSecurityError as e:
            logger.error("Embed token generation failed: %s", e)
            json_error(
                self.request.response, 500, "token_generation_failed", message=str(e)
            )
            return

        logger.info(
            "Embed token generated: survey=%s origin=%s expires=%s",
            survey_uid,
            normalized_origin,
            metadata.get("expires_at"),
        )

        json_response(
            self.request.response,
            {
                "token": token,
                "expires_at": metadata["expires_at"],
                "origin": normalized_origin,
                "survey_uid": survey_uid,
                "embed_url": f"{self.context.absolute_url()}/@@embed-loader",
            },
        )


class EmbedConfigView(BrowserView):
    """Serve form configuration to embedded clients with CORS.

    Returns the SurveyJS form JSON along with a session ID and CSRF token.
    Validates the embed token and origin headers.
    """

    def __call__(self):
        """Return form JSON with CORS headers for validated requests."""
        # Check if direct embedding is enabled globally
        if not is_embed_direct_globally_enabled():
            json_error(
                self.request.response,
                403,
                "feature_disabled",
                message="Direct DOM embedding is not enabled globally",
            )
            return

        # Handle preflight
        allowed_origins = list(getattr(self.context, "embed_direct_origins", []) or [])

        if handle_cors_preflight(self.request, self.request.response, allowed_origins):
            return

        # Get and validate origin
        origin = self.request.get_header("Origin") or self.request.get("HTTP_ORIGIN")
        is_valid, normalized_origin, error_msg = validate_origin(
            origin, allowed_origins
        )

        # Only set CORS headers for valid (allowlisted) origins
        if is_valid and normalized_origin:
            set_cors_headers(self.request.response, normalized_origin)

        if not is_valid:
            json_error(self.request.response, 403, "invalid_origin", message=error_msg)
            return

        # Validate token
        token = self.request.get_header("X-Embed-Token")
        if not token:
            json_error(self.request.response, 403, "token_required")
            return

        try:
            payload = validate_embed_token(token, normalized_origin, secret=None)
        except TokenExpiredError:
            json_error(self.request.response, 403, "token_expired")
            return
        except TokenInvalidError as e:
            json_error(self.request.response, 403, "token_invalid", message=str(e))
            return
        except EmbedSecurityError as e:
            json_error(
                self.request.response, 403, "token_validation_failed", message=str(e)
            )
            return

        # Verify survey matches token
        try:
            survey_uid = self.context.UID()
        except Exception:
            survey_uid = self.context.getId()

        if payload.get("sub") != survey_uid:
            json_error(self.request.response, 403, "survey_mismatch")
            return

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
            survey_uid,
            normalized_origin,
            session_id[:8],
        )

        json_response(
            self.request.response,
            {
                "form_json": form_data,
                "form_version": form_version_id,
                "csrf_token": csrf_token,
                "submit_endpoint": f"{self.context.absolute_url()}/@@save-poll",
                "session_id": session_id,
            },
        )


class EmbedSurveyJSView(BrowserView):
    """Serve SurveyJS library files with CORS headers for direct DOM embedding.

    The ++resource++ traversal does not add CORS headers, so cross-origin
    embedding pages cannot load the SurveyJS scripts directly.  This view
    re-serves a strict whitelist of those files with Access-Control-Allow-Origin: *
    (they are public, unversioned library assets with no credentials).
    """

    _ALLOWED = frozenset(["survey.core.min.js", "survey-js-ui.min.js"])

    def __call__(self):
        name = self.request.get("name", "")
        if name not in self._ALLOWED:
            self.request.response.setStatus(404)
            return "Not found"

        filepath = os.path.join(os.path.dirname(__file__), "static", "surveyjs", name)
        try:
            with open(filepath, "rb") as fh:
                content = fh.read()
        except OSError:
            self.request.response.setStatus(404)
            return "Not found"

        response = self.request.response
        response.setHeader("Content-Type", "application/javascript; charset=utf-8")
        response.setHeader("Access-Control-Allow-Origin", "*")
        response.setHeader("Cache-Control", "public, max-age=86400, immutable")
        response.setHeader("X-Content-Type-Options", "nosniff")
        return content


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

    @staticmethod
    def _sri_hash(filepath):
        """Compute a base64-encoded SHA-384 SRI hash for a file."""
        try:
            with open(filepath, "rb") as fh:
                digest = hashlib.sha384(fh.read()).digest()
            return "sha384-" + base64.b64encode(digest).decode("ascii")
        except Exception:
            return None

    def _get_embed_js(self):
        """Generate the embed client JavaScript."""
        portal_url = plone.api.portal.get_tool("portal_url")()
        # Use @@embed-surveyjs instead of ++resource++ so CORS headers are present
        # for cross-origin embedding pages loading these scripts.
        surveyjs_resource_url = f"{portal_url}/@@embed-surveyjs?name"
        surveyjs_css_url = f"{portal_url}/++resource++zopyx.surveyjs/surveyjs"

        # Compute SRI hashes from the files on disk so the embedding page can
        # verify script integrity before execution.
        _static_dir = os.path.join(os.path.dirname(__file__), "static", "surveyjs")
        _sri_core = (
            self._sri_hash(os.path.join(_static_dir, "survey.core.min.js")) or ""
        )
        _sri_ui = self._sri_hash(os.path.join(_static_dir, "survey-js-ui.min.js")) or ""

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
      surveyLink.href = '{surveyjs_css_url}/survey-core.min.css';
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

      const loadScript = (src, integrity) => new Promise((resolve, reject) => {{
        const s = document.createElement('script');
        s.src = src;
        if (integrity) {{
          s.integrity = integrity;
          s.crossOrigin = 'anonymous';
        }}
        s.onload = resolve;
        s.onerror = () => reject(new Error('Failed to load: ' + src));
        document.head.appendChild(s);
      }});

      return loadScript('{surveyjs_resource_url}=survey.core.min.js', '{_sri_core}')
        .then(() => loadScript('{surveyjs_resource_url}=survey-js-ui.min.js', '{_sri_ui}'))
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


class DirectEmbedDemoView(BrowserView):
    """Demo view showing direct DOM embedding in action.

    This is a standalone HTML page that demonstrates the direct embedding
    feature by embedding the current survey using the web component.
    """

    def __call__(self):
        """Render the demo page."""
        # Check permissions
        if not plone.api.user.has_permission(ModifyPortalContent, obj=self.context):
            self.request.response.setStatus(403)
            return "Access denied"

        # Check if direct embedding is enabled globally
        if not is_embed_direct_globally_enabled():
            return self._render_config_error(
                "Feature disabled", "Direct DOM embedding is not enabled globally."
            )

        # Check if direct embedding is configured
        if getattr(self.context, "embedding_mode", None) != "direct":
            return self._render_config_error(
                "Direct embedding not enabled",
                "This survey's embedding mode must be set to 'Direct DOM'.",
            )

        allowed_origins = list(getattr(self.context, "embed_direct_origins", []) or [])
        if not allowed_origins:
            return self._render_config_error(
                "No origins configured",
                "Please add at least one allowed origin in the survey settings.",
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
            return self._render_config_error("Token generation failed", str(e))

        return self._render_demo_page(token, demo_origin, metadata)

    def _render_config_error(self, title, message):
        """Render an error page for configuration issues."""
        self.request.response.setHeader("Content-Type", "text/html; charset=utf-8")
        safe_title = html.escape(title)
        safe_message = html.escape(message)
        safe_edit_url = html.escape(self.context.absolute_url() + "/edit")
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
        <h1>⚠️ {safe_title}</h1>
        <p>{safe_message}</p>
        <p><a href="{safe_edit_url}">← Back to survey settings</a></p>
    </div>
</body>
</html>"""

    def _render_demo_page(self, token, origin, metadata):
        """Render the full demo page with embedded form."""
        survey_url = self.context.absolute_url()
        embed_loader_url = f"{survey_url}/@@embed-loader"
        expires_at = metadata.get("expires_at", "unknown")
        ttl = getattr(self.context, "embed_direct_token_ttl", 300) or 300

        # Escape all user-controlled values for safe HTML interpolation
        safe_title = html.escape(self.context.title or "")
        safe_survey_url = html.escape(survey_url)
        safe_embed_loader_url = html.escape(embed_loader_url)
        safe_origin = html.escape(origin)
        safe_expires_at = html.escape(str(expires_at))
        safe_token = html.escape(token)
        # JSON-encode token and HTML-escape it so it's safe inside a double-quoted attribute.
        # json.dumps produces "token..." with double quotes; html.escape turns them into &quot;
        # which browsers unescape correctly before executing the JS.
        js_token = html.escape(json.dumps(token))

        self.request.response.setHeader("Content-Type", "text/html; charset=utf-8")

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Direct DOM Embedding Demo - {safe_title}</title>
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
                <span class="info-value">{safe_title}</span>
                <span class="info-label">Origin:</span>
                <span class="info-value">{safe_origin}</span>
                <span class="info-label">Token Expires:</span>
                <span class="info-value">{safe_expires_at}</span>
                <span class="info-label">Mode:</span>
                <span class="info-value"><span class="badge badge-success">Direct DOM</span></span>
                <span class="info-label">Token:</span>
                <span class="info-value" style="word-break:break-all;font-size:0.75rem;">{safe_token}</span>
            </div>
            <button onclick="navigator.clipboard.writeText({js_token}).then(()=>this.textContent='Copied!').catch(()=>alert('Copy failed'))"
                    style="margin-top:10px;padding:6px 14px;background:#667eea;color:white;border:none;border-radius:4px;cursor:pointer;">
                Copy Token
            </button>
        </div>

        <div class="info-panel">
            <h2>💻 Integration Code</h2>
            <p>Add this code to your website to embed this form:</p>
            <div class="code-block">
<span class="comment">&lt;!-- 1. Load the embed script --&gt;</span>
&lt;<span class="tag">script</span> <span class="attr">src</span>=<span class="string">"{safe_embed_loader_url}"</span>&gt;&lt;/<span class="tag">script</span>&gt;

<span class="comment">&lt;!-- 2. Add the embed element --&gt;</span>
&lt;<span class="tag">surveyjs-embed</span>
  <span class="attr">survey-url</span>=<span class="string">"{safe_survey_url}"</span>
  <span class="attr">token</span>=<span class="string">"{safe_token}"</span>&gt;
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
                survey-url="{safe_survey_url}"
                token="{safe_token}">
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
    <script src="{safe_embed_loader_url}"></script>
</body>
</html>"""
