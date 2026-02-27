/**
 * Survey overview table logic for @@survey-overview and templates overview.
 * Uses a lightweight vanilla JavaScript table implementation with sorting, filtering, and pagination.
 */

/**
 * Initialize the survey overview table once the DOM is ready.
 * @param {Event} event
 */
function handleSurveyOverviewReady(event) {
    const defaultTranslate = function (msgid) {
        return msgid;
    };
    const t = window._t || defaultTranslate;

    const gridMount = document.getElementById("survey-overview-grid");
    if (!gridMount) {
        return;
    }

    const dataEl = document.getElementById("survey-overview-data");
    let data = Array.isArray(window.SURVEY_OVERVIEW_DATA) ? window.SURVEY_OVERVIEW_DATA : [];
    if (dataEl && dataEl.textContent) {
        try {
            const parsed = JSON.parse(dataEl.textContent);
            if (Array.isArray(parsed)) {
                data = parsed;
            }
        } catch (error) {
            console.error("Failed to parse survey overview data", error);
        }
    }

    const configEl = document.getElementById("survey-overview-config");
    let config = {};
    if (configEl && configEl.textContent) {
        try {
            config = JSON.parse(configEl.textContent) || {};
        } catch (error) {
            console.error("Failed to parse survey overview config", error);
        }
    }
    const isTemplatesMode = config.mode === "templates" || window.SURVEY_OVERVIEW_MODE === "templates";
    const templateAction = config.templateAction || window.SURVEY_TEMPLATE_ACTION || {};

    const pagerMount = document.getElementById("survey-overview-pager");

    // Store metadata toggle state for each row
    const metadataToggleState = new Map();

    /**
     * Escape text for HTML output.
     * @param {string} text
     * @returns {string}
     */
    function escapeHtml(text) {
        const div = document.createElement("div");
        div.textContent = text == null ? "" : String(text);
        return div.innerHTML;
    }

    /**
     * Render survey cell content.
     * @param {Object} row
     * @returns {string}
     */
    function renderSurveyCell(row) {
        const rowId = row.url || row.title || "";
        const isOpen = metadataToggleState.get(rowId) || false;

        const title = escapeHtml(row.title || "");
        const url = escapeHtml(row.url || "#");
        const description = row.description
            ? `<div class="survey-overview-description">${escapeHtml(row.description)}</div>`
            : "";
        const metadata = Array.isArray(row.metadata) ? row.metadata : [];
        let metadataBlock = "";
        if (metadata.length) {
            const items = metadata
                .map((item) => {
                    const label = escapeHtml(item.label || "");
                    const value = escapeHtml(item.value || "");
                    const full = escapeHtml(item.value_full || "");
                    const titleAttr = full ? ` title="${full}"` : "";
                    return `<div class="survey-overview-meta-item"><span class="survey-overview-meta-label">${label}:</span><span class="survey-overview-meta-value"${titleAttr}>${value}</span></div>`;
                })
                .join("");
            const openClass = isOpen ? " is-open" : "";
            const ariaExpanded = isOpen ? "true" : "false";
            const gridBlock = isOpen ? `<div class="survey-overview-meta-grid-wrapper"><div class="survey-overview-meta-grid">${items}</div></div>` : "";
            metadataBlock = `
                <div class="survey-overview-meta${openClass}">
                    <button type="button" class="survey-overview-meta-toggle" aria-expanded="${ariaExpanded}" data-row-id="${escapeHtml(rowId)}">
                        ${escapeHtml(t("Metadata"))}
                    </button>
                </div>
                ${gridBlock}
            `;
        }
        return `
            <div class="survey-overview-cell-wrapper">
                <div class="survey-overview-content">
                    <div><a href="${url}">${title}</a></div>
                    ${description}
                </div>
                ${metadataBlock}
            </div>
        `;
    }

    /**
     * Render status cell content.
     * @param {Object} row
     * @returns {string}
     */
    function renderStatusCell(row) {
        const status = escapeHtml(row.review_state || "");
        const effective = escapeHtml(row.effective || "");
        const expires = escapeHtml(row.expires || "");
        const showAsterisk = row.expires_future ? '<span class="survey-overview-asterisk">*</span>' : "";

        let dates = "";
        if (effective && expires) {
            dates = `<div class="survey-overview-dates">${effective} - ${expires}${showAsterisk}</div>`;
        } else if (effective) {
            dates = `<div class="survey-overview-dates">${effective}</div>`;
        } else if (expires) {
            dates = `<div class="survey-overview-dates">${expires}${showAsterisk}</div>`;
        }

        return `<div>${status}</div>${dates}`;
    }

    /**
     * Render template action button.
     * @param {Object} row
     * @returns {string}
     */
    function renderActionCell(row) {
        const uid = escapeHtml(row.uid || "");
        if (!uid) {
            return "";
        }
        return `<button type="button" class="survey-overview-action-btn" data-template-uid="${uid}">${escapeHtml(t("Create form"))}</button>`;
    }

    /**
     * Submit a create-from-template action.
     * @param {string} uid
     */
    function createFromTemplate(uid) {
        if (!uid || !templateAction.createUrl) {
            return;
        }
        const form = document.createElement("form");
        form.method = "post";
        form.action = templateAction.createUrl;

        const authInput = document.createElement("input");
        authInput.type = "hidden";
        authInput.name = "_authenticator";
        authInput.value = templateAction.authenticator || "";
        form.appendChild(authInput);

        const actionInput = document.createElement("input");
        actionInput.type = "hidden";
        actionInput.name = "pfs_action";
        actionInput.value = "create_from_template";
        form.appendChild(actionInput);

        const uidInput = document.createElement("input");
        uidInput.type = "hidden";
        uidInput.name = "template_uid";
        uidInput.value = uid;
        form.appendChild(uidInput);

        document.body.appendChild(form);
        form.submit();
    }

    // Table state
    let tableState = {
        data: data,
        filteredData: [...data],
        sortColumn: null,
        sortDirection: 'asc',
        filterValues: {},
        currentPage: 1,
        pageSize: 10,
    };

    // Column width storage
    const columnWidthsKey = 'surveyjs_overview_column_widths';
    let columnWidths = {};
    try {
        const saved = localStorage.getItem(columnWidthsKey);
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

    // Column resizing state
    let resizeState = {
        resizing: false,
        columnKey: null,
        startX: 0,
        startWidth: 0,
        thElement: null
    };

    const columns = [
        {
            key: "title",
            title: isTemplatesMode ? t("Template") : t("Forms"),
            sortable: true,
            filterable: true,
            render: renderSurveyCell,
        },
        {
            key: "review_state",
            title: t("Workflow status"),
            sortable: true,
            filterable: true,
            render: renderStatusCell,
            align: "center",
        },
        {
            key: "language",
            title: t("Language"),
            sortable: true,
            filterable: true,
            align: "center",
        },
    ];

    if (isTemplatesMode && templateAction.canCreate) {
        columns.push({
            key: "actions",
            title: t("Action"),
            sortable: false,
            filterable: false,
            render: renderActionCell,
            align: "center",
        });
    }

    /**
     * Apply filters and sorting to data.
     */
    function processData() {
        let result = [...tableState.data];

        // Apply filters
        columns.forEach(col => {
            if (col.filterable && tableState.filterValues[col.key]) {
                const filterValue = tableState.filterValues[col.key].toLowerCase();
                result = result.filter(row => {
                    const value = row[col.key];
                    if (value == null) return false;
                    return String(value).toLowerCase().includes(filterValue);
                });
            }
        });

        // Apply sorting
        if (tableState.sortColumn) {
            const col = columns.find(c => c.key === tableState.sortColumn);
            result.sort((a, b) => {
                let valA = a[tableState.sortColumn];
                let valB = b[tableState.sortColumn];
                
                if (valA == null) valA = "";
                if (valB == null) valB = "";
                
                valA = String(valA).toLowerCase();
                valB = String(valB).toLowerCase();
                
                if (valA < valB) return tableState.sortDirection === 'asc' ? -1 : 1;
                if (valA > valB) return tableState.sortDirection === 'asc' ? 1 : -1;
                return 0;
            });
        }

        tableState.filteredData = result;
        tableState.currentPage = 1;
        render();
    }

    /**
     * Get current page data.
     */
    function getPageData() {
        const start = (tableState.currentPage - 1) * tableState.pageSize;
        const end = start + tableState.pageSize;
        return tableState.filteredData.slice(start, end);
    }

    /**
     * Get total pages.
     */
    function getTotalPages() {
        return Math.ceil(tableState.filteredData.length / tableState.pageSize) || 1;
    }

    /**
     * Render the table.
     */
    function render() {
        const pageData = getPageData();
        
        // Build table HTML
        let html = '<table class="survey-overview-table">';
        
        // Header
        html += '<thead><tr>';
        columns.forEach(col => {
            const sortClass = tableState.sortColumn === col.key 
                ? ` sorted-${tableState.sortDirection}` 
                : '';
            const savedWidth = columnWidths[col.key];
            const widthStyle = savedWidth ? `width: ${savedWidth}px; min-width: ${savedWidth}px;` : '';
            const alignStyle = col.align ? `text-align: ${col.align};` : '';
            const styleAttr = (widthStyle || alignStyle) ? ` style="${widthStyle}${alignStyle}"` : '';
            html += `<th data-column="${col.key}"${styleAttr}>`;
            html += '<div class="th-content">';
            if (col.sortable) {
                html += `<button type="button" class="sort-btn${sortClass}" data-column="${col.key}">${escapeHtml(col.title)}</button>`;
            } else {
                html += escapeHtml(col.title);
            }
            html += '</div>';
            html += `<div class="resize-handle" data-column="${col.key}"></div>`;
            html += '</th>';
        });
        html += '</tr>';
        
        // Filter row
        html += '<tr class="filter-row">';
        columns.forEach(col => {
            const alignAttr = col.align ? ` style="text-align: ${col.align};"` : '';
            html += `<td${alignAttr}>`;
            if (col.filterable) {
                const filterValue = tableState.filterValues[col.key] || '';
                html += `<input type="text" class="filter-input" data-column="${col.key}" placeholder="${escapeHtml(t('Filter...'))}" value="${escapeHtml(filterValue)}">`;
            }
            html += '</td>';
        });
        html += '</tr></thead>';
        
        // Body
        html += '<tbody>';
        if (pageData.length === 0) {
            const colspan = columns.length;
            const emptyMessage = isTemplatesMode 
                ? t("No survey templates found below this location.") 
                : t("No surveys found below this location.");
            html += `<tr><td colspan="${colspan}" class="no-data">${escapeHtml(emptyMessage)}</td></tr>`;
        } else {
            pageData.forEach(row => {
                html += '<tr>';
                columns.forEach(col => {
                    const alignAttr = col.align ? ` style="text-align: ${col.align};"` : '';
                    if (col.render) {
                        html += `<td${alignAttr}>${col.render(row)}</td>`;
                    } else {
                        html += `<td${alignAttr}>${escapeHtml(row[col.key] || '')}</td>`;
                    }
                });
                html += '</tr>';
            });
        }
        html += '</tbody></table>';
        
        gridMount.innerHTML = html;
        
        // Attach event listeners
        attachTableEvents();
        
        // Render pagination
        renderPagination();
    }

    /**
     * Attach event listeners to table elements.
     */
    function attachTableEvents() {
        // Sort buttons
        gridMount.querySelectorAll('.sort-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const column = e.currentTarget.dataset.column;
                if (tableState.sortColumn === column) {
                    tableState.sortDirection = tableState.sortDirection === 'asc' ? 'desc' : 'asc';
                } else {
                    tableState.sortColumn = column;
                    tableState.sortDirection = 'asc';
                }
                processData();
            });
        });
        
        // Filter inputs
        gridMount.querySelectorAll('.filter-input').forEach(input => {
            input.addEventListener('input', (e) => {
                const column = e.currentTarget.dataset.column;
                tableState.filterValues[column] = e.currentTarget.value;
                processData();
            });
        });
        
        // Metadata toggles
        gridMount.querySelectorAll('.survey-overview-meta-toggle').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                const rowId = e.currentTarget.dataset.rowId;
                const currentState = metadataToggleState.get(rowId) || false;
                metadataToggleState.set(rowId, !currentState);
                render();
            });
        });
        
        // Action buttons
        gridMount.querySelectorAll('.survey-overview-action-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                const uid = e.currentTarget.dataset.templateUid;
                createFromTemplate(uid);
            });
        });

        // Column resize handles
        gridMount.querySelectorAll('.resize-handle').forEach(handle => {
            handle.addEventListener('mousedown', (e) => {
                e.preventDefault();
                e.stopPropagation();
                const columnKey = e.currentTarget.dataset.column;
                const th = e.currentTarget.closest('th');
                const rect = th.getBoundingClientRect();
                resizeState = {
                    resizing: true,
                    columnKey: columnKey,
                    startX: e.clientX,
                    startWidth: rect.width,
                    thElement: th
                };
                document.body.style.cursor = 'col-resize';
                th.classList.add('resizing');
            });
        });
    }

    /**
     * Render pagination controls.
     */
    function renderPagination() {
        if (!pagerMount) return;
        
        const totalPages = getTotalPages();
        const totalItems = tableState.filteredData.length;
        const startItem = totalItems === 0 ? 0 : (tableState.currentPage - 1) * tableState.pageSize + 1;
        const endItem = Math.min(tableState.currentPage * tableState.pageSize, totalItems);
        
        let html = '<div class="pagination-container">';
        
        // Page size selector
        html += '<div class="page-size">';
        html += `<span>${escapeHtml(t('Page Size'))}:</span>`;
        html += '<select class="page-size-select">';
        [10, 25, 50, 100].forEach(size => {
            const selected = size === tableState.pageSize ? ' selected' : '';
            html += `<option value="${size}"${selected}>${size}</option>`;
        });
        html += '</select></div>';
        
        // Page info
        html += `<div class="page-info">${startItem}-${endItem} ${escapeHtml(t('of'))} ${totalItems}</div>`;
        
        // Page buttons
        html += '<div class="page-buttons">';
        
        // First
        const firstDisabled = tableState.currentPage === 1 ? ' disabled' : '';
        html += `<button type="button" class="page-btn" data-page="1"${firstDisabled}>${escapeHtml(t('First'))}</button>`;
        
        // Prev
        const prevDisabled = tableState.currentPage === 1 ? ' disabled' : '';
        html += `<button type="button" class="page-btn" data-page="${tableState.currentPage - 1}"${prevDisabled}>${escapeHtml(t('Prev'))}</button>`;
        
        // Page numbers
        const maxButtons = 5;
        let startPage = Math.max(1, tableState.currentPage - Math.floor(maxButtons / 2));
        let endPage = Math.min(totalPages, startPage + maxButtons - 1);
        if (endPage - startPage < maxButtons - 1) {
            startPage = Math.max(1, endPage - maxButtons + 1);
        }
        
        for (let i = startPage; i <= endPage; i++) {
            const active = i === tableState.currentPage ? ' active' : '';
            html += `<button type="button" class="page-btn${active}" data-page="${i}">${i}</button>`;
        }
        
        // Next
        const nextDisabled = tableState.currentPage === totalPages ? ' disabled' : '';
        html += `<button type="button" class="page-btn" data-page="${tableState.currentPage + 1}"${nextDisabled}>${escapeHtml(t('Next'))}</button>`;
        
        // Last
        const lastDisabled = tableState.currentPage === totalPages ? ' disabled' : '';
        html += `<button type="button" class="page-btn" data-page="${totalPages}"${lastDisabled}>${escapeHtml(t('Last'))}</button>`;
        
        html += '</div></div>';
        
        pagerMount.innerHTML = html;
        
        // Attach pagination event listeners
        pagerMount.querySelectorAll('.page-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                if (e.currentTarget.disabled) return;
                const page = parseInt(e.currentTarget.dataset.page, 10);
                if (page >= 1 && page <= totalPages) {
                    tableState.currentPage = page;
                    render();
                }
            });
        });
        
        pagerMount.querySelector('.page-size-select')?.addEventListener('change', (e) => {
            tableState.pageSize = parseInt(e.currentTarget.value, 10);
            tableState.currentPage = 1;
            render();
        });
    }

    // Column resize document-level handlers
    document.addEventListener('mousemove', (e) => {
        if (!resizeState.resizing) return;
        e.preventDefault();
        const delta = e.clientX - resizeState.startX;
        const newWidth = Math.max(50, resizeState.startWidth + delta);
        resizeState.thElement.style.width = newWidth + 'px';
        resizeState.thElement.style.minWidth = newWidth + 'px';
    });

    document.addEventListener('mouseup', () => {
        if (!resizeState.resizing) return;
        const finalWidth = resizeState.thElement.getBoundingClientRect().width;
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

    // Initial render
    processData();
}

document.addEventListener("DOMContentLoaded", handleSurveyOverviewReady);
