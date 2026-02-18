document.addEventListener("DOMContentLoaded", function () {
    const t = window._t || function (msgid) {
        return msgid;
    };

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

    const data = Array.isArray(window.SURVEY_OVERVIEW_DATA) ? window.SURVEY_OVERVIEW_DATA : [];
    const rawLocale = window.SURVEYJS_I18N_LOCALE || navigator.language || "en";
    const tabulatorLocale = String(rawLocale).split("-")[0] || "en";

    // Store metadata toggle state for each row
    const metadataToggleState = new Map();

    function escapeHtml(text) {
        const div = document.createElement("div");
        div.textContent = text == null ? "" : String(text);
        return div.innerHTML;
    }

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

    const table = new Tabulator(gridMount, {
        data,
        layout: "fitColumns",
        responsiveLayout: "collapse",
        placeholder: t("No surveys found below this location."),
        pagination: "local",
        paginationSize: 10,
        paginationSizeSelector: [10, 25, 50, 100],
        paginationElement: pagerMount || undefined,
        locale: tabulatorLocale,
        langs: tabulatorLangs,
        columns: [
            {
                title: t("Survey"),
                field: "title",
                formatter: surveyFormatter,
                sorter: "string",
                minWidth: 240,
                variableHeight: true,
                cssClass: "survey-overview-col",
                cellClick: function (event, cell) {
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
                },
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
                title: t("Submitted"),
                field: "results_count",
                sorter: "number",
                hozAlign: "center",
                headerHozAlign: "center",
                width: 120,
                headerSort: true,
            },
            {
                title: t("Security mode"),
                field: "access_mode",
                sorter: "string",
                width: 140,
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
        ],
    });

});
