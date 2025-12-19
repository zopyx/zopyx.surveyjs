document.addEventListener("DOMContentLoaded", function() {

  // DOM Elements for JSON viewer
  var jsonViewerModal = document.getElementById('jsonViewerModal');
  var jsonContent = document.getElementById('jsonContent');

  // DOM Elements for Previewer
  const modal = document.getElementById("previewModal");
  const closeButton = modal.querySelector(".close-button");
  const surveyContainer = document.getElementById("surveyContainer");

  // Handle "View JSON" form submissions
  document.querySelectorAll('.view-json-btn').forEach(function(button) {
    var form = button.closest('form');
    form.addEventListener('submit', function(e) {
      e.preventDefault();
      var versionId = button.getAttribute('data-version-id');
      var url = window.location.href.split('/@@')[0] + '/@@view-version-json?version_id=' + versionId;

      fetch(url, {
        credentials: 'same-origin'
      })
        .then(response => response.json())
        .then(data => {
          jsonContent.textContent = JSON.stringify(data, null, 2);
          if (typeof jQuery !== 'undefined') {
            jQuery(jsonViewerModal).modal('show');
          } else {
            jsonViewerModal.style.display = 'block';
            jsonViewerModal.classList.add('in');
            var backdrop = document.createElement('div');
            backdrop.className = 'modal-backdrop fade in';
            backdrop.id = 'modal-backdrop-json';
            document.body.appendChild(backdrop);
          }
        })
        .catch(error => {
          console.error('Error fetching version JSON:', error);
          alert('Error loading version data. Please try again.');
        });
    });
  });

  // Handle "Preview" form submissions
  document.querySelectorAll('.preview-btn').forEach(function(button) {
    var form = button.closest('form');
    form.addEventListener('submit', function(e) {
      e.preventDefault();
      var versionId = button.getAttribute('data-version-id');
      var url = window.location.href.split('/@@')[0] + '/@@view-version-json?version_id=' + versionId;

      fetch(url, {
        credentials: 'same-origin'
      })
      .then(response => response.json())
      .then(json => {
        surveyContainer.innerHTML = "";
        try {
          const survey = new Survey.Model(json);
          survey.applyTheme(SurveyTheme.LayeredDarkPanelless);
          survey.showCompleteButton = false;
          survey.showPreviewBeforeComplete = "showAnsweredQuestions";
          survey.render(surveyContainer);
          modal.style.display = "block";
        } catch (error) {
          console.error("Error rendering preview:", error);
          alert("Failed to render preview: " + error.message);
        }
      })
      .catch(error => {
        console.error('Error fetching version JSON for preview:', error);
        alert('Error loading version data for preview. Please try again.');
      });
    });
  });

  // Close modal handlers
  closeButton.addEventListener("click", function() {
    modal.style.display = "none";
  });

  window.addEventListener("click", function(event) {
    if (event.target === modal) {
      modal.style.display = "none";
    }
  });

  // Close preview modal with ESC key
  document.addEventListener("keydown", function(event) {
    if (event.key === "Escape" && modal.style.display === "block") {
      modal.style.display = "none";
    }
  });

  // Fallback for environments where jQuery/Bootstrap JS is not available for JSON viewer
  if (typeof jQuery === 'undefined') {
    function closeJsonModalFallback() {
      if (jsonViewerModal.classList.contains('in')) {
        jsonViewerModal.style.display = 'none';
        jsonViewerModal.classList.remove('in');
        var backdrop = document.getElementById('modal-backdrop-json');
        if (backdrop) {
          backdrop.parentNode.removeChild(backdrop);
        }
      }
    }

    document.addEventListener('click', function(e) {
      var button = e.target.closest('[data-dismiss="modal"]');
      if (button && button.closest('#jsonViewerModal')) {
        e.preventDefault();
        closeJsonModalFallback();
        return;
      }
      if (e.target.matches('#modal-backdrop-json')) {
        e.preventDefault();
        closeJsonModalFallback();
      }
    });

    document.addEventListener('keydown', function(e) {
      if (e.key === "Escape") {
        closeJsonModalFallback();
        // Also close preview modal if open
        if (modal.style.display === "block") {
            modal.style.display = "none";
        }
      }
    });
  }
});

// Handle file input label
var fileInput = document.getElementById('json_file');
if (fileInput) {
  fileInput.addEventListener('change', function() {
    var fileName = this.files[0] ? this.files[0].name : 'No file selected';
    var label = this.nextElementSibling;
    if (label && label.tagName === 'LABEL') {
      label.textContent = fileName;
    }
  });
}

