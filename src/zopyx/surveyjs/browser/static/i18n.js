/**
 * SurveyJS i18n loader utilities.
 * Exposes helpers to fetch locale bundles for SurveyJS/Creator.
 */
(function () {
  'use strict';

/**
 * @function
 */
  function applyMapping(text, mapping) {
    if (!mapping) {
      return text;
    }

/**
 * @function
 */
    return text.replace(/\$\{([a-zA-Z0-9_]+)\}/g, function (match, key) {
      if (Object.prototype.hasOwnProperty.call(mapping, key)) {
        return String(mapping[key]);
      }
      return match;
    });
  }

/**
 * @function
 */
  window._t = function (msgid, mapping) {
    const messages = window.SURVEYJS_I18N_MESSAGES || {};
    const translated = Object.prototype.hasOwnProperty.call(messages, msgid)
      ? messages[msgid]
      : msgid;
    return applyMapping(translated, mapping);
  };
})();
