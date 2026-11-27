const bundleCache = new Map();
const intFormatter = new Intl.NumberFormat("en-US");
const THEME_STORAGE_KEY = "color-scheme";
const TILT_MAX_DEG = 2.2;
let themeGlobalsBound = false;

function getColorSchemeMeta() {
  return document.querySelector('meta[name="color-scheme"]');
}

function readStoredColorScheme() {
  try {
    const value = localStorage.getItem(THEME_STORAGE_KEY);
    return value === "light" || value === "dark" ? value : null;
  } catch {
    return null;
  }
}

function writeStoredColorScheme(scheme) {
  try {
    if (scheme === "light" || scheme === "dark") {
      localStorage.setItem(THEME_STORAGE_KEY, scheme);
    } else {
      localStorage.removeItem(THEME_STORAGE_KEY);
    }
  } catch {
    // Ignore storage denial (e.g. strict privacy modes); meta state still applies in-memory
  }
}

function getSystemTheme() {
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function getActiveTheme() {
  const metaContent = getColorSchemeMeta()?.getAttribute("content")?.trim();
  if (metaContent === "light" || metaContent === "dark") {
    return metaContent;
  }
  const stored = readStoredColorScheme();
  if (stored) {
    return stored;
  }
  return getSystemTheme();
}

function applyMetaColorScheme(contentValue) {
  const meta = getColorSchemeMeta();
  if (meta && meta.getAttribute("content") !== contentValue) {
    meta.setAttribute("content", contentValue);
  }
}

function dispatchThemeChange(theme) {
  window.dispatchEvent(
    new CustomEvent("agyis-theme-change", {
      detail: { theme },
    })
  );
}

function initThemeToggle() {
  const initialStored = readStoredColorScheme();
  if (initialStored) {
    applyMetaColorScheme(initialStored);
  }

  if (!themeGlobalsBound) {
    themeGlobalsBound = true;

    window.addEventListener("storage", (event) => {
      if (event.key !== null && event.key !== THEME_STORAGE_KEY) return;
      const nextStored =
        event.key === THEME_STORAGE_KEY &&
        (event.newValue === "light" || event.newValue === "dark")
          ? event.newValue
          : readStoredColorScheme();
      applyMetaColorScheme(nextStored ?? "light dark");
      dispatchThemeChange(getActiveTheme());
    });

    const schemeQuery = window.matchMedia("(prefers-color-scheme: dark)");
    const handleSystemSchemeChange = () => {
      // Never remove stored override when OS changes to match it; only notify when following system
      if (!readStoredColorScheme()) {
        const metaContent = getColorSchemeMeta()?.getAttribute("content")?.trim();
        if (metaContent !== "light" && metaContent !== "dark") {
          dispatchThemeChange(getActiveTheme());
        }
      }
    };

    if (typeof schemeQuery.addEventListener === "function") {
      schemeQuery.addEventListener("change", handleSystemSchemeChange);
    }
  }

  const toggleBtn = document.getElementById("theme-toggle");
  if (!toggleBtn || toggleBtn.dataset.themeBound === "1") return;
  toggleBtn.dataset.themeBound = "1";

  toggleBtn.addEventListener("click", () => {
    const current = getActiveTheme();
    const systemScheme = getSystemTheme();
    const target = current === "dark" ? "light" : "dark";
    const root = document.documentElement;

    if (root) {
      root.classList.add("is-theme-switching");
    }

    if (target !== systemScheme) {
      writeStoredColorScheme(target);
      applyMetaColorScheme(target);
    } else {
      writeStoredColorScheme(null);
      applyMetaColorScheme("light dark");
    }

    if (root) {
      void root.offsetHeight;
      requestAnimationFrame(() => root.classList.remove("is-theme-switching"));
    }

    dispatchThemeChange(target);
    announce(`Switched to ${target} theme`);
  });
}

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

function clampValue(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function resetTiltCard(card) {
  if (!card) return;
  if (card._agyisTiltRaf) {
    cancelAnimationFrame(card._agyisTiltRaf);
    card._agyisTiltRaf = 0;
  }
  delete card.dataset.tilting;
  card.style.removeProperty("--tilt-x");
  card.style.removeProperty("--tilt-y");
  card.style.removeProperty("--spot-x");
  card.style.removeProperty("--spot-y");
}

function initPointerTilt(root = document) {
  if (!root) return;
  const motionQuery = window.matchMedia("(prefers-reduced-motion: no-preference)");
  const hoverQuery = window.matchMedia("(hover: hover)");
  const isTiltEnabled = () => motionQuery.matches && hoverQuery.matches;

  const cards = root.querySelectorAll("[data-tilt], .art-card, .kpi-card");
  if (cards.length === 0) return;

  if (!isTiltEnabled()) {
    for (const card of cards) {
      resetTiltCard(card);
    }
  }

  for (const card of cards) {
    if (card.dataset.tiltBound === "1") continue;
    card.dataset.tiltBound = "1";

    let lastX = 0;
    let lastY = 0;

    const scheduleUpdate = (event) => {
      if (!isTiltEnabled() || event.pointerType === "touch") {
        resetTiltCard(card);
        return;
      }
      lastX = event.clientX;
      lastY = event.clientY;
      card.dataset.tilting = "1";
      if (card._agyisTiltRaf) return;

      card._agyisTiltRaf = requestAnimationFrame(() => {
        card._agyisTiltRaf = 0;
        if (!isTiltEnabled() || card.dataset.tilting !== "1") return;
        const rect = card.getBoundingClientRect();
        if (rect.width <= 0 || rect.height <= 0) return;

        const relX = clampValue(lastX - rect.left, 0, rect.width);
        const relY = clampValue(lastY - rect.top, 0, rect.height);
        const normX = relX / rect.width - 0.5;
        const normY = relY / rect.height - 0.5;

        const tiltX = clampValue(-normY * (TILT_MAX_DEG * 2), -TILT_MAX_DEG, TILT_MAX_DEG);
        const tiltY = clampValue(normX * (TILT_MAX_DEG * 2), -TILT_MAX_DEG, TILT_MAX_DEG);

        card.style.setProperty("--tilt-x", `${tiltX.toFixed(2)}deg`);
        card.style.setProperty("--tilt-y", `${tiltY.toFixed(2)}deg`);
        card.style.setProperty("--spot-x", `${relX.toFixed(1)}px`);
        card.style.setProperty("--spot-y", `${relY.toFixed(1)}px`);
      });
    };

    card.addEventListener("pointerenter", scheduleUpdate);
    card.addEventListener("pointermove", scheduleUpdate);
    card.addEventListener("pointerleave", () => resetTiltCard(card));
    card.addEventListener("pointercancel", () => resetTiltCard(card));
  }

  if (!root._agyisTiltListenersBound) {
    root._agyisTiltListenersBound = true;
    const handleCapabilityChange = () => {
      if (!isTiltEnabled()) {
        document
          .querySelectorAll("[data-tilt], .art-card, .kpi-card")
          .forEach((card) => resetTiltCard(card));
      }
    };
    if (typeof motionQuery.addEventListener === "function") {
      motionQuery.addEventListener("change", handleCapabilityChange);
    }
    if (typeof hoverQuery.addEventListener === "function") {
      hoverQuery.addEventListener("change", handleCapabilityChange);
    }
  }
}

function bootSharedShell() {
  initThemeToggle();
  document.querySelectorAll("[data-tabs]").forEach((el) => initTabs(el));
  initOnboardingStepper();
  bindCopyButtons(document);
  initHeaderScroll();
  initNavbar();
  initPointerTilt(document);
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
  getActiveTheme,
});

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", bootSharedShell, { once: true });
} else {
  bootSharedShell();
}
