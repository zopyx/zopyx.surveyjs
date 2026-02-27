/**
 * Results view logic for @@results.
 * Uses vanilla JavaScript table with server-side pagination, sorting, and filtering.
 */

/**
 * Initialize results view once the DOM is ready.
 * @param {Event} event
 */
function handleResultsReady(event) {
    const defaultTranslate = function (msgid, mapping) {
        if (!mapping) {
            return msgid;
        }
        const replaceToken = function (match, key) {
            if (Object.prototype.hasOwnProperty.call(mapping, key)) {
                return String(mapping[key]);
            }
            return match;
        };
        return msgid.replace(/\$\{([a-zA-Z0-9_]+)\}/g, replaceToken);
    };
    const t = window._t || defaultTranslate;

    const configEl = document.getElementById("results-config");
    let config = window.RESULTS_CONFIG || {};
    if (configEl && configEl.textContent) {
        try {
            config = JSON.parse(configEl.textContent) || config;
        } catch (error) {
            console.error("Failed to parse results config", error);
        }
    }
    const formats = Array.isArray(config.converterFormats) ? config.converterFormats : [];
    const isManager = Boolean(config.isManager);
    const hasMailAction = Boolean(config.hasMailAction);
    const hasPostAction = Boolean(config.hasPostAction);
    const authToken = config.authenticator || "";
    const gridMount = document.getElementById("results-grid");
    const pagerMount = document.getElementById("results-pager");
    const pagerRowMount = document.getElementById("results-pager-row");
    const emptyStateMount = document.getElementById("results-empty-state");
    const toolbarMount = document.getElementById("results-toolbar");
    const exportRowMount = document.getElementById("results-export-row");

    const modal = document.getElementById("json-modal");
    const closeButton = document.querySelector(".close-button");
    const jsonContent = document.getElementById("json-content");

    const detailsModal = document.getElementById("details-modal");
    const detailsCloseButton = document.querySelector(".details-close-button");
    const detailsContent = document.getElementById("details-content");

    const deleteConfirmModal = document.getElementById("delete-confirm-modal");
    const deleteCloseButton = document.querySelector(".delete-close-button");
    const deleteConfirmBtn = document.getElementById("delete-confirm-btn");
    const deleteCancelBtn = document.getElementById("delete-cancel-btn");

    const deleteSelectedConfirmModal = document.getElementById("delete-selected-confirm-modal");
    const deleteSelectedCloseButton = document.querySelector(".delete-selected-close-button");
    const deleteSelectedConfirmBtn = document.getElementById("delete-selected-confirm-btn");
    const deleteSelectedCancelBtn = document.getElementById("delete-selected-cancel-btn");
    const deleteSelectedMessage = document.getElementById("delete-selected-message");

    const totalCountEl = document.getElementById("results-total-count");
    const deleteSelectedBtn = document.getElementById("results-delete-selected-btn");
    const exportFrom = document.getElementById("results-export-from");
    const exportTo = document.getElementById("results-export-to");
    const exportLinks = document.querySelectorAll("[data-base-href]");
    const exportWarning = document.getElementById("results-export-warning");
    const fullscreenToggle = document.getElementById("surveyResultsFullscreenToggle");
    const fullscreenClass = "survey-results-fullscreen";
    const fullscreenParam = new URLSearchParams(window.location.search).get("fullscreen");

    const questionLabels = {};
    const questionDefinitions = {};

    const handleFormResponse = function (response) {
        return response.json();
    };
    const handleFormData = function (data) {
        (data.pages || []).forEach(function attachPage(page) {
            (page.elements || []).forEach(function attachElement(element) {
                if (element.name) {
                    questionLabels[element.name] = element.title || element.name;
                    questionDefinitions[element.name] = element;
                }
            });
        });
    };
    const handleFormDataError = function (error) {
        // Best-effort label mapping; fall back to keys on failure.
    };

    fetch("get-form-json", { credentials: "same-origin" })
        .then(handleFormResponse)
        .then(handleFormData)
        .catch(handleFormDataError);

    function updateTotalCount(count) {
        if (totalCountEl) {
            totalCountEl.textContent = String(count || 0);
        }
    }

    function setFullscreen(enabled) {
        document.body.classList.toggle(fullscreenClass, Boolean(enabled));
        if (!fullscreenToggle) {
            return;
        }
        fullscreenToggle.textContent = enabled ? t("Exit fullscreen") : t("Fullscreen");
        fullscreenToggle.setAttribute("aria-pressed", enabled ? "true" : "false");
    }

    function hasInvalidExportRange() {
        if (!exportFrom || !exportTo) {
            return false;
        }
        if (!exportFrom.value || !exportTo.value) {
            return false;
        }
        return exportTo.value <= exportFrom.value;
    }

    function updateExportWarning() {
        if (!exportWarning) {
            return;
        }
        if (hasInvalidExportRange()) {
            exportWarning.style.display = "inline-flex";
        } else {
            exportWarning.style.display = "none";
        }
    }

    function updateExportLinks() {
        if (!exportLinks.length) {
            return;
        }
        const fromValue = exportFrom ? exportFrom.value : "";
        const toValue = exportTo ? exportTo.value : "";
        exportLinks.forEach(link => {
            const baseHref = link.getAttribute("data-base-href");
            if (!baseHref) {
                return;
            }
            const url = new URL(baseHref, window.location.href);
            if (fromValue) {
                url.searchParams.set("from", fromValue);
            }
            if (toValue) {
                url.searchParams.set("to", toValue);
            }
            link.setAttribute("href", `${url.pathname}${url.search}`);
        });
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

    function showGridError(message) {
        if (!gridMount) {
            return;
        }
        const notice = document.createElement("div");
        notice.className = "results-empty";
        notice.textContent = message;
        gridMount.innerHTML = "";
        gridMount.appendChild(notice);
    }

    if (exportFrom) {
        exportFrom.addEventListener("change", function () {
            updateExportWarning();
            updateExportLinks();
        });
    }
    if (exportTo) {
        exportTo.addEventListener("change", function () {
            updateExportWarning();
            updateExportLinks();
        });
    }
    updateExportWarning();
    updateExportLinks();

    if (fullscreenToggle) {
        fullscreenToggle.addEventListener("click", function (event) {
            event.preventDefault();
            const isFullscreen = document.body.classList.contains(fullscreenClass);
            setFullscreen(!isFullscreen);
        });
        document.addEventListener("keydown", function (event) {
            if (event.key === "Escape" && document.body.classList.contains(fullscreenClass)) {
                setFullscreen(false);
            }
        });
    }

    if (fullscreenParam === "1" || fullscreenParam === "true" || fullscreenParam === "yes") {
        setFullscreen(true);
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

    let pendingDeletePollId = null;
    let pendingDeleteSelectedIds = [];

    function openDeleteModal(pollId) {
        if (!deleteConfirmModal) {
            return;
        }
        pendingDeletePollId = pollId;
        deleteConfirmModal.style.display = "block";
        if (deleteConfirmBtn) {
            deleteConfirmBtn.disabled = false;
        }
    }

    function openDeleteSelectedModal(selectedIds) {
        if (!deleteSelectedConfirmModal) {
            return;
        }
        pendingDeleteSelectedIds = selectedIds.slice();
        if (deleteSelectedMessage) {
            deleteSelectedMessage.textContent = t("Delete ${count} selected result(s)?", {
                count: pendingDeleteSelectedIds.length
            });
        }
        deleteSelectedConfirmModal.style.display = "block";
        if (deleteSelectedConfirmBtn) {
            deleteSelectedConfirmBtn.disabled = pendingDeleteSelectedIds.length === 0;
        }
    }

    function createSvgIcon(pathMarkup) {
        const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        svg.setAttribute("viewBox", "0 0 24 24");
        svg.setAttribute("aria-hidden", "true");
        svg.setAttribute("focusable", "false");
        svg.classList.add("results-icon");
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
            img.className = "results-icon";
            el.appendChild(img);
        }

        const sr = document.createElement("span");
        sr.className = "sr-only";
        sr.textContent = label;
        el.appendChild(sr);
        return el;
    }

    // Table State
    let tableState = {
        data: [],
        page: 1,
        size: 25,
        lastPage: 1,
        totalRows: 0,
        sortColumn: "created_ts",
        sortDirection: "desc",
        filterValues: {},
        selectedIds: new Set(),
        loading: false
    };

    let currentQuery = "";

    // Column width storage
    const columnWidthsKey = 'surveyjs_results_column_widths';
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

    // Column Definitions
    const columns = [
        {
            key: "select",
            title: "",
            sortable: false,
            filterable: false,
            width: "40px",
            align: "center",
            visible: isManager,
            renderHeader: () => {
                if (!isManager) return "";
                const allSelected = tableState.data.length > 0 && tableState.data.every(row => tableState.selectedIds.has(row.poll_id));
                return `<input type="checkbox" class="select-all-checkbox" ${allSelected ? "checked" : ""} title="${escapeHtml(t("Select all"))}">`;
            },
            render: (row) => {
                if (!isManager) return "";
                const checked = tableState.selectedIds.has(row.poll_id) ? "checked" : "";
                return `<input type="checkbox" class="row-checkbox" data-poll-id="${escapeHtml(row.poll_id)}" ${checked}>`;
            }
        },
        {
            key: "created_ts",
            title: t("Date"),
            sortable: true,
            filterable: true,
            width: "170px",
            render: (row) => row.created_display || ""
        },
        {
            key: "user",
            title: t("User"),
            sortable: true,
            filterable: true,
            width: "160px"
        },
        {
            key: "seq_no",
            title: t("#"),
            sortable: true,
            filterable: true,
            width: "70px",
            align: "center"
        },
        {
            key: "poll_id",
            title: t("Poll ID"),
            sortable: true,
            filterable: true,
            render: (row) => {
                const full = escapeHtml(String(row.poll_id || ""));
                const short = shortenId(row.poll_id);
                return `<span title="${full}">${short}</span>`;
            }
        },
        {
            key: "actions",
            title: t("Action"),
            sortable: false,
            filterable: false,
            width: "322px",
            render: (row) => ""  // Rendered via renderActionCell
        }
    ].filter(col => col.visible !== false);

    function renderActionCell(row) {
        const wrapper = document.createElement("div");
        wrapper.className = "results-action-group";
        const leftGroup = document.createElement("div");
        leftGroup.className = "results-action-left";
        const middleGroup = document.createElement("div");
        middleGroup.className = "results-action-middle";
        const rightGroup = document.createElement("div");
        rightGroup.className = "results-action-right";

        const jsonBtn = createIconButton({
            label: t("JSON"),
            className: "btn-primary view-json",
            type: "button",
            svg: "<path d=\"M6 3h8l4 4v14H6z\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.6\"/><path d=\"M14 3v5h5\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.6\"/><path d=\"M8 13h2m-2 4h2m2-4h4m-4 4h4\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.6\" stroke-linecap=\"round\"/>",
            onClick: function () {
                openJsonModal(row.poll_id);
            }
        });
        leftGroup.appendChild(jsonBtn);

        const tableBtn = createIconButton({
            label: t("Table"),
            className: "btn-success view-details",
            type: "button",
            svg: "<path d=\"M3 5h18v14H3z\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.6\"/><path d=\"M3 9h18M8 5v14M16 5v14\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.6\"/>",
            onClick: function () {
                openDetailsModal(row.poll_id);
            }
        });
        leftGroup.appendChild(tableBtn);

        const detailLink = createIconButton({
            tag: "a",
            label: t("Details"),
            className: "btn-secondary detail-link",
            href: `${config.detailUrlBase}${encodeURIComponent(row.poll_id)}`,
            svg: "<path d=\"M12 5c5 0 9 5 9 7s-4 7-9 7-9-5-9-7 4-7 9-7z\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.6\"/><circle cx=\"12\" cy=\"12\" r=\"2.5\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.6\"/>"
        });
        leftGroup.appendChild(detailLink);

        const form = document.createElement("form");
        form.method = "get";
        form.action = config.downloadUrl;
        form.className = "download-form results-action-form";

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
        pollInput.value = row.poll_id;
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
                    openDeleteModal(row.poll_id);
                }
            });
            rightGroup.appendChild(deleteBtn);
        }

        wrapper.appendChild(leftGroup);
        wrapper.appendChild(middleGroup);
        wrapper.appendChild(rightGroup);
        return wrapper;
    }

    function buildRequestParams() {
        const params = new URLSearchParams();
        params.set("page", tableState.page);
        params.set("size", tableState.size);
        if (currentQuery) {
            params.set("q", currentQuery);
        }

        // Add sorters
        if (tableState.sortColumn) {
            const sorter = {
                field: tableState.sortColumn,
                dir: tableState.sortDirection
            };
            params.set("sorters", JSON.stringify([sorter]));
        }

        // Add filters
        const filters = [];
        Object.entries(tableState.filterValues).forEach(([field, value]) => {
            if (value) {
                filters.push({ field, value, type: "like" });
            }
        });
        if (filters.length) {
            params.set("filters", JSON.stringify(filters));
        }

        return params;
    }

    async function loadData() {
        if (tableState.loading) return;
        tableState.loading = true;

        try {
            const params = buildRequestParams();
            const response = await fetch(`${config.resultsUrl}?${params.toString()}`, {
                credentials: "same-origin"
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            tableState.data = data.data || [];
            tableState.page = data.page || 1;
            tableState.lastPage = data.last_page || 1;
            tableState.totalRows = data.total_rows || 0;

            updateTotalCount(tableState.totalRows);
            render();
        } catch (error) {
            console.error(t("Error loading results:"), error);
            showGridError(t("Failed to load results. Please check the console for details."));
        } finally {
            tableState.loading = false;
        }
    }

    function toggleEmptyState(showEmpty) {
        if (emptyStateMount) {
            emptyStateMount.style.display = showEmpty ? 'block' : 'none';
        }
        if (gridMount) {
            gridMount.style.display = showEmpty ? 'none' : 'block';
        }
        if (pagerRowMount) {
            pagerRowMount.style.display = showEmpty ? 'none' : 'flex';
        }
        if (toolbarMount) {
            toolbarMount.style.display = showEmpty ? 'none' : 'flex';
        }
        if (exportRowMount) {
            exportRowMount.style.display = showEmpty ? 'none' : 'flex';
        }
    }

    function render() {
        if (!gridMount) return;

        // Show empty state if no results
        if (tableState.totalRows === 0) {
            toggleEmptyState(true);
            updateDeleteSelectedButton();
            return;
        }

        toggleEmptyState(false);

        let html = '<table class="results-table">';

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
            } else if (col.renderHeader) {
                html += col.renderHeader();
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
        tableState.data.forEach(row => {
            const selectedClass = tableState.selectedIds.has(row.poll_id) ? " selected" : "";
            html += `<tr class="${selectedClass}">`;
            columns.forEach(col => {
                const alignAttr = col.align ? ` style="text-align: ${col.align};"` : '';
                if (col.key === "actions") {
                    html += `<td${alignAttr} class="actions-cell"></td>`;
                } else if (col.render) {
                    html += `<td${alignAttr}>${col.render(row)}</td>`;
                } else {
                    html += `<td${alignAttr}>${escapeHtml(row[col.key] || '')}</td>`;
                }
            });
            html += '</tr>';
        });
        html += '</tbody></table>';

        gridMount.innerHTML = html;

        // Render action cells after table is in DOM
        const actionCells = gridMount.querySelectorAll(".actions-cell");
        actionCells.forEach((cell, index) => {
            if (tableState.data[index]) {
                cell.appendChild(renderActionCell(tableState.data[index]));
            }
        });

        attachTableEvents();
        renderPagination();
        updateDeleteSelectedButton();
    }

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
                loadData();
            });
        });

        // Filter inputs
        let filterTimeout;
        gridMount.querySelectorAll('.filter-input').forEach(input => {
            input.addEventListener('input', (e) => {
                const column = e.currentTarget.dataset.column;
                tableState.filterValues[column] = e.currentTarget.value;
                clearTimeout(filterTimeout);
                filterTimeout = setTimeout(() => {
                    loadData();
                }, 300);
            });
        });

        // Row checkboxes
        gridMount.querySelectorAll('.row-checkbox').forEach(checkbox => {
            checkbox.addEventListener('change', (e) => {
                const pollId = e.currentTarget.dataset.pollId;
                if (e.currentTarget.checked) {
                    tableState.selectedIds.add(pollId);
                } else {
                    tableState.selectedIds.delete(pollId);
                }
                render();
            });
        });

        // Select all checkbox
        const selectAll = gridMount.querySelector('.select-all-checkbox');
        if (selectAll) {
            selectAll.addEventListener('change', (e) => {
                if (e.currentTarget.checked) {
                    tableState.data.forEach(row => tableState.selectedIds.add(row.poll_id));
                } else {
                    tableState.data.forEach(row => tableState.selectedIds.delete(row.poll_id));
                }
                render();
            });

        // Column resize handles
        gridMount.querySelectorAll(".resize-handle").forEach(handle => {
            handle.addEventListener("mousedown", (e) => {
                e.preventDefault();
                e.stopPropagation();
                const columnKey = e.currentTarget.dataset.column;
                const th = e.currentTarget.closest("th");
                const rect = th.getBoundingClientRect();
                resizeState = {
                    resizing: true,
                    columnKey: columnKey,
                    startX: e.clientX,
                    startWidth: rect.width,
                    thElement: th
                };
                document.body.style.cursor = "col-resize";
                th.classList.add("resizing");
            });
        });
        }
    }

    function renderPagination() {
        if (!pagerMount) return;

        const startItem = tableState.totalRows === 0 ? 0 : (tableState.page - 1) * tableState.size + 1;
        const endItem = Math.min(tableState.page * tableState.size, tableState.totalRows);

        let html = '<div class="pagination-container">';

        // Page size selector
        html += '<div class="page-size">';
        html += `<span>${escapeHtml(t('Page Size'))}:</span>`;
        html += '<select class="page-size-select">';
        [10, 25, 50, 100, 250].forEach(size => {
            const selected = size === tableState.size ? ' selected' : '';
            html += `<option value="${size}"${selected}>${size}</option>`;
        });
        html += '</select></div>';

        // Page info
        html += `<div class="page-info">${startItem}-${endItem} ${escapeHtml(t('of'))} ${tableState.totalRows}</div>`;

        // Page buttons
        html += '<div class="page-buttons">';

        // First
        const firstDisabled = tableState.page === 1 ? ' disabled' : '';
        html += `<button type="button" class="page-btn" data-page="1"${firstDisabled}>${escapeHtml(t('First'))}</button>`;

        // Prev
        const prevDisabled = tableState.page === 1 ? ' disabled' : '';
        html += `<button type="button" class="page-btn" data-page="${tableState.page - 1}"${prevDisabled}>${escapeHtml(t('Prev'))}</button>`;

        // Page numbers
        const maxButtons = 5;
        let startPage = Math.max(1, tableState.page - Math.floor(maxButtons / 2));
        let endPage = Math.min(tableState.lastPage, startPage + maxButtons - 1);
        if (endPage - startPage < maxButtons - 1) {
            startPage = Math.max(1, endPage - maxButtons + 1);
        }

        for (let i = startPage; i <= endPage; i++) {
            const active = i === tableState.page ? ' active' : '';
            html += `<button type="button" class="page-btn${active}" data-page="${i}">${i}</button>`;
        }

        // Next
        const nextDisabled = tableState.page === tableState.lastPage ? ' disabled' : '';
        html += `<button type="button" class="page-btn" data-page="${tableState.page + 1}"${nextDisabled}>${escapeHtml(t('Next'))}</button>`;

        // Last
        const lastDisabled = tableState.page === tableState.lastPage ? ' disabled' : '';
        html += `<button type="button" class="page-btn" data-page="${tableState.lastPage}"${lastDisabled}>${escapeHtml(t('Last'))}</button>`;

        html += '</div></div>';

        pagerMount.innerHTML = html;

        // Attach pagination event listeners
        pagerMount.querySelectorAll('.page-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                if (e.currentTarget.disabled) return;
                const page = parseInt(e.currentTarget.dataset.page, 10);
                if (page >= 1 && page <= tableState.lastPage) {
                    tableState.page = page;
                    loadData();
                }
            });
        });

        pagerMount.querySelector('.page-size-select')?.addEventListener('change', (e) => {
            tableState.size = parseInt(e.currentTarget.value, 10);
            tableState.page = 1;
            loadData();
        });
    }

    function updateDeleteSelectedButton() {
        if (deleteSelectedBtn) {
            deleteSelectedBtn.disabled = tableState.selectedIds.size === 0;
        }
    }

    // Search functionality
    const searchInput = document.getElementById("results-search-input");
    const searchBtn = document.getElementById("results-search-btn");
    const resetBtn = document.getElementById("results-reset-btn");
    const refreshBtn = document.getElementById("results-refresh-btn");

    function applySearch() {
        currentQuery = searchInput ? searchInput.value.trim() : "";
        tableState.page = 1;
        loadData();
    }

    if (searchBtn) {
        searchBtn.addEventListener('click', applySearch);
    }

    if (searchInput) {
        searchInput.addEventListener('keypress', function (event) {
            if (event.key === "Enter") {
                applySearch();
            }
        });
    }

    if (resetBtn) {
        resetBtn.addEventListener('click', function () {
            if (searchInput) {
                searchInput.value = "";
            }
            tableState.filterValues = {};
            tableState.selectedIds.clear();
            currentQuery = "";
            tableState.page = 1;
            loadData();
        });
    }

    if (refreshBtn) {
        refreshBtn.addEventListener('click', function () {
            loadData();
        });
    }

    // Modal close handlers
    if (closeButton) {
        closeButton.addEventListener('click', function () {
            modal.style.display = "none";
        });
    }

    if (detailsCloseButton) {
        detailsCloseButton.addEventListener('click', function () {
            detailsModal.style.display = "none";
        });
    }

    if (deleteCloseButton) {
        deleteCloseButton.addEventListener('click', function () {
            if (deleteConfirmModal) {
                deleteConfirmModal.style.display = "none";
            }
            pendingDeletePollId = null;
        });
    }

    if (deleteCancelBtn) {
        deleteCancelBtn.addEventListener('click', function () {
            if (deleteConfirmModal) {
                deleteConfirmModal.style.display = "none";
            }
            pendingDeletePollId = null;
        });
    }

    if (deleteConfirmBtn) {
        deleteConfirmBtn.addEventListener('click', function () {
            if (!pendingDeletePollId) {
                return;
            }
            deleteConfirmBtn.disabled = true;
            deletePolls([pendingDeletePollId])
                .then(() => {
                    if (deleteConfirmModal) {
                        deleteConfirmModal.style.display = "none";
                    }
                    pendingDeletePollId = null;
                    tableState.selectedIds.delete(pendingDeletePollId);
                    loadData();
                })
                .catch(error => {
                    console.error(t("Error deleting result:"), error);
                    alert(t("Failed to delete the result. Please check the console for details."));
                })
                .finally(() => {
                    deleteConfirmBtn.disabled = false;
                });
        });
    }

    if (deleteSelectedCloseButton) {
        deleteSelectedCloseButton.addEventListener('click', function () {
            if (deleteSelectedConfirmModal) {
                deleteSelectedConfirmModal.style.display = "none";
            }
            pendingDeleteSelectedIds = [];
        });
    }

    if (deleteSelectedCancelBtn) {
        deleteSelectedCancelBtn.addEventListener('click', function () {
            if (deleteSelectedConfirmModal) {
                deleteSelectedConfirmModal.style.display = "none";
            }
            pendingDeleteSelectedIds = [];
        });
    }

    if (deleteSelectedConfirmBtn) {
        deleteSelectedConfirmBtn.addEventListener('click', function () {
            if (!pendingDeleteSelectedIds.length) {
                return;
            }
            deleteSelectedConfirmBtn.disabled = true;
            deletePolls(pendingDeleteSelectedIds)
                .then(() => {
                    if (deleteSelectedConfirmModal) {
                        deleteSelectedConfirmModal.style.display = "none";
                    }
                    pendingDeleteSelectedIds.forEach(id => tableState.selectedIds.delete(id));
                    pendingDeleteSelectedIds = [];
                    loadData();
                })
                .catch(error => {
                    console.error(t("Error deleting selected results:"), error);
                    alert(t("Failed to delete selected results. Please check the console for details."));
                })
                .finally(() => {
                    deleteSelectedConfirmBtn.disabled = false;
                });
        });
    }

    if (deleteSelectedBtn && isManager) {
        deleteSelectedBtn.addEventListener('click', function () {
            if (tableState.selectedIds.size === 0) {
                return;
            }
            openDeleteSelectedModal(Array.from(tableState.selectedIds));
        });
    }

    // Clear results handlers
    const clearResultsBtn = document.getElementById("results-clear-results-btn");
    const clearConfirmModal = document.getElementById("clear-confirm-modal");
    const clearCloseButton = document.querySelector(".clear-close-button");
    const clearConfirmInput = document.getElementById("clear-confirm-input");
    const clearConfirmBtn = document.getElementById("clear-confirm-btn");
    const clearCancelBtn = document.getElementById("clear-cancel-btn");
    const clearKeyword = clearConfirmInput
        ? (clearConfirmInput.dataset.clearKeyword || "clear")
        : "clear";

    if (clearResultsBtn) {
        clearResultsBtn.addEventListener('click', function () {
            clearConfirmModal.style.display = "block";
            clearConfirmInput.value = "";
            clearConfirmInput.focus();
            clearConfirmBtn.disabled = true;
        });
    }

    if (clearConfirmInput) {
        clearConfirmInput.addEventListener('input', function () {
            clearConfirmBtn.disabled = this.value.toLowerCase() !== clearKeyword.toLowerCase();
        });

        clearConfirmInput.addEventListener('keypress', function (event) {
            if (event.key === "Enter" && this.value.toLowerCase() === clearKeyword.toLowerCase()) {
                clearConfirmBtn.click();
            }
        });
    }

    if (clearConfirmBtn) {
        clearConfirmBtn.addEventListener('click', function () {
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
                    tableState.selectedIds.clear();
                    loadData();
                })
                .catch(error => {
                    console.error(t("Error clearing results:"), error);
                    alert(t("Failed to clear results. Please check the console for more information."));
                });
        });
    }

    if (clearCloseButton) {
        clearCloseButton.addEventListener('click', function () {
            clearConfirmModal.style.display = "none";
        });
    }

    if (clearCancelBtn) {
        clearCancelBtn.addEventListener('click', function () {
            clearConfirmModal.style.display = "none";
        });
    }

    // Window click handlers for modals
    window.addEventListener('click', function (event) {
        if (event.target === modal) {
            modal.style.display = "none";
        }
        if (event.target === detailsModal) {
            detailsModal.style.display = "none";
        }
        if (event.target === deleteConfirmModal) {
            deleteConfirmModal.style.display = "none";
            pendingDeletePollId = null;
        }
        if (event.target === deleteSelectedConfirmModal) {
            deleteSelectedConfirmModal.style.display = "none";
            pendingDeleteSelectedIds = [];
        }
        if (event.target === clearConfirmModal) {
            clearConfirmModal.style.display = "none";
        }
    });

    document.addEventListener('keydown', function (event) {
        if (event.key === "Escape") {
            if (modal && modal.style.display === "block") {
                modal.style.display = "none";
            }
            if (detailsModal && detailsModal.style.display === "block") {
                detailsModal.style.display = "none";
            }
            if (deleteConfirmModal && deleteConfirmModal.style.display === "block") {
                deleteConfirmModal.style.display = "none";
                pendingDeletePollId = null;
            }
            if (deleteSelectedConfirmModal && deleteSelectedConfirmModal.style.display === "block") {
                deleteSelectedConfirmModal.style.display = "none";
                pendingDeleteSelectedIds = [];
            }
            if (clearConfirmModal && clearConfirmModal.style.display === "block") {
                clearConfirmModal.style.display = "none";
            }
        }
    });


    // Column resize document-level handlers
    document.addEventListener("mousemove", (e) => {
        if (!resizeState.resizing) return;
        e.preventDefault();
        const delta = e.clientX - resizeState.startX;
        const newWidth = Math.max(50, resizeState.startWidth + delta);
        resizeState.thElement.style.width = newWidth + "px";
        resizeState.thElement.style.minWidth = newWidth + "px";
    });

    document.addEventListener("mouseup", () => {
        if (!resizeState.resizing) return;
        const finalWidth = resizeState.thElement.getBoundingClientRect().width;
        columnWidths[resizeState.columnKey] = finalWidth;
        saveColumnWidths();
        resizeState.thElement.classList.remove("resizing");
        resizeState = {
            resizing: false,
            columnKey: null,
            startX: 0,
            startWidth: 0,
            thElement: null
        };
        document.body.style.cursor = "";
    });

    // Initial load
    loadData();
}

document.addEventListener("DOMContentLoaded", handleResultsReady);
