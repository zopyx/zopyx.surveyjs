document.addEventListener("DOMContentLoaded", function () {
    const modal = document.getElementById("json-modal");
    const closeButton = document.querySelector(".close-button");
    const jsonContent = document.getElementById("json-content");
    const viewButtons = document.querySelectorAll(".view-json");

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
    });
});