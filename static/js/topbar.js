(function () {
  "use strict";

  function initTopbarNotifications() {
    var list = document.querySelector(".dh-notification-list[data-user-key]");
    if (!list) {
      return;
    }

    var items = Array.prototype.slice.call(
      list.querySelectorAll(".dh-notification-item[data-notification-id]")
    );
    var storageKey = "dh_read_notifications_" + list.getAttribute("data-user-key");
    var emptyState = list.querySelector("[data-notification-empty-read]");
    var badges = Array.prototype.slice.call(
      document.querySelectorAll(
        "#topbarNotifications .dh-notif-badge, #topbarNotificationsMenu .dh-menu-count"
      )
    );

    function getReadIds() {
      try {
        var raw = window.localStorage.getItem(storageKey);
        var parsed = raw ? JSON.parse(raw) : [];
        return Array.isArray(parsed) ? parsed : [];
      } catch (error) {
        return [];
      }
    }

    function saveReadIds(ids) {
      try {
        window.localStorage.setItem(storageKey, JSON.stringify(ids));
      } catch (error) {
        /* storage unavailable; read state is session-only */
      }
    }

    function updateCount() {
      var unread = items.filter(function (item) {
        return !item.classList.contains("dh-notification-read");
      }).length;

      badges.forEach(function (badge) {
        if (unread > 0) {
          badge.textContent = unread;
          badge.classList.remove("d-none");
        } else {
          badge.classList.add("d-none");
        }
      });

      if (emptyState) {
        emptyState.classList.toggle("d-none", unread > 0);
      }
    }

    if (!items.length) {
      return;
    }

    var readIds = getReadIds();
    items.forEach(function (item) {
      var id = item.getAttribute("data-notification-id");
      if (readIds.indexOf(id) !== -1) {
        item.classList.add("dh-notification-read");
      }

      item.addEventListener("click", function () {
        if (item.classList.contains("dh-notification-read")) {
          return;
        }

        item.classList.add("dh-notification-read");
        readIds.push(id);
        saveReadIds(readIds);
        updateCount();
      });
    });

    updateCount();
  }

  function initTopbarDropdowns() {
    var buttons = Array.prototype.slice.call(
      document.querySelectorAll(".dh-topbar [data-dh-dropdown]")
    );

    if (!buttons.length) {
      return;
    }

    function setOpen(button, open) {
      var menu = document.getElementById(button.getAttribute("aria-controls"));
      var wrapper = button.closest(".dropdown");

      if (!menu) {
        return;
      }

      menu.classList.toggle("show", open);
      button.setAttribute("aria-expanded", open ? "true" : "false");

      if (wrapper) {
        wrapper.classList.toggle("show", open);
      }
    }

    function closeAll(exceptButton) {
      buttons.forEach(function (button) {
        if (button !== exceptButton) {
          setOpen(button, false);
        }
      });
    }

    buttons.forEach(function (button) {
      button.addEventListener("click", function (event) {
        event.preventDefault();
        event.stopPropagation();

        var isOpen = button.getAttribute("aria-expanded") === "true";
        closeAll(button);
        setOpen(button, !isOpen);
      });
    });

    document.addEventListener("click", function (event) {
      if (!event.target.closest(".dh-topbar .dropdown")) {
        closeAll();
      }
    });

    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") {
        closeAll();
      }
    });
  }

  function init() {
    initTopbarDropdowns();
    initTopbarNotifications();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
