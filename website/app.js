const announcer = document.getElementById("status-announcer");

function announce(message) {
  if (!announcer) return;
  announcer.textContent = "";
  requestAnimationFrame(() => {
    announcer.textContent = message;
  });
}

function hasFocusableDescendant(element) {
  return Boolean(
    element.querySelector(
      'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
    )
  );
}

function initTabsGroup(root) {
  const tablist = root.querySelector('[role="tablist"]');
  const tabs = Array.from(root.querySelectorAll('[role="tab"]'));
  const panels = Array.from(root.querySelectorAll('[role="tabpanel"]'));
  if (!tablist || tabs.length === 0 || panels.length === 0) return;

  const supportsFocusGroup = Object.hasOwn(HTMLElement.prototype, "focusGroup");

  function panelForTab(tab) {
    return panels.find((panel) => panel.getAttribute("aria-labelledby") === tab.id);
  }

  function selectTab(nextTab, { focus = false, scroll = true } = {}) {
    const activePanel = panelForTab(nextTab);
    if (!activePanel) return;

    for (const tab of tabs) {
      const isSelected = tab === nextTab;
      tab.setAttribute("aria-selected", String(isSelected));
      tab.toggleAttribute("focusgroupstart", isSelected);
      if (!supportsFocusGroup) {
        tab.tabIndex = isSelected ? 0 : -1;
      }
    }

    for (const panel of panels) {
      const isTarget = panel === activePanel;
      if (isTarget) {
        panel.removeAttribute("hidden");
        if (!hasFocusableDescendant(panel)) {
          panel.tabIndex = 0;
        } else {
          panel.removeAttribute("tabindex");
        }
      } else {
        panel.setAttribute("hidden", "until-found");
        panel.removeAttribute("tabindex");
      }
    }

    if (scroll) {
      nextTab.scrollIntoView({
        block: "nearest",
        inline: "nearest",
        container: "nearest",
      });
    }

    if (focus) {
      nextTab.focus();
    }
  }

  const initialTab =
    tabs.find((tab) => tab.getAttribute("aria-selected") === "true") || tabs[0];
  selectTab(initialTab, { focus: false, scroll: false });

  for (const tab of tabs) {
    tab.addEventListener("click", () => {
      selectTab(tab, { focus: false, scroll: true });
    });

    tab.addEventListener("focus", () => {
      if (tab.getAttribute("aria-selected") !== "true") {
        selectTab(tab, { focus: false, scroll: true });
      }
    });

    if (!supportsFocusGroup) {
      tab.addEventListener("keydown", (event) => {
        const index = tabs.indexOf(tab);
        let nextIndex = -1;

        if (event.key === "ArrowRight") {
          nextIndex = (index + 1) % tabs.length;
        } else if (event.key === "ArrowLeft") {
          nextIndex = (index - 1 + tabs.length) % tabs.length;
        } else if (event.key === "Home") {
          nextIndex = 0;
        } else if (event.key === "End") {
          nextIndex = tabs.length - 1;
        }

        if (nextIndex >= 0) {
          event.preventDefault();
          selectTab(tabs[nextIndex], { focus: true, scroll: true });
        }
      });
    }
  }

  for (const panel of panels) {
    panel.addEventListener("beforematch", () => {
      const ownerId = panel.getAttribute("aria-labelledby");
      const ownerTab = tabs.find((tab) => tab.id === ownerId);
      if (ownerTab) {
        selectTab(ownerTab, { focus: false, scroll: true });
      }
    });
  }
}

function initCopyButtons() {
  const buttons = document.querySelectorAll("[data-copy]");
  for (const button of buttons) {
    let resetTimer = 0;
    const defaultLabel = button.textContent.trim();

    button.addEventListener("click", async () => {
      const text = button.getAttribute("data-copy") || "";
      if (!text) return;

      try {
        await navigator.clipboard.writeText(text);
        button.textContent = "Copied";
        announce(`Copied ${text} to clipboard`);
      } catch {
        button.textContent = "Failed";
        announce("Unable to copy command to clipboard");
      }

      clearTimeout(resetTimer);
      resetTimer = setTimeout(() => {
        button.textContent = defaultLabel;
      }, 1800);
    });
  }
}

function initHeaderScrollFallback() {
  const header = document.querySelector(".site-header");
  if (!header) return;

  if (CSS.supports("(animation-timeline: scroll()) and (animation-range: 0% 100%)")) {
    return;
  }

  const updateHeader = () => {
    header.classList.toggle("is-scrolled", window.scrollY > 24);
  };

  updateHeader();
  window.addEventListener("scroll", updateHeader, { passive: true });
}

function initMobileDialog() {
  const openButton = document.querySelector(".nav-toggle");
  const dialog = document.getElementById("mobile-nav-dialog");
  if (!openButton || !(dialog instanceof HTMLDialogElement)) return;

  openButton.addEventListener("click", () => {
    dialog.showModal();
  });

  const closeButton = dialog.querySelector("[data-dialog-close]");
  if (closeButton) {
    closeButton.addEventListener("click", () => {
      dialog.close();
    });
  }

  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) {
      dialog.close();
    }
  });

  for (const link of dialog.querySelectorAll("a")) {
    link.addEventListener("click", () => {
      dialog.close();
    });
  }
}

document.querySelectorAll("[data-tabs]").forEach(initTabsGroup);
initCopyButtons();
initHeaderScrollFallback();
initMobileDialog();
