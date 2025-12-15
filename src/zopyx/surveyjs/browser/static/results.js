document.addEventListener("DOMContentLoaded", function () {
    const modal = document.getElementById("json-modal");
    const closeButton = document.querySelector(".close-button");
    const jsonContent = document.getElementById("json-content");
    const viewButtons = document.querySelectorAll(".view-json");

    const detailsModal = document.getElementById("details-modal");
    const detailsCloseButton = document.querySelector(".details-close-button");
    const detailsContent = document.getElementById("details-content");
    const detailsButtons = document.querySelectorAll(".view-details");

    // View JSON button handlers
    viewButtons.forEach(button => {
        button.addEventListener("click", function () {
            const pollId = this.getAttribute("data-poll-id");
            fetch(`view-result-json?poll_id=${pollId}`)
                .then(response => response.json())
                .then(data => {
                    jsonContent.textContent = JSON.stringify(data, null, 2);
                    modal.style.display = "block";
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

    // View Details button handlers
    detailsButtons.forEach(button => {
        button.addEventListener("click", function () {
            const pollId = this.getAttribute("data-poll-id");
            fetch(`view-result-json?poll_id=${pollId}`)
                .then(response => response.json())
                .then(data => {
                    renderDetailsTable(data);
                    detailsModal.style.display = "block";
                });
        });
    });

    detailsCloseButton.addEventListener("click", function () {
        detailsModal.style.display = "none";
    });

    function renderDetailsTable(data) {
        let html = "<table class='details-table'>";
        html += "<thead><tr><th>Question</th><th>Answer</th></tr></thead>";
        html += "<tbody>";

        for (const [key, value] of Object.entries(data)) {
            html += `<tr><td class="question-cell"><strong>${escapeHtml(key)}</strong></td><td class="answer-cell">`;

            if (Array.isArray(value) && value.length > 0) {
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
});