document.addEventListener("DOMContentLoaded", function () {
    const t = window._t || function (msgid, mapping) {
        if (!mapping) {
            return msgid;
        }
        return msgid.replace(/\$\{([a-zA-Z0-9_]+)\}/g, function (match, key) {
            if (Object.prototype.hasOwnProperty.call(mapping, key)) {
                return String(mapping[key]);
            }
            return match;
        });
    };

    const config = window.RESULTS2_CONFIG || {};
    const formats = Array.isArray(config.converterFormats) ? config.converterFormats : [];
    const isManager = Boolean(config.isManager);
    const hasMailAction = Boolean(config.hasMailAction);
    const hasPostAction = Boolean(config.hasPostAction);
    const authToken = config.authenticator || "";
    const gridMount = document.getElementById("results2-grid");

    if (typeof Tabulator === "undefined") {
        if (gridMount) {
            const notice = document.createElement("div");
            notice.className = "results2-empty";
            notice.textContent = t("Tabulator assets missing. Please install tabulator.min.js and tabulator.min.css in ++resource++zopyx.surveyjs/vendor/.");
            gridMount.appendChild(notice);
        }
        console.error("Tabulator assets missing. Provide vendor/tabulator.min.js and vendor/tabulator.min.css.");
        return;
    }

    const modal = document.getElementById("json-modal");
    const closeButton = document.querySelector(".close-button");
    const jsonContent = document.getElementById("json-content");

    const detailsModal = document.getElementById("details-modal");
    const detailsCloseButton = document.querySelector(".details-close-button");
    const detailsContent = document.getElementById("details-content");

    const totalCountEl = document.getElementById("results2-total-count");
    const deleteSelectedBtn = document.getElementById("results2-delete-selected-btn");

    const questionLabels = {};
    const questionDefinitions = {};

    fetch("get-form-json", { credentials: "same-origin" })
        .then(response => response.json())
        .then(data => {
            (data.pages || []).forEach(page => {
                (page.elements || []).forEach(element => {
                    if (element.name) {
                        questionLabels[element.name] = element.title || element.name;
                        questionDefinitions[element.name] = element;
                    }
                });
            });
        })
        .catch(() => {
            // Best-effort label mapping; fall back to keys on failure.
        });

    function updateTotalCount(count) {
        if (totalCountEl) {
            totalCountEl.textContent = String(count || 0);
        }
    }

    function escapeHtml(text) {
        const div = document.createElement("div");
        div.textContent = text;
        return div.innerHTML;
    }

    function shortenId(value) {
        if (!value) {
            return "";
        }
        const text = String(value);
        if (text.length <= 12) {
            return escapeHtml(text);
        }
        const head = text.slice(0, 6);
        const tail = text.slice(-6);
        return `${escapeHtml(head)}...${escapeHtml(tail)}`;
    }

    function idFormatter(cell) {
        const value = cell.getValue();
        if (!value) {
            return "";
        }
        const full = escapeHtml(String(value));
        const short = shortenId(value);
        return `<span title="${full}">${short}</span>`;
    }

    function showGridError(message) {
        if (!gridMount) {
            return;
        }
        const notice = document.createElement("div");
        notice.className = "results2-empty";
        notice.textContent = message;
        gridMount.innerHTML = "";
        gridMount.appendChild(notice);
    }

    function renderMatrixTable(value, element) {
        if (!element) {
            return null;
        }

        if (element.type === "matrixdynamic" && Array.isArray(value)) {
            const columnDefs = (element.columns || []).map(col => ({
                key: col.name || col.value || col.title || "",
                label: col.title || col.name || col.value || "",
            }));

            const allKeys = Array.from(
                new Set(
                    columnDefs.length
                        ? columnDefs.map(col => col.key)
                        : value.flatMap(row => Object.keys(row || {})),
                ),
            ).filter(Boolean);

            const headers = columnDefs.length
                ? columnDefs
                : allKeys.map(key => ({ key, label: key }));

            let html = "<table class='details-table matrix-table'>";
            html += "<thead><tr>";
            headers.forEach(col => {
                html += `<th>${escapeHtml(col.label)}</th>`;
            });
            html += "</tr></thead><tbody>";

            value.forEach(row => {
                html += "<tr>";
                headers.forEach(col => {
                    const cell = row ? row[col.key] : "";
                    html += `<td>${escapeHtml(cell != null ? String(cell) : "")}</td>`;
                });
                html += "</tr>";
            });

            html += "</tbody></table>";
            return html;
        }

        if (element.type === "matrix" && value && typeof value === "object" && !Array.isArray(value)) {
            const rows = Object.entries(value);
            const rowDefs = element.rows || [];
            const columnDefs = element.columns || [];

            const columnLookup = new Map(
                columnDefs
                    .filter(col => col && (col.value || col.name))
                    .map(col => [col.value || col.name, col.text || col.title || col.name]),
            );

            let html = "<table class='details-table matrix-table'>";
            html += "<thead><tr><th>" + t("Row") + "</th><th>" + t("Answer") + "</th></tr></thead><tbody>";

            rows.forEach(([rowKey, answer]) => {
                const rowLabel =
                    (rowDefs.find(r => r && (r.value === rowKey || r.name === rowKey)) || {})
                        .text ||
                    rowKey;
                let answerText;
                if (typeof answer === "string") {
                    answerText = columnLookup.get(answer) || answer;
                } else if (Array.isArray(answer)) {
                    answerText = answer
                        .map(val => columnLookup.get(val) || String(val))
                        .join(", ");
                } else if (answer && typeof answer === "object") {
                    answerText = Object.entries(answer)
                        .map(([k, v]) => `${k}: ${v}`)
                        .join(", ");
                } else {
                    answerText = answer != null ? String(answer) : "";
                }

                html += "<tr>";
                html += `<td>${escapeHtml(String(rowLabel))}</td>`;
                html += `<td>${escapeHtml(answerText)}</td>`;
                html += "</tr>";
            });

            html += "</tbody></table>";
            return html;
        }

        return null;
    }

    function renderDetailsTable(data) {
        let html = "<table class='details-table'>";
        html += "<thead><tr><th>" + t("Key / Question") + "</th><th>" + t("Answer") + "</th></tr></thead>";
        html += "<tbody>";

        for (const [key, value] of Object.entries(data)) {
            const label = questionLabels[key] || key;
            const questionDef = questionDefinitions[key];
            html += "<tr>";
            html += "<td class=\"question-cell\">";
            html += `<span class="question-key">${escapeHtml(key)}</span>`;
            html += `<span class="question-label">${escapeHtml(label)}</span>`;
            html += "</td>";
            html += "<td class=\"answer-cell\">";

            const matrixHtml = renderMatrixTable(value, questionDef);

            if (matrixHtml) {
                html += matrixHtml;
            } else if (Array.isArray(value) && value.length > 0) {
                const item = value[0];
                if (typeof item === "object" && item !== null && "name" in item && "content" in item) {
                    if (item.type && item.type.includes("image")) {
                        html += `<div class="image-preview"><img src="${item.content}" alt="${escapeHtml(item.name)}" /></div>`;
                    } else {
                        html += t("Attached file: ${name}", { name: escapeHtml(item.name) });
                    }
                } else {
                    html += value.map(v => escapeHtml(String(v))).join("<br>");
                }
            } else if (typeof value === "string" && value.startsWith("data:image/")) {
                html += `<div class="image-preview"><img src="${value}" alt="${escapeHtml(key)}" /></div>`;
            } else if (typeof value === "object" && value !== null) {
                html += Object.entries(value)
                    .map(([k, v]) => `${escapeHtml(k)}: ${escapeHtml(String(v))}`)
                    .join("<br>");
            } else {
                html += escapeHtml(String(value));
            }

            html += "</td></tr>";
        }

        html += "</tbody></table>";
        detailsContent.innerHTML = html;
    }

    function openJsonModal(pollId) {
        fetch(`${config.viewJsonUrlBase}${encodeURIComponent(pollId)}`, { credentials: "same-origin" })
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                jsonContent.textContent = JSON.stringify(data, null, 2);
                modal.style.display = "block";
            })
            .catch(error => {
                console.error(t("Error fetching JSON:"), error);
                alert(t("Failed to load JSON data. Please check the console for more information."));
            });
    }

    function openDetailsModal(pollId) {
        fetch(`${config.viewJsonUrlBase}${encodeURIComponent(pollId)}`, { credentials: "same-origin" })
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                if (data.error) {
                    alert(t("Error: ${error}", { error: data.error }));
                    return;
                }
                renderDetailsTable(data);
                detailsModal.style.display = "block";
            })
            .catch(error => {
                console.error(t("Error fetching details:"), error);
                alert(t("Failed to load details. Please check the console for more information."));
            });
    }

    function deletePolls(pollIds) {
        const headers = {
            "Content-Type": "application/json"
        };
        if (authToken) {
            headers["X-CSRF-TOKEN"] = authToken;
        }

        return fetch("delete-results", {
            method: "POST",
            credentials: "same-origin",
            headers,
            body: JSON.stringify({ poll_ids: pollIds })
        }).then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json().catch(() => ({}));
        });
    }

    function createSvgIcon(pathMarkup) {
        const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        svg.setAttribute("viewBox", "0 0 24 24");
        svg.setAttribute("aria-hidden", "true");
        svg.setAttribute("focusable", "false");
        svg.classList.add("results2-icon");
        svg.innerHTML = pathMarkup;
        return svg;
    }

    function createIconButton(options) {
        const label = options.label || "";
        const tag = options.tag || "button";
        const el = document.createElement(tag);
        el.className = `btn icon-only ${options.className || ""}`.trim();
        el.setAttribute("aria-label", label);
        el.setAttribute("title", label);

        if (options.type) {
            el.type = options.type;
        }
        if (options.href) {
            el.href = options.href;
        }
        if (options.formAction) {
            el.setAttribute("formaction", options.formAction);
        }
        if (options.formMethod) {
            el.setAttribute("formmethod", options.formMethod);
        }
        if (options.onClick) {
            el.addEventListener("click", options.onClick);
        }

        if (options.svg) {
            el.appendChild(createSvgIcon(options.svg));
        } else if (options.imgSrc) {
            const img = document.createElement("img");
            img.src = options.imgSrc;
            img.alt = label;
            img.className = "results2-icon";
            el.appendChild(img);
        }

        const sr = document.createElement("span");
        sr.className = "sr-only";
        sr.textContent = label;
        el.appendChild(sr);
        return el;
    }

    let currentQuery = "";

    function actionFormatter(cell) {
        const data = cell.getRow().getData();
        const wrapper = document.createElement("div");
        wrapper.className = "results2-action-group";
        const leftGroup = document.createElement("div");
        leftGroup.className = "results2-action-left";
        const middleGroup = document.createElement("div");
        middleGroup.className = "results2-action-middle";
        const rightGroup = document.createElement("div");
        rightGroup.className = "results2-action-right";

        const jsonBtn = createIconButton({
            label: t("JSON"),
            className: "btn-primary view-json",
            type: "button",
            svg: "<path d=\"M6 3h8l4 4v14H6z\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.6\"/><path d=\"M14 3v5h5\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.6\"/><path d=\"M8 13h2m-2 4h2m2-4h4m-4 4h4\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.6\" stroke-linecap=\"round\"/>",
            onClick: function () {
                openJsonModal(data.poll_id);
            }
        });
        leftGroup.appendChild(jsonBtn);

        const tableBtn = createIconButton({
            label: t("Table"),
            className: "btn-success view-details",
            type: "button",
            svg: "<path d=\"M3 5h18v14H3z\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.6\"/><path d=\"M3 9h18M8 5v14M16 5v14\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.6\"/>",
            onClick: function () {
                openDetailsModal(data.poll_id);
            }
        });
        leftGroup.appendChild(tableBtn);

        const detailLink = createIconButton({
            tag: "a",
            label: t("Details"),
            className: "btn-secondary detail-link",
            href: `${config.detailUrlBase}${encodeURIComponent(data.poll_id)}`,
            svg: "<path d=\"M12 5c5 0 9 5 9 7s-4 7-9 7-9-5-9-7 4-7 9-7z\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.6\"/><circle cx=\"12\" cy=\"12\" r=\"2.5\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.6\"/>"
        });
        leftGroup.appendChild(detailLink);

        const form = document.createElement("form");
        form.method = "get";
        form.action = config.downloadUrl;
        form.className = "download-form results2-action-form";

        if (authToken) {
            const tokenInput = document.createElement("input");
            tokenInput.type = "hidden";
            tokenInput.name = "_authenticator";
            tokenInput.value = authToken;
            form.appendChild(tokenInput);
        }

        const pollInput = document.createElement("input");
        pollInput.type = "hidden";
        pollInput.name = "poll_id";
        pollInput.value = data.poll_id;
        form.appendChild(pollInput);

        const select = document.createElement("select");
        select.name = "format";
        formats.forEach(fmt => {
            const option = document.createElement("option");
            option.value = fmt.key;
            option.textContent = fmt.short_label || fmt.label || fmt.key;
            select.appendChild(option);
        });
        form.appendChild(select);

        const downloadBtn = createIconButton({
            label: t("Download result"),
            className: "btn-secondary download-result",
            type: "submit",
            imgSrc: "++resource++zopyx.surveyjs/icon-download.svg"
        });
        form.appendChild(downloadBtn);

        if (hasMailAction) {
            const mailBtn = createIconButton({
                label: t("Mail result"),
                className: "btn-info mail-result",
                type: "submit",
                formAction: "mail-result",
                imgSrc: "++resource++zopyx.surveyjs/icon-mail.svg"
            });
            form.appendChild(mailBtn);
        }

        if (hasPostAction) {
            const postBtn = createIconButton({
                label: t("POST result"),
                className: "btn-warning post-result",
                type: "submit",
                formAction: "post-result",
                formMethod: "post",
                imgSrc: "++resource++zopyx.surveyjs/icon-post.svg"
            });
            form.appendChild(postBtn);
        }

        middleGroup.appendChild(form);

        if (isManager) {
            const deleteBtn = createIconButton({
                label: t("Delete"),
                className: "btn-danger delete-result",
                type: "button",
                imgSrc: "++resource++zopyx.surveyjs/icon-trash.svg",
                onClick: function () {
                    const table = cell.getTable();
                    if (!confirm(t("Delete this result?"))) {
                        return;
                    }
                    deletePolls([data.poll_id])
                        .then(() => {
                            table.setData(config.resultsUrl, { q: currentQuery });
                        })
                        .catch(error => {
                            console.error(t("Error deleting result:"), error);
                            alert(t("Failed to delete the result. Please check the console for details."));
                        });
                }
            });
            rightGroup.appendChild(deleteBtn);
        }

        wrapper.appendChild(leftGroup);
        wrapper.appendChild(middleGroup);
        wrapper.appendChild(rightGroup);
        return wrapper;
    }

    const table = new Tabulator("#results2-grid", {
        ajaxURL: config.resultsUrl,
        ajaxConfig: "GET",
        ajaxRequestFunc: function (url, config, params) {
            const requestUrl = new URL(url, window.location.href);
            Object.entries(params || {}).forEach(([key, value]) => {
                if (value === null || typeof value === "undefined") {
                    return;
                }
                if (typeof value === "object") {
                    requestUrl.searchParams.set(key, JSON.stringify(value));
                } else {
                    requestUrl.searchParams.set(key, value);
                }
            });
            return fetch(requestUrl.toString(), { credentials: "same-origin" })
                .then(response => {
                    if (!response.ok) {
                        throw new Error(`HTTP error! status: ${response.status}`);
                    }
                    return response.json();
                });
        },
        ajaxSorting: true,
        ajaxFiltering: true,
        pagination: true,
        paginationMode: "remote",
        paginationSize: 25,
        paginationSizeSelector: [10, 25, 50, 100, 250],
        layout: "fitColumns",
        height: "600px",
        placeholder: t("No stored results yet. Once responses are saved, analytics will appear here."),
        index: "poll_id",
        selectable: isManager,
        initialSort: [
            { column: "created_ts", dir: "desc" }
        ],
        columns: [
            {
                formatter: "rowSelection",
                titleFormatter: "rowSelection",
                hozAlign: "center",
                headerHozAlign: "center",
                headerSort: false,
                width: 40,
                visible: isManager,
                cssClass: "results2-select-col"
            },
            {
                title: t("Date"),
                field: "created_ts",
                sorter: "number",
                headerFilter: "input",
                widthGrow: 1,
                formatter: function (cell) {
                    const data = cell.getRow().getData();
                    return data.created_display || "";
                }
            },
            {
                title: t("User"),
                field: "user",
                headerFilter: "input",
                widthGrow: 1
            },
            {
                title: t("#"),
                field: "seq_no",
                headerFilter: "input",
                hozAlign: "center",
                width: 70
            },
            {
                title: t("Poll ID"),
                field: "poll_id",
                headerFilter: "input",
                widthGrow: 1,
                formatter: idFormatter
            },
            {
                title: t("Action"),
                field: "actions",
                headerSort: false,
                formatter: actionFormatter,
                width: 322,
                maxWidth: 345,
                minWidth: 276
            }
        ],
        paginationDataSent: {
            page: "page",
            size: "size"
        },
        paginationDataReceived: {
            last_page: "last_page",
            data: "data",
            current_page: "page",
            total_rows: "total_rows"
        },
        ajaxResponse: function (url, params, response) {
            if (response && typeof response.total_rows !== "undefined") {
                updateTotalCount(response.total_rows);
            }
            return response;
        },
        ajaxError: function () {
            showGridError(t("Failed to load results. Please check the console for details."));
        }
    });

    if (isManager && deleteSelectedBtn) {
        table.on("rowSelectionChanged", function (data) {
            deleteSelectedBtn.disabled = data.length === 0;
        });

        deleteSelectedBtn.addEventListener("click", function () {
            const selected = table.getSelectedData() || [];
            if (!selected.length) {
                return;
            }
            if (!confirm(t("Delete ${count} selected result(s)?", { count: selected.length }))) {
                return;
            }
            deletePolls(selected.map(row => row.poll_id))
                .then(() => {
                    table.setData(config.resultsUrl, { q: currentQuery });
                })
                .catch(error => {
                    console.error(t("Error deleting selected results:"), error);
                    alert(t("Failed to delete selected results. Please check the console for details."));
                });
        });
    }

    const searchInput = document.getElementById("results2-search-input");
    const searchBtn = document.getElementById("results2-search-btn");
    const resetBtn = document.getElementById("results2-reset-btn");
    const refreshBtn = document.getElementById("results2-refresh-btn");

    function applySearch() {
        currentQuery = searchInput ? searchInput.value.trim() : "";
        table.setData(config.resultsUrl, { q: currentQuery });
    }

    if (searchBtn) {
        searchBtn.addEventListener("click", function () {
            applySearch();
        });
    }

    if (searchInput) {
        searchInput.addEventListener("keypress", function (event) {
            if (event.key === "Enter") {
                applySearch();
            }
        });
    }

    if (resetBtn) {
        resetBtn.addEventListener("click", function () {
            if (searchInput) {
                searchInput.value = "";
            }
            table.clearFilter(true);
            currentQuery = "";
            table.setData(config.resultsUrl, { q: currentQuery });
        });
    }

    if (refreshBtn) {
        refreshBtn.addEventListener("click", function () {
            table.setData(config.resultsUrl, { q: currentQuery });
        });
    }

    if (closeButton) {
        closeButton.addEventListener("click", function () {
            modal.style.display = "none";
        });
    }

    if (detailsCloseButton) {
        detailsCloseButton.addEventListener("click", function () {
            detailsModal.style.display = "none";
        });
    }

    window.addEventListener("click", function (event) {
        if (event.target === modal) {
            modal.style.display = "none";
        }
        if (event.target === detailsModal) {
            detailsModal.style.display = "none";
        }
    });

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape") {
            if (modal && modal.style.display === "block") {
                modal.style.display = "none";
            }
            if (detailsModal && detailsModal.style.display === "block") {
                detailsModal.style.display = "none";
            }
        }
    });

    const clearResultsBtn = document.getElementById("results2-clear-results-btn");
    const clearConfirmModal = document.getElementById("clear-confirm-modal");
    const clearCloseButton = document.querySelector(".clear-close-button");
    const clearConfirmInput = document.getElementById("clear-confirm-input");
    const clearConfirmBtn = document.getElementById("clear-confirm-btn");
    const clearCancelBtn = document.getElementById("clear-cancel-btn");
    const clearKeyword = clearConfirmInput
        ? (clearConfirmInput.dataset.clearKeyword || "clear")
        : "clear";

    if (clearResultsBtn) {
        clearResultsBtn.addEventListener("click", function () {
            clearConfirmModal.style.display = "block";
            clearConfirmInput.value = "";
            clearConfirmInput.focus();
            clearConfirmBtn.disabled = true;
        });
    }

    if (clearConfirmInput) {
        clearConfirmInput.addEventListener("input", function () {
            clearConfirmBtn.disabled = this.value.toLowerCase() !== clearKeyword.toLowerCase();
        });

        clearConfirmInput.addEventListener("keypress", function (event) {
            if (event.key === "Enter" && this.value.toLowerCase() === clearKeyword.toLowerCase()) {
                clearConfirmBtn.click();
            }
        });
    }

    if (clearConfirmBtn) {
        clearConfirmBtn.addEventListener("click", function () {
            const headers = {};
            if (authToken) {
                headers["X-CSRF-TOKEN"] = authToken;
            }

            fetch("clear-results", {
                method: "POST",
                credentials: "same-origin",
                headers
            })
                .then(response => {
                    if (!response.ok) {
                        throw new Error(`HTTP error! status: ${response.status}`);
                    }
                    return response.text();
                })
                .then(() => {
                    clearConfirmModal.style.display = "none";
                    alert(t("All results have been cleared successfully."));
                    table.setData(config.resultsUrl, { q: currentQuery });
                })
                .catch(error => {
                    console.error(t("Error clearing results:"), error);
                    alert(t("Failed to clear results. Please check the console for more information."));
                });
        });
    }

    if (clearCloseButton) {
        clearCloseButton.addEventListener("click", function () {
            clearConfirmModal.style.display = "none";
        });
    }

    if (clearCancelBtn) {
        clearCancelBtn.addEventListener("click", function () {
            clearConfirmModal.style.display = "none";
        });
    }

    window.addEventListener("click", function (event) {
        if (event.target === clearConfirmModal) {
            clearConfirmModal.style.display = "none";
        }
    });

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && clearConfirmModal && clearConfirmModal.style.display === "block") {
            clearConfirmModal.style.display = "none";
        }
    });
});
