/**
 * Survey overview grid logic for @@survey-overview and templates overview.
 * Builds Tabulator table, metadata toggles, and template actions.
 */
/**
 * Initialize the survey overview grid once the DOM is ready.
 * @param {Event} event
 */
function handleSurveyOverviewReady(event) {
    /**
     * Default translation fallback.
     * @param {string} msgid
     * @returns {string}
     */
    const defaultTranslate = function (msgid) {
        return msgid;
    };
    const t = window._t || defaultTranslate;

    const gridMount = document.getElementById("survey-overview-grid");
    if (!gridMount) {
        return;
    }

    if (typeof Tabulator === "undefined") {
        const notice = document.createElement("div");
        notice.className = "survey-overview-empty";
        notice.textContent = t("Tabulator assets missing. Please install tabulator.min.js and tabulator.min.css in ++resource++zopyx.surveyjs/vendor/.");
        gridMount.appendChild(notice);
        console.error("Tabulator assets missing. Provide vendor/tabulator.min.js and vendor/tabulator.min.css.");
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
    const rawLocale = window.SURVEYJS_I18N_LOCALE || navigator.language || "en";
    const tabulatorLocale = String(rawLocale).split("-")[0] || "en";

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
     * @param {Object} cell
     * @returns {string}
     */
    function surveyFormatter(cell) {
        const row = cell.getData() || {};
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
/**
 * @function
 */
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
            const hiddenAttr = isOpen ? "" : " hidden";
            const gridBlock = isOpen ? `<div class="survey-overview-meta-grid-wrapper"><div class="survey-overview-meta-grid">${items}</div></div>` : "";
            metadataBlock = `
                <div class="survey-overview-meta${openClass}">
                    <button type="button" class="survey-overview-meta-toggle" aria-expanded="${ariaExpanded}">
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
     * @param {Object} cell
     * @returns {string}
     */
    function statusFormatter(cell) {
        const row = cell.getData() || {};
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

    const pagerMount = document.getElementById("survey-overview-pager");
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

    const tabulatorLangs = {};
    tabulatorLangs[tabulatorLocale] = {
        "pagination": {
            "first": t("First"),
            "first_title": t("First Page"),
            "last": t("Last"),
            "last_title": t("Last Page"),
            "prev": t("Prev"),
            "prev_title": t("Prev Page"),
            "next": t("Next"),
            "next_title": t("Next Page"),
            "all": t("All"),
            "page_size": t("Page Size"),
        },
    };

    const templateAction = config.templateAction || window.SURVEY_TEMPLATE_ACTION || {};

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

    /**
     * Toggle metadata expansion for a row.
     * @param {MouseEvent} event
     * @param {Object} cell
     */
    function handleMetadataToggleClick(event, cell) {
        const target = event.target;
        if (!target || !target.closest) {
            return;
        }
        const toggle = target.closest(".survey-overview-meta-toggle");
        if (!toggle) {
            return;
        }
        event.preventDefault();
        event.stopPropagation();

        const row = cell.getData() || {};
        const rowId = row.url || row.title || "";
        const currentState = metadataToggleState.get(rowId) || false;
        metadataToggleState.set(rowId, !currentState);

        table.redraw(true);
    }

    const columns = [
        {
            title: isTemplatesMode ? t("Template") : t("Forms"),
            field: "title",
            formatter: surveyFormatter,
            sorter: "string",
            minWidth: 240,
            variableHeight: true,
            cssClass: "survey-overview-col",
            cellClick: handleMetadataToggleClick,
            headerFilter: "input",
            headerSort: true,
        },
        {
            title: t("Workflow status"),
            field: "review_state",
            formatter: statusFormatter,
            sorter: "string",
            width: 160,
            hozAlign: "center",
            headerHozAlign: "center",
            headerFilter: "input",
            headerSort: true,
        },
        {
            title: t("Language"),
            field: "language",
            sorter: "string",
            width: 110,
            hozAlign: "center",
            headerHozAlign: "center",
            headerFilter: "input",
            headerSort: true,
        },
    ];

    if (isTemplatesMode && templateAction.canCreate) {
        /**
         * Render the template action button.
         * @param {Object} cell
         * @returns {string}
         */
        function templateActionFormatter(cell) {
            const row = cell.getData() || {};
            const uid = escapeHtml(row.uid || "");
            if (!uid) {
                return "";
            }
            return `<button type="button" class="survey-overview-action-btn" data-template-uid="${uid}">${escapeHtml(t("Create form"))}</button>`;
        }
        /**
         * Handle template action button clicks.
         * @param {MouseEvent} event
         * @param {Object} cell
         */
        function handleTemplateActionClick(event, cell) {
            const target = event.target;
            if (!target || !target.closest) {
                return;
            }
            const button = target.closest(".survey-overview-action-btn");
            if (!button) {
                return;
            }
            event.preventDefault();
            event.stopPropagation();
            createFromTemplate(button.getAttribute("data-template-uid") || "");
        }
        columns.push({
            title: t("Action"),
            field: "actions",
            headerSort: false,
            width: 160,
            hozAlign: "center",
            headerHozAlign: "center",
            formatter: templateActionFormatter,
            cellClick: handleTemplateActionClick,
        });
    }

    const table = new Tabulator(gridMount, {
        data,
        layout: "fitColumns",
        responsiveLayout: "collapse",
        placeholder: isTemplatesMode ? t("No survey templates found below this location.") : t("No surveys found below this location."),
        pagination: "local",
        paginationSize: 10,
        paginationSizeSelector: [10, 25, 50, 100],
        paginationElement: pagerMount || undefined,
        locale: tabulatorLocale,
        langs: tabulatorLangs,
        columns: columns,
    });

}

document.addEventListener("DOMContentLoaded", handleSurveyOverviewReady);
