const bundleCache = new Map();
const intFormatter = new Intl.NumberFormat("en-US");

function getAnnouncer() {
  return document.getElementById("status-announcer");
}

function announce(message) {
  const announcer = getAnnouncer();
  if (!announcer) return;
  announcer.textContent = "";
  requestAnimationFrame(() => {
    announcer.textContent = message;
  });
}

function getDataRoot() {
  const raw = document.body?.dataset?.dataRoot || "./data/";
  return raw.endsWith("/") ? raw : `${raw}/`;
}

async function fetchBundle(filename) {
  const base = new URL(getDataRoot(), document.baseURI);
  const resolvedUrl = new URL(filename, base).href;
  if (bundleCache.has(resolvedUrl)) {
    return bundleCache.get(resolvedUrl);
  }

  const pending = fetch(resolvedUrl, { headers: { Accept: "application/json" } }).then(
    async (response) => {
      if (!response.ok) {
        throw new Error(`Failed to fetch ${filename} (${response.status})`);
      }
      return response.json();
    }
  );

  bundleCache.set(resolvedUrl, pending);
  try {
    return await pending;
  } catch (err) {
    bundleCache.delete(resolvedUrl);
    throw err;
  }
}

function formatInt(value) {
  const num = Number(value);
  return Number.isFinite(num) ? intFormatter.format(num) : String(value ?? "");
}

function formatPct(value, digits = 2) {
  const num = Number(value);
  return Number.isFinite(num) ? `${num.toFixed(digits)}%` : String(value ?? "");
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function hasFocusableDescendant(element) {
  return Boolean(
    element.querySelector(
      'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
    )
  );
}

function initTabs(root) {
  if (!root || root.dataset.tabsBound === "1") {
    return root?._agyisTabs || null;
  }

  const tablist = root.querySelector('[role="tablist"]');
  const tabs = Array.from(root.querySelectorAll('[role="tab"]'));
  const panels = Array.from(root.querySelectorAll('[role="tabpanel"]'));
  if (!tablist || tabs.length === 0 || panels.length === 0) return null;

  root.dataset.tabsBound = "1";
  const supportsFocusGroup = Object.hasOwn(HTMLElement.prototype, "focusGroup");
  let currentIndex = 0;

  function panelForTab(tab) {
    return panels.find((panel) => panel.getAttribute("aria-labelledby") === tab.id);
  }

  function selectTab(nextTab, { focus = false, scroll = true, notify = true } = {}) {
    const activePanel = panelForTab(nextTab);
    if (!activePanel) return;

    currentIndex = Math.max(0, tabs.indexOf(nextTab));

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

    if (scroll && typeof nextTab.scrollIntoView === "function") {
      try {
        nextTab.scrollIntoView({
          block: "nearest",
          inline: "nearest",
        });
      } catch {
        nextTab.scrollIntoView(false);
      }
    }

    if (focus) {
      nextTab.focus();
    }

    if (notify) {
      root.dispatchEvent(
        new CustomEvent("agyis:tabchange", {
          detail: {
            index: currentIndex,
            total: tabs.length,
            tab: nextTab,
            panel: activePanel,
          },
        })
      );
    }
  }

  const initialTab =
    tabs.find((tab) => tab.getAttribute("aria-selected") === "true") || tabs[0];
  selectTab(initialTab, { focus: false, scroll: false, notify: true });

  for (const tab of tabs) {
    tab.addEventListener("click", () => {
      selectTab(tab, { focus: false, scroll: true });
    });

    tab.addEventListener("focus", () => {
      if (tab.getAttribute("aria-selected") !== "true") {
        selectTab(tab, { focus: false, scroll: true });
      }
    });

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

  for (const panel of panels) {
    panel.addEventListener("beforematch", () => {
      const ownerId = panel.getAttribute("aria-labelledby");
      const ownerTab = tabs.find((tab) => tab.id === ownerId);
      if (ownerTab) {
        selectTab(ownerTab, { focus: false, scroll: true });
      }
    });
  }

  const controller = {
    selectIndex(idx, options = {}) {
      const clamped = Math.max(0, Math.min(tabs.length - 1, idx));
      selectTab(tabs[clamped], options);
    },
    getIndex() {
      return currentIndex;
    },
    count: tabs.length,
  };

  root._agyisTabs = controller;
  return controller;
}

async function copyStringToClipboard(text) {
  if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
    try {
      await navigator.clipboard.writeText(text);
      return;
    } catch {
      // Fall through to textarea + execCommand fallback on permission or non-HTTPS rejection
    }
  }

  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.setAttribute("aria-hidden", "true");
  area.style.position = "fixed";
  area.style.top = "0";
  area.style.left = "-9999px";
  area.style.opacity = "0";
  document.body.appendChild(area);
  area.focus({ preventScroll: true });
  area.select();
  area.setSelectionRange(0, area.value.length);
  let ok = false;
  try {
    ok = document.execCommand("copy");
  } catch {
    ok = false;
  }
  area.remove();
  if (!ok) {
    throw new Error("Clipboard fallback failed");
  }
}

function bindCopyButtons(root = document) {
  if (!root) return;
  const selector = "[data-copy], [data-copy-text], [data-copy-target]";
  const buttons = root.querySelectorAll(selector);

  for (const button of buttons) {
    if (button.dataset.copyBound === "1") continue;
    button.dataset.copyBound = "1";

    let resetTimer = 0;
    const defaultLabel = button.dataset.copyDefaultLabel || button.textContent.trim();
    button.dataset.copyDefaultLabel = defaultLabel;

    button.addEventListener("click", async () => {
      let text =
        button.getAttribute("data-copy") ||
        button.getAttribute("data-copy-text") ||
        "";

      const targetSelector = button.getAttribute("data-copy-target");
      if (!text && targetSelector) {
        const targetEl = document.querySelector(targetSelector);
        if (targetEl) {
          text = targetEl.textContent || "";
        }
      }

      text = text.trim();
      if (!text) return;

      const successLabel = button.getAttribute("data-copy-label") || "Copied";

      try {
        await copyStringToClipboard(text);
        button.textContent = successLabel;
        button.classList.add("is-copied");
        button.dataset.copyState = "copied";
        const announcement =
          button.getAttribute("data-copy-announce") ||
          `Copied ${text.length > 72 ? "snippet" : text} to clipboard`;
        announce(announcement);
      } catch {
        button.textContent = "Failed";
        button.classList.remove("is-copied");
        button.dataset.copyState = "failed";
        announce("Unable to copy text to clipboard");
      }

      clearTimeout(resetTimer);
      resetTimer = setTimeout(() => {
        button.textContent = defaultLabel;
        button.classList.remove("is-copied");
        delete button.dataset.copyState;
      }, 2200);
    });
  }
}

function initHeaderScroll() {
  const header = document.querySelector(".site-header");
  if (!header) return;

  const updateHeader = () => {
    header.classList.toggle("is-scrolled", window.scrollY > 24);
  };

  updateHeader();
  window.addEventListener("scroll", updateHeader, { passive: true });
}

function initNavbar() {
  const nav = document.getElementById("site-nav");
  if (!nav) return;

  const toggle = nav.querySelector(".nav-toggle");
  const links = nav.querySelector(".nav-links");
  if (!toggle || !links) return;

  const desktopQuery = window.matchMedia("(min-width: 900px)");

  function setMenuOpen(open, { returnFocus = false } = {}) {
    links.classList.toggle("is-open", open);
    toggle.setAttribute("aria-expanded", String(open));
    toggle.textContent = open ? "Close" : "Menu";
    if (!open && returnFocus) {
      toggle.focus();
    }
  }

  toggle.addEventListener("click", () => {
    const isOpen = links.classList.contains("is-open");
    setMenuOpen(!isOpen);
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && links.classList.contains("is-open")) {
      setMenuOpen(false, { returnFocus: true });
    }
  });

  document.addEventListener("click", (event) => {
    if (!links.classList.contains("is-open")) return;
    if (!nav.contains(event.target)) {
      setMenuOpen(false);
    }
  });

  for (const link of links.querySelectorAll("a")) {
    link.addEventListener("click", () => {
      if (links.classList.contains("is-open")) {
        setMenuOpen(false);
      }
    });
  }

  const handleMediaChange = (event) => {
    if (event.matches && links.classList.contains("is-open")) {
      setMenuOpen(false);
    }
  };

  if (typeof desktopQuery.addEventListener === "function") {
    desktopQuery.addEventListener("change", handleMediaChange);
  }
}

function initOnboardingStepper() {
  const containers = document.querySelectorAll("[data-tabs]");
  for (const container of containers) {
    const controls = container.querySelector(".stepper-controls");
    if (!controls) continue;

    const prevBtn = controls.querySelector("[data-step-prev]");
    const nextBtn = controls.querySelector("[data-step-next]");
    const statusEl = controls.querySelector(".stepper-status");
    const controller = initTabs(container);
    if (!controller || !prevBtn || !nextBtn || !statusEl) continue;

    const updateStatus = (index, total) => {
      statusEl.textContent = `Phase ${index + 1} / ${total}`;
      prevBtn.disabled = index <= 0;
      nextBtn.disabled = index >= total - 1;
    };

    updateStatus(controller.getIndex(), controller.count);

    container.addEventListener("agyis:tabchange", (event) => {
      const { index, total } = event.detail;
      updateStatus(index, total);
    });

    prevBtn.addEventListener("click", () => {
      const next = controller.getIndex() - 1;
      if (next >= 0) {
        controller.selectIndex(next, { focus: false, scroll: true });
      }
    });

    nextBtn.addEventListener("click", () => {
      const next = controller.getIndex() + 1;
      if (next < controller.count) {
        controller.selectIndex(next, { focus: false, scroll: true });
      }
    });
  }
}

function bootSharedShell() {
  document.querySelectorAll("[data-tabs]").forEach((el) => initTabs(el));
  initOnboardingStepper();
  bindCopyButtons(document);
  initHeaderScroll();
  initNavbar();
}

window.AgyisSite = Object.freeze({
  getDataRoot,
  fetchBundle,
  formatInt,
  formatPct,
  escapeHtml,
  bindCopyButtons,
  initTabs,
  announce,
});

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", bootSharedShell, { once: true });
} else {
  bootSharedShell();
}
