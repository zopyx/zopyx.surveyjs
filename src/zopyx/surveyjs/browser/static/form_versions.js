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
    setupResizableColumns();
    console.log('Form versions initialized');
  }

  // Column resizing functionality
  var columnWidthsKey = 'surveyjs_formversions_column_widths';
  var columnWidths = {};
  try {
    var saved = localStorage.getItem(columnWidthsKey);
    if (saved) {
      columnWidths = JSON.parse(saved);
    }
  } catch (e) {
    // Ignore localStorage errors
  }

  function saveColumnWidths() {
    try {
      localStorage.setItem(columnWidthsKey, JSON.stringify(columnWidths));
    } catch (e) {
      // Ignore localStorage errors
    }
  }

  var resizeState = {
    resizing: false,
    columnKey: null,
    startX: 0,
    startWidth: 0,
    thElement: null
  };

  // Table state for sorting and filtering
  var tableState = {
    sortColumn: null,
    sortDirection: 'asc',
    filterValues: {}
  };

  // Store original row order for filtering
  var originalRows = [];

  /**
   * @function
   */
  function setupResizableColumns() {
    var table = document.querySelector('.form-versions-table');
    if (!table) return;

    // Store original rows
    var tbody = table.querySelector('tbody');
    if (tbody) {
      originalRows = Array.from(tbody.querySelectorAll('tr'));
    }

    // Apply saved widths and setup sort/filter
    var headers = table.querySelectorAll('thead th');
    var columnNames = ['date', 'user', 'version', 'actions'];
    
    headers.forEach(function(th, index) {
      var key = 'col-' + index;
      var colName = columnNames[index] || 'col-' + index;
      
      if (columnWidths[key]) {
        th.style.width = columnWidths[key] + 'px';
        th.style.minWidth = columnWidths[key] + 'px';
      }

      // Wrap header content for sorting
      if (index < 3) { // Don't make Actions column sortable
        var content = th.innerHTML;
        th.innerHTML = '<div class="th-content"><button type="button" class="sort-btn" data-column="' + colName + '">' + content + '</button></div>';
      } else {
        th.innerHTML = '<div class="th-content">' + th.innerHTML + '</div>';
      }

      // Add resize handle
      var handle = document.createElement('div');
      handle.className = 'resize-handle';
      handle.setAttribute('data-column', key);
      th.appendChild(handle);

      handle.addEventListener('mousedown', function(e) {
        e.preventDefault();
        e.stopPropagation();
        var rect = th.getBoundingClientRect();
        resizeState = {
          resizing: true,
          columnKey: key,
          startX: e.clientX,
          startWidth: rect.width,
          thElement: th
        };
        document.body.style.cursor = 'col-resize';
        th.classList.add('resizing');
      });
    });

    // Add filter row
    addFilterRow(table, columnNames);

    // Setup sort handlers
    setupSortHandlers(table);

    // Document-level mouse events for resize
    document.addEventListener('mousemove', function(e) {
      if (!resizeState.resizing) return;
      e.preventDefault();
      var delta = e.clientX - resizeState.startX;
      var newWidth = Math.max(50, resizeState.startWidth + delta);
      resizeState.thElement.style.width = newWidth + 'px';
      resizeState.thElement.style.minWidth = newWidth + 'px';
    });

    document.addEventListener('mouseup', function() {
      if (!resizeState.resizing) return;
      var finalWidth = resizeState.thElement.getBoundingClientRect().width;
      columnWidths[resizeState.columnKey] = finalWidth;
      saveColumnWidths();
      resizeState.thElement.classList.remove('resizing');
      resizeState = {
        resizing: false,
        columnKey: null,
        startX: 0,
        startWidth: 0,
        thElement: null
      };
      document.body.style.cursor = '';
    });
  }

  /**
   * @function
   */
  function addFilterRow(table, columnNames) {
    var thead = table.querySelector('thead');
    if (!thead) return;

    var filterRow = document.createElement('tr');
    filterRow.className = 'filter-row';

    columnNames.forEach(function(colName, index) {
      var td = document.createElement('td');
      if (index < 3) { // Don't add filter for Actions column
        var input = document.createElement('input');
        input.type = 'text';
        input.className = 'filter-input';
        input.setAttribute('data-column', colName);
        input.placeholder = t('Filter...');
        input.addEventListener('input', function() {
          tableState.filterValues[colName] = this.value.toLowerCase();
          applyFiltersAndSort();
        });
        td.appendChild(input);
      }
      filterRow.appendChild(td);
    });

    thead.appendChild(filterRow);
  }

  /**
   * @function
   */
  function setupSortHandlers(table) {
    table.querySelectorAll('.sort-btn').forEach(function(btn) {
      btn.addEventListener('click', function() {
        var column = this.getAttribute('data-column');
        
        if (tableState.sortColumn === column) {
          tableState.sortDirection = tableState.sortDirection === 'asc' ? 'desc' : 'asc';
        } else {
          tableState.sortColumn = column;
          tableState.sortDirection = 'asc';
        }

        // Update sort indicators
        table.querySelectorAll('.sort-btn').forEach(function(b) {
          b.classList.remove('sorted-asc', 'sorted-desc');
        });
        this.classList.add('sorted-' + tableState.sortDirection);

        applyFiltersAndSort();
      });
    });
  }

  /**
   * @function
   */
  function applyFiltersAndSort() {
    var table = document.querySelector('.form-versions-table');
    if (!table || !originalRows.length) return;

    var tbody = table.querySelector('tbody');
    
    // Filter rows
    var filteredRows = originalRows.filter(function(row) {
      var cells = row.querySelectorAll('td');
      
      // Check date filter
      if (tableState.filterValues.date) {
        var dateText = cells[0] ? cells[0].textContent.toLowerCase() : '';
        if (dateText.indexOf(tableState.filterValues.date) === -1) {
          return false;
        }
      }
      
      // Check user filter
      if (tableState.filterValues.user) {
        var userText = cells[1] ? cells[1].textContent.toLowerCase() : '';
        if (userText.indexOf(tableState.filterValues.user) === -1) {
          return false;
        }
      }
      
      // Check version filter
      if (tableState.filterValues.version) {
        var versionText = cells[2] ? cells[2].textContent.toLowerCase() : '';
        if (versionText.indexOf(tableState.filterValues.version) === -1) {
          return false;
        }
      }
      
      return true;
    });

    // Sort rows
    if (tableState.sortColumn) {
      filteredRows.sort(function(a, b) {
        var aCells = a.querySelectorAll('td');
        var bCells = b.querySelectorAll('td');
        var aVal, bVal;
        
        switch (tableState.sortColumn) {
          case 'date':
            aVal = aCells[0] ? aCells[0].textContent.trim() : '';
            bVal = bCells[0] ? bCells[0].textContent.trim() : '';
            break;
          case 'user':
            aVal = aCells[1] ? aCells[1].textContent.trim().toLowerCase() : '';
            bVal = bCells[1] ? bCells[1].textContent.trim().toLowerCase() : '';
            break;
          case 'version':
            aVal = aCells[2] ? aCells[2].textContent.trim().toLowerCase() : '';
            bVal = bCells[2] ? bCells[2].textContent.trim().toLowerCase() : '';
            break;
          default:
            return 0;
        }
        
        if (aVal < bVal) return tableState.sortDirection === 'asc' ? -1 : 1;
        if (aVal > bVal) return tableState.sortDirection === 'asc' ? 1 : -1;
        return 0;
      });
    }

    // Rebuild tbody
    tbody.innerHTML = '';
    filteredRows.forEach(function(row) {
      tbody.appendChild(row);
    });

    // Show "no results" message if empty
    if (filteredRows.length === 0) {
      var emptyRow = document.createElement('tr');
      var emptyCell = document.createElement('td');
      emptyCell.colSpan = 4;
      emptyCell.className = 'no-data';
      emptyCell.textContent = t('No versions match your filters.');
      emptyRow.appendChild(emptyCell);
      tbody.appendChild(emptyRow);
    }
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
