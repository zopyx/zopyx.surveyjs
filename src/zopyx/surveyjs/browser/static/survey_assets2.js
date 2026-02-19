/**
 * Initializes SurveyJS global variables from JSON config tags.
 * Used by survey_assets2.pt (CDN resource bundle).
 */
/**
 * Initialize SurveyJS global variables from JSON config tags (CDN bundle).
 */
(function initSurveyAssetsCdn() {
  /**
   * Read a JSON-encoded value from a script tag by id.
   * @param {string} id
   * @returns {string|null}
   */
  var readValue = function (id) {
    var el = document.getElementById(id);
    if (!el || !el.textContent) {
      return null;
    }
    try {
      return JSON.parse(el.textContent);
    } catch (error) {
      console.error("Failed to parse surveyjs config value", id, error);
      return null;
    }
  };

  var actualUrl = readValue("surveyjs-actual-url");
  if (actualUrl !== null) {
    window.ACTUAL_URL = actualUrl;
  }

  var csrfToken = readValue("surveyjs-csrf-token");
  if (csrfToken !== null) {
    window.CSRF_TOKEN = csrfToken;
  }

  var authToken = readValue("surveyjs-auth-token");
  if (authToken !== null) {
    window.AUTH_TOKEN = authToken;
  }

  var authTokenPdf = readValue("surveyjs-auth-token-pdf");
  if (authTokenPdf !== null) {
    window.AUTH_TOKEN_PDF = authTokenPdf;
  }

  var locale = readValue("surveyjs-i18n-locale");
  if (locale !== null) {
    window.SURVEYJS_I18N_LOCALE = locale;
  }

  var i18nBase = readValue("surveyjs-i18n-base");
  if (i18nBase !== null) {
    window.SURVEYJS_I18N_BASE = i18nBase;
  }
})();
