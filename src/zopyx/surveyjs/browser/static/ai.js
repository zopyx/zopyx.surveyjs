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
    const target = document.getElementById('aiSurveyPreviewContainer');
    const modal = document.getElementById('aiPreviewModal');
    const openBtn = document.getElementById('aiOpenPreviewBtn');
    const closeBtn = document.getElementById('aiClosePreviewBtn');

    if (!holder || !target || !modal || !openBtn || !closeBtn || typeof Survey === 'undefined') {
      return;
    }

    let surveyInstance = null;
    let previewRendered = false;

    function renderPreview() {
      try {
        if (previewRendered) {
          return;
        }
        const formJson = JSON.parse(holder.textContent || '{}');
        target.innerHTML = '';
        surveyInstance = new Survey.Model(formJson);
        surveyInstance.mode = 'display';
        surveyInstance.render(target);
        previewRendered = true;
      } catch (err) {
        target.innerHTML = "<div class='alert alert-danger'>SurveyJS preview failed.</div>";
      }
    }

    function openModal() {
      modal.style.display = 'flex';
      document.body.style.overflow = 'hidden';
      renderPreview();
    }

    function closeModal() {
      modal.style.display = 'none';
      document.body.style.overflow = '';
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
