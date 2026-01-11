document.addEventListener("DOMContentLoaded", function () {
    const modal = document.getElementById("json-modal");
    const closeButton = document.querySelector(".close-button");
    const jsonContent = document.getElementById("json-content");
    const viewButtons = document.querySelectorAll(".view-json");

    const detailsModal = document.getElementById("details-modal");
    const detailsCloseButton = document.querySelector(".details-close-button");
    const detailsContent = document.getElementById("details-content");
    const detailsButtons = document.querySelectorAll(".view-details");
    const questionLabels = {};
    const questionDefinitions = {};
    const deleteButtons = document.querySelectorAll(".delete-result");
    const deleteSelectedBtn = document.getElementById("delete-selected-btn");
    const selectAllCheckbox = document.getElementById("select-all-results");
    const selectionCheckboxes = document.querySelectorAll(".result-select");

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

    // View JSON button handlers
    viewButtons.forEach(button => {
        button.addEventListener("click", function () {
            const pollId = this.getAttribute("data-poll-id");
            fetch(`view-result-json?poll_id=${pollId}`, {
                credentials: 'same-origin'
            })
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
                    console.error('Error fetching JSON:', error);
                    alert('Failed to load JSON data. Please check the console for more information.');
                });
        });
    });

    closeButton.addEventListener("click", function () {
        modal.style.display = "none";
    });

    window.addEventListener("click", function (event) {
        if (event.target === modal) {
            modal.style.display = "none";
        }
        if (event.target === detailsModal) {
            detailsModal.style.display = "none";
        }
    });

    // Close modals with ESC key
    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape") {
            if (modal.style.display === "block") {
                modal.style.display = "none";
            }
            if (detailsModal.style.display === "block") {
                detailsModal.style.display = "none";
            }
        }
    });

    // View Details button handlers
    detailsButtons.forEach(button => {
        button.addEventListener("click", function () {
            const pollId = this.getAttribute("data-poll-id");
            fetch(`view-result-json?poll_id=${pollId}`, {
                credentials: 'same-origin'
            })
                .then(response => {
                    if (!response.ok) {
                        throw new Error(`HTTP error! status: ${response.status}`);
                    }
                    return response.json();
                })
                .then(data => {
                    if (data.error) {
                        alert(`Error: ${data.error}`);
                        return;
                    }
                    renderDetailsTable(data);
                    detailsModal.style.display = "block";
                })
                .catch(error => {
                    console.error('Error fetching details:', error);
                    alert('Failed to load details. Please check the console for more information.');
                });
        });
    });

    detailsCloseButton.addEventListener("click", function () {
        detailsModal.style.display = "none";
    });

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
            html += "<thead><tr><th>Row</th><th>Answer</th></tr></thead><tbody>";

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
        html += "<thead><tr><th>Key / Question</th><th>Answer</th></tr></thead>";
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
                // Check if it's a file upload result
                const item = value[0];
                if (typeof item === 'object' && item !== null && 'name' in item && 'content' in item) {
                    if (item.type && item.type.includes('image')) {
                        // Display image preview
                        html += `<div class="image-preview"><img src="${item.content}" alt="${escapeHtml(item.name)}" /></div>`;
                    } else {
                        html += `Attached file: ${escapeHtml(item.name)}`;
                    }
                } else {
                    // Regular array
                    html += value.map(v => escapeHtml(String(v))).join('<br>');
                }
            } else if (typeof value === 'string' && value.startsWith('data:image/')) {
                // Direct data URI image
                html += `<div class="image-preview"><img src="${value}" alt="${escapeHtml(key)}" /></div>`;
            } else if (typeof value === 'object' && value !== null) {
                // Nested object
                html += Object.entries(value)
                    .map(([k, v]) => `${escapeHtml(k)}: ${escapeHtml(String(v))}`)
                    .join('<br>');
            } else {
                // Simple value
                html += escapeHtml(String(value));
            }

            html += "</td></tr>";
        }

        html += "</tbody></table>";
        detailsContent.innerHTML = html;
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function getSelectedPollIds() {
        return Array.from(selectionCheckboxes || [])
            .filter(cb => cb.checked)
            .map(cb => cb.value);
    }

    function getAuthenticatorToken() {
        const tokenInput = document.querySelector('input[name="_authenticator"]');
        return tokenInput ? tokenInput.value : null;
    }

    function updateSelectionState() {
        const checkboxes = Array.from(selectionCheckboxes || []);
        if (!selectAllCheckbox || !deleteSelectedBtn) {
            return;
        }

        const total = checkboxes.length;
        const checkedCount = checkboxes.filter(cb => cb.checked).length;

        selectAllCheckbox.checked = total > 0 && checkedCount === total;
        selectAllCheckbox.indeterminate = checkedCount > 0 && checkedCount < total;
        deleteSelectedBtn.disabled = checkedCount === 0;
    }

    function deletePolls(pollIds) {
        const headers = {
            "Content-Type": "application/json"
        };
        const token = getAuthenticatorToken();
        if (token) {
            headers["X-CSRF-TOKEN"] = token;
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

    deleteButtons.forEach(button => {
        button.addEventListener("click", function () {
            const pollId = this.getAttribute("data-poll-id");
            if (!pollId) {
                return;
            }
            if (!confirm("Delete this result?")) {
                return;
            }
            deletePolls([pollId])
                .then(() => window.location.reload())
                .catch(error => {
                    console.error("Error deleting result:", error);
                    alert("Failed to delete the result. Please check the console for details.");
                });
        });
    });

    selectionCheckboxes.forEach(checkbox => {
        checkbox.addEventListener("change", updateSelectionState);
    });

    if (selectAllCheckbox) {
        selectAllCheckbox.addEventListener("change", function () {
            selectionCheckboxes.forEach(cb => {
                cb.checked = selectAllCheckbox.checked;
            });
            updateSelectionState();
        });
    }

    if (deleteSelectedBtn) {
        deleteSelectedBtn.addEventListener("click", function () {
            const selected = getSelectedPollIds();
            if (!selected.length) {
                return;
            }
            if (!confirm(`Delete ${selected.length} selected result(s)?`)) {
                return;
            }
            deletePolls(selected)
                .then(() => window.location.reload())
                .catch(error => {
                    console.error("Error deleting selected results:", error);
                    alert("Failed to delete selected results. Please check the console for details.");
                });
        });
    }

    updateSelectionState();

    // Clear Results functionality
    const clearResultsBtn = document.getElementById("clear-results-btn");
    const clearConfirmModal = document.getElementById("clear-confirm-modal");
    const clearCloseButton = document.querySelector(".clear-close-button");
    const clearConfirmInput = document.getElementById("clear-confirm-input");
    const clearConfirmBtn = document.getElementById("clear-confirm-btn");
    const clearCancelBtn = document.getElementById("clear-cancel-btn");

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
            if (this.value.toLowerCase() === "clear") {
                clearConfirmBtn.disabled = false;
            } else {
                clearConfirmBtn.disabled = true;
            }
        });

        clearConfirmInput.addEventListener("keypress", function (e) {
            if (e.key === "Enter" && this.value.toLowerCase() === "clear") {
                clearConfirmBtn.click();
            }
        });
    }

    if (clearConfirmBtn) {
        clearConfirmBtn.addEventListener("click", function () {
            const headers = {};
            const token = getAuthenticatorToken();
            if (token) {
                headers["X-CSRF-TOKEN"] = token;
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
                    alert("All results have been cleared successfully.");
                    window.location.reload();
                })
                .catch(error => {
                    console.error("Error clearing results:", error);
                    alert("Failed to clear results. Please check the console for more information.");
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

    // Close clear modal when clicking outside
    window.addEventListener("click", function (event) {
        if (event.target === clearConfirmModal) {
            clearConfirmModal.style.display = "none";
        }
    });

    // Close clear modal with ESC key
    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && clearConfirmModal && clearConfirmModal.style.display === "block") {
            clearConfirmModal.style.display = "none";
        }
    });
});
