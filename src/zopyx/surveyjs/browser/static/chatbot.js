document.addEventListener("DOMContentLoaded", function () {
  const root = document.querySelector(".chatbot-page");
  if (!root) {
    return;
  }

  const apiUrl = root.dataset.chatApi;
  const form = document.getElementById("chatbotForm");
  const input = document.getElementById("chatbotInput");
  const sendBtn = document.getElementById("chatbotSend");
  const resetBtn = document.getElementById("chatbotReset");
  const streamToggle = document.getElementById("chatbotStream");
  const messages = document.getElementById("chatbotMessages");
  const sourcesEl = document.getElementById("chatbotSources");
  const followupsEl = document.getElementById("chatbotFollowups");
  const promptButtons = document.querySelectorAll(".chatbot-prompt");

  const history = [];

  const t = window._t || function (msgid) {
    return msgid;
  };

  function escapeHtml(text) {
    return String(text || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function renderRichText(text) {
    const source = escapeHtml(text);
    const lines = source.split("\n");
    const out = [];
    let inList = false;

    function closeListIfOpen() {
      if (inList) {
        out.push("</ul>");
        inList = false;
      }
    }

    lines.forEach((line) => {
      const trimmed = line.trim();
      if (!trimmed) {
        closeListIfOpen();
        out.push("<br/>");
        return;
      }
      if (trimmed.startsWith("### ")) {
        closeListIfOpen();
        out.push("<h4>" + trimmed.slice(4) + "</h4>");
        return;
      }
      if (trimmed.startsWith("## ")) {
        closeListIfOpen();
        out.push("<h3>" + trimmed.slice(3) + "</h3>");
        return;
      }
      if (trimmed.startsWith("# ")) {
        closeListIfOpen();
        out.push("<h2>" + trimmed.slice(2) + "</h2>");
        return;
      }
      if (trimmed.startsWith("- ") || trimmed.startsWith("* ")) {
        if (!inList) {
          out.push("<ul>");
          inList = true;
        }
        out.push("<li>" + trimmed.slice(2) + "</li>");
        return;
      }
      closeListIfOpen();
      out.push("<p>" + trimmed + "</p>");
    });
    closeListIfOpen();

    let html = out.join("");
    html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
    html = html.replace(
      /(^|<br\/>|<p>)(Sources|Confidence|Follow-ups|Recommendation|Note):/g,
      "$1<span class=\"chatbot-key-term\">$2:</span>"
    );
    return html;
  }

  function addMessage(role, text, extra, rich) {
    const div = document.createElement("div");
    div.className = "chatbot-message " + role;
    if (rich) {
      div.innerHTML = renderRichText(text);
    } else {
      div.textContent = text;
    }

    if (extra) {
      const meta = document.createElement("div");
      meta.className = "chatbot-meta";
      meta.textContent = extra;
      div.appendChild(meta);
    }

    messages.appendChild(div);
    messages.scrollTop = messages.scrollHeight;
    return div;
  }

  function setSources(sources, confidence) {
    if (!sources || !sources.length) {
      sourcesEl.textContent = t("Sources: none");
      return;
    }
    const names = sources.map((item) => item.source).filter(Boolean);
    sourcesEl.textContent =
      t("Sources") + ": " + names.join(", ") + " (" + t("confidence") + ": " + confidence + ")";
  }

  function setFollowups(followups) {
    followupsEl.innerHTML = "";
    if (!followups || !followups.length) {
      return;
    }
    const label = document.createElement("strong");
    label.textContent = t("Follow-ups") + ": ";
    followupsEl.appendChild(label);

    followups.forEach((text) => {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "chatbot-chip";
      chip.textContent = text;
      chip.addEventListener("click", function () {
        input.value = text;
        input.focus();
      });
      followupsEl.appendChild(chip);
    });
  }

  function toFormData(payload) {
    const data = new FormData();
    data.append("message", payload.message);
    data.append("current_view", payload.current_view);
    data.append("survey_title", payload.survey_title);
    data.append("user_role", payload.user_role);
    data.append("history", JSON.stringify(payload.history || []));
    data.append("survey_json", JSON.stringify(payload.survey_json || {}));
    data.append("stream", payload.stream ? "true" : "false");
    data.append("_authenticator", window.CSRF_TOKEN || "");
    return data;
  }

  async function sendNormal(payload) {
    const response = await fetch(apiUrl, {
      method: "POST",
      body: toFormData(payload),
      credentials: "same-origin",
    });

    if (!response.ok) {
      let msg = t("Request failed");
      try {
        const err = await response.json();
        msg = err.message || err.error || msg;
      } catch (ignore) {
      }
      throw new Error(msg);
    }
    return response.json();
  }

  async function sendStream(payload, assistantEl) {
    const response = await fetch(apiUrl, {
      method: "POST",
      body: toFormData(payload),
      credentials: "same-origin",
      headers: {
        Accept: "text/event-stream",
      },
    });

    if (!response.ok || !response.body) {
      let msg = t("Streaming request failed");
      try {
        const err = await response.json();
        msg = err.message || err.error || msg;
      } catch (ignore) {
      }
      throw new Error(msg);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";
    let fullText = "";
    let finalEvent = null;

    while (true) {
      const result = await reader.read();
      if (result.done) {
        break;
      }
      buffer += decoder.decode(result.value, { stream: true });
      const blocks = buffer.split("\n\n");
      buffer = blocks.pop() || "";

      blocks.forEach((block) => {
        const line = block
          .split("\n")
          .find((entry) => entry.startsWith("data: "));
        if (!line) {
          return;
        }
        try {
          const payloadObj = JSON.parse(line.slice(6));
          if (payloadObj.chunk) {
            fullText += payloadObj.chunk;
            assistantEl.innerHTML = renderRichText(fullText);
          }
          if (payloadObj.done) {
            finalEvent = payloadObj;
          }
        } catch (ignore) {
        }
      });
    }

    return {
      response: fullText,
      sources: (finalEvent && finalEvent.sources) || [],
      followups: (finalEvent && finalEvent.followups) || [],
      confidence: (finalEvent && finalEvent.confidence) || "low",
    };
  }

  async function loadSurveyJson() {
    try {
      const response = await fetch(ACTUAL_URL + "/@@get-form-json", {
        credentials: "same-origin",
      });
      if (!response.ok) {
        return null;
      }
      const data = await response.json();
      if (data && typeof data === "object") {
        return data;
      }
    } catch (ignore) {
    }
    return null;
  }

  async function contextPayload(message) {
    const surveyJson = await loadSurveyJson();
    return {
      message,
      current_view: "@@chatbot",
      survey_title: document.title || "",
      user_role: "Editor",
      history,
      survey_json: surveyJson,
      stream: Boolean(streamToggle && streamToggle.checked),
    };
  }

  async function ask(message) {
    addMessage("user", message);
    const assistantEl = addMessage("assistant", t("Thinking..."), null, true);
    sendBtn.disabled = true;

    try {
      const payload = await contextPayload(message);
      const result = payload.stream
        ? await sendStream(payload, assistantEl)
        : await sendNormal(payload);

      assistantEl.innerHTML = renderRichText(result.response || t("No answer returned."));
      setSources(result.sources || [], result.confidence || "low");
      setFollowups(result.followups || []);

      history.push({ role: "user", content: message });
      history.push({ role: "assistant", content: result.response || "" });
    } catch (error) {
      assistantEl.innerHTML = renderRichText(error.message || t("Chat request failed."));
      setSources([], "low");
      setFollowups([]);
    } finally {
      sendBtn.disabled = false;
    }
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    const message = (input.value || "").trim();
    if (!message) {
      return;
    }
    input.value = "";
    ask(message);
  });

  resetBtn.addEventListener("click", function () {
    history.length = 0;
    messages.innerHTML = "";
    sourcesEl.innerHTML = "";
    followupsEl.innerHTML = "";
    input.focus();
  });

  promptButtons.forEach((button) => {
    button.addEventListener("click", function () {
      input.value = button.dataset.prompt || "";
      input.focus();
    });
  });
});
