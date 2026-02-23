/**
 * Form versions management UI for @@form-versions.
 * Handles modal dialogs, preview rendering, and version actions.
 */
// ============================================================================
// Form Versions Management - Clean Simple Implementation
// ============================================================================

/**
 * @function
 */
(function() {
  'use strict';

/**
 * @function
 */
  var t = window._t || function (msgid, mapping) {
    if (!mapping) {
      return msgid;
    }
/**
 * @function
 */
    return msgid.replace(/\$\{([a-zA-Z0-9_]+)\}/g, function (match, key) {
      if (Object.prototype.hasOwnProperty.call(mapping, key)) {
        return String(mapping[key]);
      }
      return match;
    });
  };
  var baseUrl = '';
  var activeJsonRequest = null;
  var activeSurvey = null;
  var activePreviewRequest = null;

  // Wait for DOM to be ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

/**
 * @function
 */
  function init() {
    console.log('Form versions initializing...');
    baseUrl = window.location.href.split('/@@')[0];
    setupJsonViewer();
    setupPreviewModal();
    setupRestoreModal();
    setupTemplateModal();
    setupDeleteModal();
    setupFileInput();
    console.log('Form versions initialized');
  }

  // ============================================================================
  // JSON Viewer
  // ============================================================================

/**
 * @function
 */
  function setupJsonViewer() {
    var modal = document.getElementById('jsonViewerModal');
    var overlay = document.getElementById('jsonModalOverlay');
    var content = document.getElementById('jsonContent');

    if (!modal || !overlay || !content) {
      console.error('JSON viewer elements missing');
      return;
    }

    // Handle JSON button clicks
/**
 * @function
 */
    document.querySelectorAll('.view-json-btn').forEach(function(btn) {
/**
 * @function
 */
      btn.addEventListener('click', function(e) {
        e.preventDefault();
        var versionId = btn.getAttribute('data-version-id');
        if (!versionId) {
          console.error('Missing version id for JSON preview');
          return;
        }

        if (activeJsonRequest && activeJsonRequest.abort) {
          activeJsonRequest.abort();
        }
        var jsonController = ('AbortController' in window) ? new AbortController() : null;
        activeJsonRequest = jsonController;

        var url = baseUrl + '/@@view-version-json?version_id=' + encodeURIComponent(versionId);

        // Show modal
        content.textContent = t('Loading...');
        modal.classList.add('active');
        overlay.classList.add('active');
        document.body.style.overflow = 'hidden';

        var fetchOptions = { credentials: 'same-origin' };
        if (jsonController) {
          fetchOptions.signal = jsonController.signal;
        }

        // Fetch JSON
        fetch(url, fetchOptions)
/**
 * @function
 */
          .then(function(res) { return res.json(); })
/**
 * @function
 */
          .then(function(data) {
            content.textContent = JSON.stringify(data, null, 2);
          })
/**
 * @function
 */
          .catch(function(err) {
            if (err.name === 'AbortError') {
              return;
            }
            content.textContent = t('Error: ${error}', { error: err.message });
          })
/**
 * @function
 */
          .finally(function() {
            if (activeJsonRequest === jsonController) {
              activeJsonRequest = null;
            }
          });
      });
    });

    // Close handlers
    modal.querySelector('.json-modal-close').addEventListener('click', closeJsonModal);
    overlay.addEventListener('click', closeJsonModal);
/**
 * @function
 */
    document.addEventListener('keydown', function(e) {
      if (e.key === 'Escape' && modal.classList.contains('active')) {
        closeJsonModal();
      }
    });

/**
 * @function
 */
    function closeJsonModal() {
      if (activeJsonRequest && activeJsonRequest.abort) {
        activeJsonRequest.abort();
      }
      activeJsonRequest = null;
      modal.classList.remove('active');
      overlay.classList.remove('active');
      document.body.style.overflow = '';
    }
  }

  // ============================================================================
  // Preview Modal
  // ============================================================================

/**
 * @function
 */
  function setupPreviewModal() {
    var modal = document.getElementById('previewModal');
    var overlay = document.getElementById('previewModalOverlay');
    var container = document.getElementById('surveyContainer');

    if (!modal || !overlay || !container) {
      console.error('Preview modal elements missing');
      return;
    }

    console.log('Setting up preview handlers for', document.querySelectorAll('.preview-btn').length, 'buttons');

    // Handle Preview button clicks
/**
 * @function
 */
    document.querySelectorAll('.preview-btn').forEach(function(btn) {
/**
 * @function
 */
      btn.addEventListener('click', function(e) {
        e.preventDefault();
        var versionId = btn.getAttribute('data-version-id');
        if (!versionId) {
          console.error('Missing version id for preview');
          return;
        }

        console.log('Opening preview for version:', versionId);
        openPreview(versionId);
      });
    });

/**
 * @function
 */
    function openPreview(versionId) {
      if (activePreviewRequest && activePreviewRequest.abort) {
        activePreviewRequest.abort();
      }
      var previewController = ('AbortController' in window) ? new AbortController() : null;
      activePreviewRequest = previewController;
      var url = baseUrl + '/@@view-version-json?version_id=' + encodeURIComponent(versionId);

      // Clear previous survey
      if (activeSurvey) {
        try { activeSurvey.dispose(); } catch(e) {}
        activeSurvey = null;
      }

      // Show modal with loading message
      container.innerHTML =
        '<div style="text-align:center;padding:40px;color:#666;">' +
        t('Loading preview...') +
        '</div>';
      modal.classList.add('active');
      overlay.classList.add('active');
      document.body.style.overflow = 'hidden';

      var fetchOptions = { credentials: 'same-origin' };
      if (previewController) {
        fetchOptions.signal = previewController.signal;
      }

      // Fetch and render
      fetch(url, fetchOptions)
/**
 * @function
 */
        .then(function(res) {
          if (!res.ok) throw new Error('HTTP ' + res.status);
          return res.json();
        })
/**
 * @function
 */
        .then(function(json) {
          console.log('JSON received, rendering survey...');
          container.innerHTML = '';

          if (typeof Survey === 'undefined') {
            throw new Error(t('Survey library not loaded'));
          }

          var renderTarget = document.createElement('div');
          renderTarget.className = 'sv-preview-host';
          container.appendChild(renderTarget);

          activeSurvey = new Survey.Model(json);
          if (window.SURVEYJS_I18N_LOCALE) {
            activeSurvey.locale = window.SURVEYJS_I18N_LOCALE;
          }
          if (typeof Survey !== 'undefined' && Survey.surveyLocalization) {
            Survey.surveyLocalization.currentLocale = window.SURVEYJS_I18N_LOCALE;
          }

          // Apply light theme if available
          if (typeof SurveyTheme !== 'undefined' && SurveyTheme.LayeredLightPanelless) {
            activeSurvey.applyTheme(SurveyTheme.LayeredLightPanelless);
          }

          activeSurvey.showCompleteButton = false;
          activeSurvey.render(renderTarget);

          console.log('Survey rendered successfully');
          console.log('Container innerHTML length:', container.innerHTML.length);
          console.log('Container has', container.children.length, 'direct children');
          console.log('Container computed height:', window.getComputedStyle(container).height);

          // Log first child details
          if (container.children.length > 0) {
            var firstChild = container.children[0];
            console.log('First child tag:', firstChild.tagName);
            console.log('First child class:', firstChild.className);
            console.log('First child height:', window.getComputedStyle(firstChild).height);
            console.log('First child display:', window.getComputedStyle(firstChild).display);
          }
        })
/**
 * @function
 */
        .catch(function(err) {
          if (err.name === 'AbortError') {
            return;
          }
          console.error(t('Preview error:'), err);
          container.innerHTML =
            '<div style="text-align:center;padding:40px;color:#e00;">' +
            t('Error: ${error}', { error: err.message }) +
            '</div>';
        })
/**
 * @function
 */
        .finally(function() {
          if (activePreviewRequest === previewController) {
            activePreviewRequest = null;
          }
        });
    }

    // Close handlers
    modal.querySelector('.preview-modal-close').addEventListener('click', closePreview);
    overlay.addEventListener('click', closePreview);
/**
 * @function
 */
    document.addEventListener('keydown', function(e) {
      if (e.key === 'Escape' && modal.classList.contains('active')) {
        closePreview();
      }
    });

/**
 * @function
 */
    function closePreview() {
      if (activePreviewRequest && activePreviewRequest.abort) {
        activePreviewRequest.abort();
      }
      activePreviewRequest = null;

      if (activeSurvey) {
        try { activeSurvey.dispose(); } catch(e) {}
      }
      activeSurvey = null;
      container.innerHTML = '';
      modal.classList.remove('active');
      overlay.classList.remove('active');
      document.body.style.overflow = '';
    }
  }

  // ============================================================================
  // Restore Modal
  // ============================================================================

/**
 * @function
 */
  function setupRestoreModal() {
    var modal = document.getElementById('restoreModal');
    var overlay = document.getElementById('restoreModalOverlay');
    var versionIdEl = document.getElementById('restoreVersionId');
    var versionUserEl = document.getElementById('restoreVersionUser');
    var versionDateEl = document.getElementById('restoreVersionDate');
    var versionInput = document.getElementById('restoreVersionInput');

    if (!modal || !overlay || !versionIdEl || !versionInput) {
      return;
    }

/**
 * @function
 */
    document.querySelectorAll('.open-restore-dialog').forEach(function(btn) {
/**
 * @function
 */
      btn.addEventListener('click', function(e) {
        e.preventDefault();
        var vid = btn.getAttribute('data-version-id') || '';
        var created = btn.getAttribute('data-created') || '';
        var user = btn.getAttribute('data-user') || '';

        versionIdEl.textContent = vid;
        versionUserEl.textContent = user || t('--');
        versionDateEl.textContent = created || t('--');
        versionInput.value = vid;

        modal.classList.add('active');
        overlay.classList.add('active');
        document.body.style.overflow = 'hidden';
      });
    });

/**
 * @function
 */
    function closeRestore() {
      modal.classList.remove('active');
      overlay.classList.remove('active');
      document.body.style.overflow = '';
    }

/**
 * @function
 */
    document.querySelectorAll('.close-restore').forEach(function(btn) {
/**
 * @function
 */
      btn.addEventListener('click', function(e) {
        e.preventDefault();
        closeRestore();
      });
    });

    overlay.addEventListener('click', closeRestore);
/**
 * @function
 */
    document.addEventListener('keydown', function(e) {
      if (e.key === 'Escape' && modal.classList.contains('active')) {
        closeRestore();
      }
    });
  }

  // ============================================================================
  // Delete Modal
  // ============================================================================

/**
 * @function
 */
  function setupDeleteModal() {
    var modal = document.getElementById('deleteModal');
    var overlay = document.getElementById('deleteModalOverlay');
    var versionIdEl = document.getElementById('deleteVersionId');
    var confirmButton = document.querySelector('.confirm-delete');
    var pendingDeleteForm = null;

    if (!modal || !overlay || !versionIdEl || !confirmButton) {
      return;
    }

/**
 * @function
 */
    document.querySelectorAll('.open-delete-dialog').forEach(function(btn) {
/**
 * @function
 */
      btn.addEventListener('click', function(e) {
        e.preventDefault();
        var vid = btn.getAttribute('data-version-id') || '';
        pendingDeleteForm = btn.closest('form');

        versionIdEl.textContent = vid || t('--');
        modal.classList.add('active');
        overlay.classList.add('active');
        document.body.style.overflow = 'hidden';
      });
    });

/**
 * @function
 */
    function closeDelete() {
      pendingDeleteForm = null;
      modal.classList.remove('active');
      overlay.classList.remove('active');
      document.body.style.overflow = '';
    }

/**
 * @function
 */
    confirmButton.addEventListener('click', function(e) {
      e.preventDefault();
      if (pendingDeleteForm) {
        pendingDeleteForm.submit();
      }
    });

/**
 * @function
 */
    document.querySelectorAll('.close-delete').forEach(function(btn) {
/**
 * @function
 */
      btn.addEventListener('click', function(e) {
        e.preventDefault();
        closeDelete();
      });
    });

    overlay.addEventListener('click', closeDelete);
/**
 * @function
 */
    document.addEventListener('keydown', function(e) {
      if (e.key === 'Escape' && modal.classList.contains('active')) {
        closeDelete();
      }
    });
  }

  // ============================================================================
  // Template Modal
  // ============================================================================

/**
 * @function
 */
  function setupTemplateModal() {
    var modal = document.getElementById('templateModal');
    var overlay = document.getElementById('templateModalOverlay');
    var versionIdEl = document.getElementById('templateVersionId');
    var versionInput = document.getElementById('templateVersionInput');
    var titleInput = document.getElementById('templateTitleInput');
    var titleHidden = document.getElementById('templateTitleHidden');
    var form = document.getElementById('templateForm');
    var container = document.querySelector('.form-versions-container');
    var surveyId = container ? container.getAttribute('data-survey-id') || '' : '';

    if (!modal || !overlay || !versionIdEl || !versionInput || !titleInput || !titleHidden || !form) {
      return;
    }

/**
 * @function
 */
    document.querySelectorAll('.open-template-dialog').forEach(function(btn) {
/**
 * @function
 */
      btn.addEventListener('click', function(e) {
        e.preventDefault();
        var vid = btn.getAttribute('data-version-id') || '';
        versionIdEl.textContent = vid || t('--');
        versionInput.value = vid;

        var defaultTitle = 'template' + surveyId;
        titleInput.value = defaultTitle;
        titleHidden.value = defaultTitle;

        modal.classList.add('active');
        overlay.classList.add('active');
        document.body.style.overflow = 'hidden';
        titleInput.focus();
        titleInput.select();
      });
    });

/**
 * @function
 */
    titleInput.addEventListener('input', function() {
      titleHidden.value = titleInput.value;
    });

/**
 * @function
 */
    form.addEventListener('submit', function() {
      titleHidden.value = titleInput.value;
    });

/**
 * @function
 */
    function closeTemplate() {
      modal.classList.remove('active');
      overlay.classList.remove('active');
      document.body.style.overflow = '';
    }

/**
 * @function
 */
    document.querySelectorAll('.close-template').forEach(function(btn) {
/**
 * @function
 */
      btn.addEventListener('click', function(e) {
        e.preventDefault();
        closeTemplate();
      });
    });

    overlay.addEventListener('click', closeTemplate);
/**
 * @function
 */
    document.addEventListener('keydown', function(e) {
      if (e.key === 'Escape' && modal.classList.contains('active')) {
        closeTemplate();
      }
    });
  }

  // ============================================================================
  // File Input
  // ============================================================================

/**
 * @function
 */
  function setupFileInput() {
    var input = document.getElementById('json_file');
    if (input) {
/**
 * @function
 */
      input.addEventListener('change', function() {
        var fileName = this.files[0]
          ? this.files[0].name
          : t('No file selected');
        var label = this.nextElementSibling;
        if (label && label.tagName === 'LABEL') {
          label.textContent = fileName;
        }
      });
    }
  }

})();
