document.addEventListener("DOMContentLoaded", function() {

  // Handle "View JSON" button clicks
  var viewJsonButtons = document.querySelectorAll('.view-json-btn');

  viewJsonButtons.forEach(function(button) {
    button.addEventListener('click', function() {
      var versionId = this.getAttribute('data-version-id');
      var url = window.location.href.split('/@@')[0] + '/@@view-version-json?version_id=' + versionId;

      // Fetch the JSON for this version
      fetch(url, {
        credentials: 'same-origin'
      })
        .then(function(response) {
          return response.json();
        })
        .then(function(data) {
          // Format and display JSON in modal
          var jsonContent = document.getElementById('jsonContent');
          jsonContent.textContent = JSON.stringify(data, null, 2);

          // Show modal (using Bootstrap's modal API)
          if (typeof jQuery !== 'undefined') {
            jQuery('#jsonViewerModal').modal('show');
          } else {
            // Fallback if jQuery not available
            var modal = document.getElementById('jsonViewerModal');
            modal.style.display = 'block';
            modal.classList.add('in');
            // Add backdrop
            var backdrop = document.createElement('div');
            backdrop.className = 'modal-backdrop fade in';
            backdrop.id = 'modal-backdrop';
            document.body.appendChild(backdrop);
          }
        })
        .catch(function(error) {
          console.error('Error fetching version JSON:', error);
          alert('Error loading version data. Please try again.');
        });
    });
  });

  // Fallback for environments where jQuery/Bootstrap JS is not available
  if (typeof jQuery === 'undefined') {

    // Centralized function to close the modal
    function closeModalFallback() {
      var modal = document.getElementById('jsonViewerModal');
      // Only act if the modal is open (has 'in' class)
      if (modal.classList.contains('in')) {
        modal.style.display = 'none';
        modal.classList.remove('in');
        var backdrop = document.getElementById('modal-backdrop');
        if (backdrop) {
          backdrop.parentNode.removeChild(backdrop);
        }
      }
    }

    // Handle modal close on button click or backdrop click using event delegation
    document.addEventListener('click', function(e) {
      
      var button = e.target.closest('[data-dismiss="modal"]');
      if (button && button.closest('#jsonViewerModal')) {
        e.preventDefault();
        closeModalFallback();
        return;
      }

      if (e.target.matches('#modal-backdrop')) {
        e.preventDefault();
        closeModalFallback();
      }
    });

    // Handle closing modal with ESC key
    document.addEventListener('keydown', function(e) {
      if (e.key === "Escape") {
        closeModalFallback();
      }
    });
  }
});
