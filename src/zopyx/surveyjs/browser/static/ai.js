/* ===== AI Page JavaScript ===== */

(function() {
  'use strict';

  // ===== Upload Form Handler =====
  function initUploadForm() {
    const form = document.getElementById('aiUploadForm');
    const button = document.getElementById('aiUploadBtn');
    const text = document.getElementById('aiUploadBtnText');
    const spinner = document.getElementById('aiUploadBtnSpinner');

    if (!form || !button || !text || !spinner) {
      return;
    }

    form.addEventListener('submit', function() {
      button.disabled = true;
      text.style.display = 'none';
      spinner.style.display = 'inline-flex';
    });
  }

  // ===== Chat Form Handler =====
  function initChatForm() {
    const form = document.getElementById('aiChatForm');
    const button = document.getElementById('aiChatSubmitBtn');
    const text = document.getElementById('aiChatSubmitText');
    const spinner = document.getElementById('aiChatSubmitSpinner');

    if (!form || !button || !text || !spinner) {
      return;
    }

    form.addEventListener('submit', function() {
      button.disabled = true;
      text.style.display = 'none';
      spinner.style.display = 'inline-flex';
    });
  }

  // ===== Preview Modal Handler =====
  function initPreviewModal() {
    const holder = document.getElementById('ai-temp-form-json');
    let target = document.getElementById('aiSurveyPreviewContainer');
    const modal = document.getElementById('aiPreviewModal');
    const openBtn = document.getElementById('aiOpenPreviewBtn');
    const closeBtn = document.getElementById('aiClosePreviewBtn');

    if (!holder || !target || !modal || !openBtn || !closeBtn || typeof Survey === 'undefined') {
      return;
    }

    let surveyInstance = null;

    function renderPreview() {
      try {
        if (surveyInstance && typeof surveyInstance.dispose === 'function') {
          surveyInstance.dispose();
        }
        surveyInstance = null;
        if (target && target.parentNode) {
          const freshTarget = target.cloneNode(false);
          target.parentNode.replaceChild(freshTarget, target);
          target = freshTarget;
        }
        const formJson = JSON.parse(holder.textContent || '{}');
        surveyInstance = new Survey.Model(formJson);
        surveyInstance.render(target);
        // Prevent form submission in preview mode
        surveyInstance.onComplete.add(function() {
          alert('Preview mode - form not submitted');
        });
      } catch (err) {
        target.innerHTML = "<div class='alert alert-danger'>SurveyJS preview failed.</div>";
      }
    }

    function openModal() {
      modal.style.display = 'flex';
      document.body.style.overflow = 'hidden';
      window.requestAnimationFrame(renderPreview);
    }

    function closeModal() {
      modal.style.display = 'none';
      document.body.style.overflow = '';
      if (surveyInstance && typeof surveyInstance.dispose === 'function') {
        surveyInstance.dispose();
      }
      surveyInstance = null;
      target.innerHTML = '';
    }

    openBtn.addEventListener('click', openModal);
    closeBtn.addEventListener('click', closeModal);

    modal.addEventListener('click', function(ev) {
      if (ev.target === modal) {
        closeModal();
      }
    });

    document.addEventListener('keydown', function(ev) {
      if (ev.key === 'Escape' && modal.style.display === 'flex') {
        closeModal();
      }
    });
  }

  // ===== Initialize on DOM Ready =====
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function() {
      initUploadForm();
      initChatForm();
      initPreviewModal();
    });
  } else {
    initUploadForm();
    initChatForm();
    initPreviewModal();
  }
})();
