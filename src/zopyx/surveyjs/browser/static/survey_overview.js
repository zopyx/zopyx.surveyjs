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

    function escapeHtml(text) {
        const div = document.createElement("div");
        div.textContent = text == null ? "" : String(text);
        return div.innerHTML;
    }

    function surveyFormatter(cell) {
        const row = cell.getData() || {};
        const title = escapeHtml(row.title || "");
        const url = escapeHtml(row.url || "#");
        const description = row.description
            ? `<div class="survey-overview-description">${escapeHtml(row.description)}</div>`
            : "";
        return `<div><a href="${url}">${title}</a></div>${description}`;
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

    new Tabulator(gridMount, {
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
