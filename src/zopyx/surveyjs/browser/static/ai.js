/* ===== AI2 Page JavaScript ===== */

(function() {
  'use strict';

  // ===== Upload Form Handler =====
  function initUploadForm() {
    const form = document.getElementById('ai2UploadForm');
    const button = document.getElementById('ai2UploadBtn');
    const text = document.getElementById('ai2UploadBtnText');
    const spinner = document.getElementById('ai2UploadBtnSpinner');

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
    const form = document.getElementById('ai2ChatForm');
    const button = document.getElementById('ai2ChatSubmitBtn');
    const text = document.getElementById('ai2ChatSubmitText');
    const spinner = document.getElementById('ai2ChatSubmitSpinner');

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
    const holder = document.getElementById('ai2-temp-form-json');
    const target = document.getElementById('ai2SurveyPreviewContainer');
    const modal = document.getElementById('ai2PreviewModal');
    const openBtn = document.getElementById('ai2OpenPreviewBtn');
    const closeBtn = document.getElementById('ai2ClosePreviewBtn');

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
