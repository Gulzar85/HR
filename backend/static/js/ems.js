/* EMS UI behaviour. CSP-safe: no inline handlers, no eval. Alpine components are registered here. */
(function () {
  "use strict";

  document.addEventListener("alpine:init", function () {
    Alpine.data("navToggle", function () {
      return {
        open: false,
        toggle() { this.open = !this.open; },
        close() { this.open = false; },
      };
    });
    Alpine.data("permGroup", function () {
      return {
        toggleAll(event) {
          var checked = event.target.checked;
          this.$root.querySelectorAll('input[type="checkbox"][name="permissions"]').forEach(function (box) {
            box.checked = checked;
          });
        },
      };
    });
  });

  function icons() {
    if (window.lucide) { window.lucide.createIcons(); }
  }
  document.addEventListener("DOMContentLoaded", icons);
  window.addEventListener("load", icons);
  document.addEventListener("htmx:afterSwap", icons);

  /* Confirmation dialog for destructive POST forms: <form data-confirm="Message"> */
  document.addEventListener("submit", function (event) {
    var form = event.target;
    var message = form.getAttribute && form.getAttribute("data-confirm");
    if (message && !form.dataset.confirmed) {
      var dialog = document.getElementById("confirm-dialog");
      if (!dialog || !dialog.showModal) { return; }
      event.preventDefault();
      dialog.querySelector("[data-confirm-message]").textContent = message;
      dialog.returnValue = "";
      dialog.onclose = function () {
        if (dialog.returnValue === "confirm") {
          form.dataset.confirmed = "1";
          form.requestSubmit();
        }
      };
      dialog.showModal();
      return;
    }
    /* loading state: disable the submit button once the form is really being sent */
    var button = form.querySelector && form.querySelector('button[type="submit"][data-loading]');
    if (button) {
      button.setAttribute("aria-busy", "true");
      button.disabled = true;
    }
  });

  /* Password visibility toggle: <button type="button" data-toggle-password="#id_password"> */
  document.addEventListener("click", function (event) {
    var btn = event.target.closest && event.target.closest("[data-toggle-password]");
    if (!btn) { return; }
    var input = document.querySelector(btn.getAttribute("data-toggle-password"));
    if (!input) { return; }
    var show = input.type === "password";
    input.type = show ? "text" : "password";
    btn.setAttribute("aria-pressed", show ? "true" : "false");
    btn.setAttribute("aria-label", show ? "Hide password" : "Show password");
  });
})();
