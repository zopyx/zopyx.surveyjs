// ============================================================================
// Form Versions Management - Clean Simple Implementation
// ============================================================================

(function() {
  'use strict';

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

  function init() {
    console.log('Form versions initializing...');
    baseUrl = window.location.href.split('/@@')[0];
    setupJsonViewer();
    setupPreviewModal();
    setupRestoreModal();
    setupFileInput();
    console.log('Form versions initialized');
  }

  // ============================================================================
  // JSON Viewer
  // ============================================================================

  function setupJsonViewer() {
    var modal = document.getElementById('jsonViewerModal');
    var overlay = document.getElementById('jsonModalOverlay');
    var content = document.getElementById('jsonContent');

    if (!modal || !overlay || !content) {
      console.error('JSON viewer elements missing');
      return;
    }

    // Handle JSON button clicks
    document.querySelectorAll('.view-json-btn').forEach(function(btn) {
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
        content.textContent = 'Loading...';
        modal.classList.add('active');
        overlay.classList.add('active');
        document.body.style.overflow = 'hidden';

        var fetchOptions = { credentials: 'same-origin' };
        if (jsonController) {
          fetchOptions.signal = jsonController.signal;
        }

        // Fetch JSON
        fetch(url, fetchOptions)
          .then(function(res) { return res.json(); })
          .then(function(data) {
            content.textContent = JSON.stringify(data, null, 2);
          })
          .catch(function(err) {
            if (err.name === 'AbortError') {
              return;
            }
            content.textContent = 'Error: ' + err.message;
          })
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
    document.addEventListener('keydown', function(e) {
      if (e.key === 'Escape' && modal.classList.contains('active')) {
        closeJsonModal();
      }
    });

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
    document.querySelectorAll('.preview-btn').forEach(function(btn) {
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
      container.innerHTML = '<div style="text-align:center;padding:40px;color:#666;">Loading preview...</div>';
      modal.classList.add('active');
      overlay.classList.add('active');
      document.body.style.overflow = 'hidden';

      var fetchOptions = { credentials: 'same-origin' };
      if (previewController) {
        fetchOptions.signal = previewController.signal;
      }

      // Fetch and render
      fetch(url, fetchOptions)
        .then(function(res) {
          if (!res.ok) throw new Error('HTTP ' + res.status);
          return res.json();
        })
        .then(function(json) {
          console.log('JSON received, rendering survey...');
          container.innerHTML = '';

          if (typeof Survey === 'undefined') {
            throw new Error('Survey library not loaded');
          }

          var renderTarget = document.createElement('div');
          renderTarget.className = 'sv-preview-host';
          container.appendChild(renderTarget);

          activeSurvey = new Survey.Model(json);

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
        .catch(function(err) {
          if (err.name === 'AbortError') {
            return;
          }
          console.error('Preview error:', err);
          container.innerHTML = '<div style="text-align:center;padding:40px;color:#e00;">Error: ' + err.message + '</div>';
        })
        .finally(function() {
          if (activePreviewRequest === previewController) {
            activePreviewRequest = null;
          }
        });
    }

    // Close handlers
    modal.querySelector('.preview-modal-close').addEventListener('click', closePreview);
    overlay.addEventListener('click', closePreview);
    document.addEventListener('keydown', function(e) {
      if (e.key === 'Escape' && modal.classList.contains('active')) {
        closePreview();
      }
    });

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

    document.querySelectorAll('.open-restore-dialog').forEach(function(btn) {
      btn.addEventListener('click', function(e) {
        e.preventDefault();
        var vid = btn.getAttribute('data-version-id') || '';
        var created = btn.getAttribute('data-created') || '';
        var user = btn.getAttribute('data-user') || '';

        versionIdEl.textContent = vid;
        versionUserEl.textContent = user || '—';
        versionDateEl.textContent = created || '—';
        versionInput.value = vid;

        modal.classList.add('active');
        overlay.classList.add('active');
        document.body.style.overflow = 'hidden';
      });
    });

    function closeRestore() {
      modal.classList.remove('active');
      overlay.classList.remove('active');
      document.body.style.overflow = '';
    }

    document.querySelectorAll('.close-restore').forEach(function(btn) {
      btn.addEventListener('click', function(e) {
        e.preventDefault();
        closeRestore();
      });
    });

    overlay.addEventListener('click', closeRestore);
    document.addEventListener('keydown', function(e) {
      if (e.key === 'Escape' && modal.classList.contains('active')) {
        closeRestore();
      }
    });
  }

  // ============================================================================
  // File Input
  // ============================================================================

  function setupFileInput() {
    var input = document.getElementById('json_file');
    if (input) {
      input.addEventListener('change', function() {
        var fileName = this.files[0] ? this.files[0].name : 'No file selected';
        var label = this.nextElementSibling;
        if (label && label.tagName === 'LABEL') {
          label.textContent = fileName;
        }
      });
    }
  }

})();
