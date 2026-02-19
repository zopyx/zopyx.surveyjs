/**
 * Privacy Forms Studio (PFS) view behavior for @@pfs.
 * Powers the template combobox and selection UX.
 */
/**
 * Initialize the PFS template combobox behavior.
 */
(function initPfsTemplateCombobox() {
  var combo = document.getElementById("pfs-template-combobox");
  if (!combo) {
    return;
  }
  var search = combo.querySelector("#pfs-template-search");
  var select = combo.querySelector("#pfs-template-select");
  var optionsBox = combo.querySelector(".pfs-combobox-options");
  var toggle = combo.querySelector(".pfs-combobox-toggle");
  var optionItems = [];
  /**
   * Build the selectable option list from the native select.
   */
  var buildOptions = function () {
    optionsBox.innerHTML = "";
    optionItems = [];
    for (var i = 0; i < select.options.length; i++) {
      var option = select.options[i];
      var div = document.createElement("div");
      div.className = "pfs-combobox-option" + (option.selected ? " is-active" : "");
      div.setAttribute("data-value", option.value || "");
      div.textContent = option.text || "";
      optionsBox.appendChild(div);
      optionItems.push(div);
    }
  };
  buildOptions();
  /**
   * Move the options list into the document body once for positioning.
   */
  var ensurePortal = function () {
    if (optionsBox.getAttribute("data-portal") === "true") {
      return;
    }
    optionsBox.setAttribute("data-portal", "true");
    document.body.appendChild(optionsBox);
  };
  /**
   * Position the floating options list under the search input.
   */
  var positionOptions = function () {
    var rect = search.getBoundingClientRect();
    optionsBox.style.position = "fixed";
    optionsBox.style.left = rect.left + "px";
    optionsBox.style.top = rect.bottom + 6 + "px";
    optionsBox.style.width = rect.width + "px";
  };
  /**
   * Open the options list.
   */
  var openList = function () {
    ensurePortal();
    positionOptions();
    optionsBox.classList.add("is-open");
  };
  /**
   * Close the options list.
   */
  var closeList = function () {
    optionsBox.classList.remove("is-open");
  };
  /**
   * Update active item styling.
   * @param {HTMLElement} option
   */
  var setActive = function (option) {
/**
 * @function
 */
    optionItems.forEach(function (item) {
      item.classList.toggle("is-active", item === option);
    });
  };
  /**
   * Update selection in the native select and input.
   * @param {HTMLElement} option
   */
  var setSelection = function (option) {
    if (!option) {
      return;
    }
    var value = option.getAttribute("data-value") || "";
    var label = option.textContent || "";
    select.value = value;
    search.value = label.trim();
    setActive(option);
    closeList();
  };
  /**
   * Filter options by the current input text.
   */
  var filterOptions = function () {
    var query = search.value.trim().toLowerCase();
/**
 * @function
 */
    optionItems.forEach(function (option) {
      if (!option.getAttribute("data-value")) {
        option.classList.toggle("is-hidden", query.length > 0);
        return;
      }
      var match = option.textContent.toLowerCase().indexOf(query) !== -1;
      option.classList.toggle("is-hidden", !match);
    });
  };
  /**
   * Close list when clicking outside.
   * @param {MouseEvent} event
   */
  var handleDocumentClick = function (event) {
    if (!combo.contains(event.target) && !optionsBox.contains(event.target)) {
      closeList();
    }
  };
  /**
   * Toggle list visibility.
   * @param {MouseEvent} event
   */
  var handleToggleClick = function (event) {
    if (optionsBox.classList.contains("is-open")) {
      closeList();
    } else {
      openList();
    }
  };
  /**
   * Filter and open list on input.
   * @param {InputEvent} event
   */
  var handleSearchInput = function (event) {
    filterOptions();
    openList();
  };
  /**
   * Reposition list on resize.
   * @param {UIEvent} event
   */
  var handleWindowResize = function (event) {
    if (optionsBox.classList.contains("is-open")) {
      positionOptions();
    }
  };
  /**
   * Reposition list on scroll.
   * @param {Event} event
   */
  var handleWindowScroll = function (event) {
    if (optionsBox.classList.contains("is-open")) {
      positionOptions();
    }
  };

  toggle.addEventListener("click", handleToggleClick);
  search.addEventListener("focus", openList);
  search.addEventListener("input", handleSearchInput);
  /**
   * Attach click handler to a combobox option.
   * @param {HTMLElement} option
   */
  var attachOptionHandler = function (option) {
    /**
     * Apply selection when clicking an option.
     * @param {MouseEvent} event
     */
    var handleOptionClick = function (event) {
      setSelection(option);
    };
    option.addEventListener("click", handleOptionClick);
  };
  optionItems.forEach(attachOptionHandler);
  window.addEventListener("resize", handleWindowResize);
  window.addEventListener("scroll", handleWindowScroll, true);
  document.addEventListener("click", handleDocumentClick);
})();
