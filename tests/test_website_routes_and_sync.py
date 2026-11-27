# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""Hermetic verification suite for the 5-route Orbital Aegis website and SSOT parity."""

from __future__ import annotations

import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import unittest
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urlsplit

from harness.delivery import sync_check

REPO_ROOT = Path(__file__).resolve().parent.parent
WEBSITE_DIR = REPO_ROOT / "website"
DATA_DIR = WEBSITE_DIR / "data"
PAGES_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "pages.yml"

EXPECTED_ROUTES: Tuple[str, ...] = (
    "index.html",
    "telemetry/index.html",
    "cognitive/index.html",
    "hud-re/index.html",
    "brand/index.html",
)

EXTERNAL_SCHEMES: Tuple[str, ...] = (
    "http://",
    "https://",
    "mailto:",
    "tel:",
    "data:",
    "javascript:",
)

_HOME_PATH_RE = re.compile(r"/home/[A-Za-z0-9._-]+")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_RAW_SECRET_PREFIX_RE = re.compile(
    r"(?:ghp_|github_pat_|AKIA|sk-|AIza|-----BEGIN)"
)
_HTML_SECRET_TOKEN_RE = re.compile(
    r"(?:ghp_[A-Za-z0-9]{10,}|github_pat_[A-Za-z0-9_]{10,}|AKIA[0-9A-Z]{12,}"
    r"|\bsk-[A-Za-z0-9_-]{12,}|AIza[0-9A-Za-z_-]{15,}"
    r"|-----BEGIN\s+[A-Z ]*PRIVATE KEY-----)"
)


class _RouteDocumentParser(HTMLParser):
    """Collects head metadata, IDs, local references, primary nav links, and footer text."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.charset_utf8: bool = False
        self.has_viewport: bool = False
        self.title_parts: List[str] = []
        self._in_title: bool = False
        self.body_attrs: Dict[str, str] = {}
        self.ids: Set[str] = set()
        self.local_refs: List[Tuple[str, str, str]] = []  # (tag, attr, raw_url)
        self.has_site_nav: bool = False
        self._nav_depth: int = 0
        self.site_nav_hrefs: List[str] = []
        self._footer_depth: int = 0
        self.footer_text_parts: List[str] = []
        self.input_attrs_by_id: Dict[str, Dict[str, Optional[str]]] = {}
        self._capture_tabpanel_id: Optional[str] = None
        self._tabpanel_depth: int = 0
        self.tabpanels_by_labelledby: Dict[str, List[str]] = {}
        self.color_scheme_meta_content: Optional[str] = None
        self._expect_fouc_script: bool = False
        self._in_fouc_script: bool = False
        self._fouc_script_parts: List[str] = []
        self.fouc_script_after_meta: str = ""
        self._nav_actions_div_depth: int = 0
        self.has_theme_toggle_in_nav_actions: bool = False
        self.img_attrs: List[Dict[str, Optional[str]]] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        attr_map: Dict[str, Optional[str]] = {k.lower(): v for k, v in attrs}
        if self._expect_fouc_script:
            self._expect_fouc_script = False
            if tag == "script" and "src" not in attr_map:
                self._in_fouc_script = True

        elem_id = attr_map.get("id")
        if elem_id:
            self.ids.add(elem_id)

        if tag == "meta":
            charset = (attr_map.get("charset") or "").strip().lower()
            if charset == "utf-8":
                self.charset_utf8 = True
            meta_name = (attr_map.get("name") or "").strip().lower()
            meta_content = (attr_map.get("content") or "").strip()
            if meta_name == "viewport" and meta_content:
                self.has_viewport = True
            if meta_name == "color-scheme":
                self.color_scheme_meta_content = meta_content
                if meta_content == "light dark":
                    self._expect_fouc_script = True
        elif tag == "title":
            self._in_title = True
        elif tag == "body":
            self.body_attrs = {k: (v or "") for k, v in attr_map.items()}
        elif tag == "input" and elem_id:
            self.input_attrs_by_id[elem_id] = attr_map
        elif tag == "img":
            self.img_attrs.append(attr_map)

        if tag == "div":
            if self._nav_actions_div_depth > 0:
                self._nav_actions_div_depth += 1
            elif "nav-actions" in (attr_map.get("class") or "").split():
                self._nav_actions_div_depth = 1
        if self._nav_actions_div_depth > 0 and elem_id == "theme-toggle":
            self.has_theme_toggle_in_nav_actions = True

        if tag == "nav":
            if elem_id == "site-nav":
                self.has_site_nav = True
                self._nav_depth = 1
            elif self._nav_depth > 0:
                self._nav_depth += 1

        if tag == "footer":
            self._footer_depth += 1

        if self._capture_tabpanel_id is not None:
            self._tabpanel_depth += 1
        elif tag == "div" and attr_map.get("role") == "tabpanel":
            labelled = attr_map.get("aria-labelledby")
            if labelled:
                self._capture_tabpanel_id = labelled
                self._tabpanel_depth = 1
                self.tabpanels_by_labelledby.setdefault(labelled, [])

        if self._nav_depth > 0 and tag == "a":
            href = (attr_map.get("href") or "").strip()
            if href:
                self.site_nav_hrefs.append(href)

        for ref_attr in ("href", "src"):
            val = (attr_map.get(ref_attr) or "").strip()
            if val:
                self.local_refs.append((tag, ref_attr, val))

        srcset = (attr_map.get("srcset") or "").strip()
        if srcset:
            for candidate in srcset.split(","):
                url_part = candidate.strip().split()[0] if candidate.strip() else ""
                if url_part:
                    self.local_refs.append((tag, "srcset", url_part))

    def handle_startendtag(
        self, tag: str, attrs: List[Tuple[str, Optional[str]]]
    ) -> None:
        self.handle_starttag(tag, attrs)
        if (
            tag in ("nav", "footer")
            or self._capture_tabpanel_id is not None
            or (tag == "div" and self._nav_actions_div_depth > 0)
            or (tag == "script" and self._in_fouc_script)
        ):
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag != "meta":
            self._expect_fouc_script = False
        if tag == "script" and self._in_fouc_script:
            self._in_fouc_script = False
            self.fouc_script_after_meta = "".join(self._fouc_script_parts).strip()
        if tag == "title":
            self._in_title = False
        if tag == "div" and self._nav_actions_div_depth > 0:
            self._nav_actions_div_depth -= 1
        if tag == "nav" and self._nav_depth > 0:
            self._nav_depth -= 1
        if tag == "footer" and self._footer_depth > 0:
            self._footer_depth -= 1
        if self._capture_tabpanel_id is not None:
            self._tabpanel_depth -= 1
            if self._tabpanel_depth <= 0:
                self._capture_tabpanel_id = None
                self._tabpanel_depth = 0

    def handle_data(self, data: str) -> None:
        if self._in_fouc_script:
            self._fouc_script_parts.append(data)
        elif self._expect_fouc_script and data.strip():
            self._expect_fouc_script = False
        if self._in_title:
            self.title_parts.append(data)
        if self._footer_depth > 0:
            self.footer_text_parts.append(data)
        if self._capture_tabpanel_id is not None:
            self.tabpanels_by_labelledby[self._capture_tabpanel_id].append(data)

    @property
    def title(self) -> str:
        return "".join(self.title_parts).strip()

    @property
    def footer_text(self) -> str:
        return " ".join("".join(self.footer_text_parts).split())


def _parse_route(rel_route: str) -> _RouteDocumentParser:
    path = WEBSITE_DIR / rel_route
    parser = _RouteDocumentParser()
    parser.feed(path.read_text(encoding="utf-8"))
    parser.close()
    return parser


def _resolve_relative_target(source_html: Path, raw_url: str) -> Tuple[Path, str]:
    """Resolve a non-external relative href/src to an on-disk path and optional fragment."""
    parts = urlsplit(raw_url)
    rel_path = parts.path
    fragment = parts.fragment
    if not rel_path:
        return source_html.resolve(), fragment
    candidate = (source_html.parent / rel_path).resolve()
    if candidate.is_dir():
        candidate = (candidate / "index.html").resolve()
    return candidate, fragment


class TestWebsiteRoutesAndSync(unittest.TestCase):
    """Hermetic verification for all 5 static routes, JSON data bundles, CI, and SSOT sync."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.parsed_routes: Dict[str, _RouteDocumentParser] = {}
        cls.ids_by_resolved_html: Dict[Path, Set[str]] = {}
        for rel_route in EXPECTED_ROUTES:
            html_path = (WEBSITE_DIR / rel_route).resolve()
            if html_path.is_file():
                parsed = _parse_route(rel_route)
                cls.parsed_routes[rel_route] = parsed
                cls.ids_by_resolved_html[html_path] = parsed.ids

    def test_five_routes_exist_and_parse_with_required_head_metadata(self) -> None:
        for rel_route in EXPECTED_ROUTES:
            html_path = WEBSITE_DIR / rel_route
            self.assertTrue(html_path.is_file(), f"Missing route HTML: {rel_route}")
            parsed = self.parsed_routes[rel_route]
            self.assertTrue(parsed.charset_utf8, f"{rel_route} missing <meta charset='utf-8'>")
            self.assertTrue(parsed.title, f"{rel_route} missing non-empty <title>")
            self.assertTrue(parsed.has_viewport, f"{rel_route} missing <meta name='viewport'>")
            self.assertTrue(parsed.has_site_nav, f"{rel_route} missing <nav id='site-nav'>")
            data_root = parsed.body_attrs.get("data-data-root", "")
            self.assertTrue(data_root, f"{rel_route} missing body[data-data-root]")
            self.assertFalse(
                data_root.startswith("/"),
                f"{rel_route} uses root-absolute data-data-root={data_root!r}",
            )
            resolved_data = (html_path.parent / data_root).resolve()
            self.assertEqual(
                resolved_data,
                DATA_DIR.resolve(),
                f"{rel_route} data-data-root does not resolve to website/data/",
            )

    def test_primary_site_nav_links_to_all_five_routes_via_relative_paths(self) -> None:
        expected_targets = {(WEBSITE_DIR / r).resolve() for r in EXPECTED_ROUTES}
        for rel_route in EXPECTED_ROUTES:
            source_html = WEBSITE_DIR / rel_route
            parsed = self.parsed_routes[rel_route]
            resolved_nav_targets: Set[Path] = set()
            for href in parsed.site_nav_hrefs:
                if href.startswith(EXTERNAL_SCHEMES):
                    continue
                self.assertFalse(
                    href.startswith("/"),
                    f"{rel_route} <nav id='site-nav'> contains root-absolute href={href!r}",
                )
                target, _fragment = _resolve_relative_target(source_html, href)
                resolved_nav_targets.add(target)
            missing = expected_targets - resolved_nav_targets
            self.assertEqual(
                missing,
                set(),
                f"{rel_route} <nav id='site-nav'> missing route links: {sorted(str(p) for p in missing)}",
            )

    def test_all_local_links_assets_and_fragments_resolve_without_root_absolute_paths(self) -> None:
        website_root = WEBSITE_DIR.resolve()
        for rel_route in EXPECTED_ROUTES:
            source_html = WEBSITE_DIR / rel_route
            parsed = self.parsed_routes[rel_route]
            for tag, attr, raw_url in parsed.local_refs:
                if raw_url.startswith(EXTERNAL_SCHEMES):
                    continue
                self.assertFalse(
                    raw_url.startswith("/"),
                    f"{rel_route} <{tag} {attr}='{raw_url}'> uses forbidden root-absolute path",
                )
                target, fragment = _resolve_relative_target(source_html, raw_url)
                try:
                    target.relative_to(website_root)
                except ValueError as exc:
                    self.fail(
                        f"{rel_route} <{tag} {attr}='{raw_url}'> escapes website/ root: {exc}"
                    )
                self.assertTrue(
                    target.is_file(),
                    f"{rel_route} broken local reference <{tag} {attr}='{raw_url}'> -> {target}",
                )
                if fragment:
                    target_ids = self.ids_by_resolved_html.get(target)
                    self.assertIsNotNone(
                        target_ids,
                        f"{rel_route} fragment #{fragment} points to non-indexed file {target}",
                    )
                    self.assertIn(
                        fragment,
                        target_ids or set(),
                        f"{rel_route} broken fragment anchor <{tag} {attr}='{raw_url}'> (#{fragment} missing in {target.relative_to(website_root)})",
                    )

    def test_required_site_assets_scripts_and_brand_files_exist(self) -> None:
        required_files = (
            "styles.css",
            "app.js",
            "telemetry/telemetry.js",
            "cognitive/cognitive.js",
            "hud-re/hud-re.js",
            "assets/art/art-cognitive-lattice.webp",
            "assets/art/art-cognitive-lattice.png",
            "assets/art/art-telemetry-optics.webp",
            "assets/art/art-telemetry-optics.png",
            "data/manifest.json",
            "data/overview.json",
            "data/eras.json",
            "data/models.json",
            "data/fleet_and_team.json",
            "data/deep_metrics.json",
        )
        for rel_asset in required_files:
            asset_path = WEBSITE_DIR / rel_asset
            self.assertTrue(asset_path.is_file(), f"Missing required website asset: {rel_asset}")
            self.assertGreater(
                asset_path.stat().st_size,
                0,
                f"Website asset is empty: {rel_asset}",
            )

        svg_assets = sorted((WEBSITE_DIR / "brand" / "svg").glob("*.svg"))
        raster_assets = sorted((WEBSITE_DIR / "brand" / "raster").glob("*"))
        self.assertGreater(len(svg_assets), 0, "website/brand/svg/ must contain SVG assets")
        self.assertGreater(len(raster_assets), 0, "website/brand/raster/ must contain raster assets")

    def test_json_bundles_schema_and_manifest_integrity(self) -> None:
        manifest = json.loads((DATA_DIR / "manifest.json").read_text(encoding="utf-8"))
        self.assertIn("schema_version", manifest)
        self.assertIn("bundles", manifest)
        privacy = manifest["privacy_audit"]
        self.assertIs(privacy["raw_prompts_included"], False)
        self.assertIs(privacy["emails_redacted"], True)
        self.assertIs(privacy["secrets_stripped"], True)
        self.assertIs(privacy["home_paths_anonymized"], True)
        self.assertIs(privacy["leak_checks_passed"], True)

        expected_bundle_names = {
            "overview.json",
            "eras.json",
            "models.json",
            "fleet_and_team.json",
            "deep_metrics.json",
        }
        self.assertEqual(set(manifest["bundles"].keys()), expected_bundle_names)
        for bundle_name, meta in manifest["bundles"].items():
            # Exporter hashes UTF-8 JSON body prior to POSIX trailing newline
            canonical_bytes = (DATA_DIR / bundle_name).read_bytes().rstrip(b"\n")
            self.assertEqual(
                len(canonical_bytes),
                meta["bytes"],
                f"Byte size mismatch for {bundle_name}",
            )
            self.assertEqual(
                hashlib.sha256(canonical_bytes).hexdigest(),
                meta["sha256"],
                f"SHA-256 mismatch for {bundle_name}",
            )

        overview = json.loads((DATA_DIR / "overview.json").read_text(encoding="utf-8"))
        self.assertEqual(overview["totals"]["total_sessions"], 3856)
        self.assertIn("compaction_highlights", overview)
        inv = overview["workspace_inventory"]
        for key in ("skills", "agents", "hooks", "aff"):
            self.assertIn(key, inv)

        eras = json.loads((DATA_DIR / "eras.json").read_text(encoding="utf-8"))
        self.assertIsInstance(eras["eras"], list)
        self.assertEqual(len(eras["eras"]), 12)
        self.assertIn("model_controlled_comparison", eras)
        self.assertIn("summary", eras)

        models = json.loads((DATA_DIR / "models.json").read_text(encoding="utf-8"))
        rt = models["reasoning_tiers"]
        for key in ("tiers", "canonical_models", "isolated_unattributed", "summary"):
            self.assertIn(key, rt)
        self.assertIn("canonical_models", models)
        self.assertIn("model_profiles", models)

        fleet = json.loads((DATA_DIR / "fleet_and_team.json").read_text(encoding="utf-8"))
        for dev in ("kuasha420", "local", "contributor-b7b2be88"):
            self.assertIn(dev, fleet["developers"])
        for surf in ("ide", "cli"):
            self.assertIn(surf, fleet["client_surfaces"])
        self.assertIn("source_kinds", fleet)

        deep = json.loads((DATA_DIR / "deep_metrics.json").read_text(encoding="utf-8"))
        for key in (
            "volume_summary",
            "compactor_simulations",
            "tool_distributions",
            "exit_code_1_breakdown",
            "context_dynamics",
            "titan_sessions",
        ):
            self.assertIn(key, deep)
        self.assertIn("macro_summary", deep["titan_sessions"])
        self.assertIn("sessions", deep["titan_sessions"])

    def test_zero_secret_email_or_home_path_leaks_across_data_and_html(self) -> None:
        json_files = sorted(DATA_DIR.glob("*.json"))
        self.assertEqual(len(json_files), 6)
        for jpath in json_files:
            content = jpath.read_text(encoding="utf-8")
            self.assertIsNone(
                _HOME_PATH_RE.search(content),
                f"Leaked /home/ path in {jpath.name}",
            )
            self.assertIsNone(
                _EMAIL_RE.search(content),
                f"Leaked email pattern in {jpath.name}",
            )
            self.assertIsNone(
                _RAW_SECRET_PREFIX_RE.search(content),
                f"Leaked secret prefix in {jpath.name}",
            )

        html_files = sorted(WEBSITE_DIR.rglob("*.html"))
        self.assertEqual(len(html_files), 5)
        for hpath in html_files:
            content = hpath.read_text(encoding="utf-8")
            rel = hpath.relative_to(WEBSITE_DIR)
            self.assertIsNone(
                _HOME_PATH_RE.search(content),
                f"Leaked /home/ path in website/{rel}",
            )
            self.assertIsNone(
                _EMAIL_RE.search(content),
                f"Leaked email pattern in website/{rel}",
            )
            self.assertIsNone(
                _HTML_SECRET_TOKEN_RE.search(content),
                f"Leaked secret token in website/{rel}",
            )

    def test_landing_page_wave13_and_wave14_ground_truth(self) -> None:
        index_text = (WEBSITE_DIR / "index.html").read_text(encoding="utf-8")
        self.assertIn("[... AGYIS Compactor:", index_text)
        self.assertIn('"decision": "continue"', index_text)
        self.assertNotIn("[... PSL Compactor:", index_text)
        self.assertIsNone(
            re.search(r"\b16\s+vs\.?\s+4\b", index_text, re.I),
            "website/index.html contains stale '16 vs 4' canonical tool claim",
        )
        self.assertIsNone(
            re.search(r"\bepochs?\b", index_text, re.I),
            "website/index.html contains stray 'epoch' terminology instead of 'checkpoint'",
        )

        parsed_index = self.parsed_routes["index.html"]
        anti_loop_panel = "".join(parsed_index.tabpanels_by_labelledby.get("wb-tab-loop", []))
        self.assertTrue(anti_loop_panel, "Missing Anti-Loop workbench tabpanel (wb-tab-loop)")
        self.assertIn('"decision": "deny"', anti_loop_panel)
        self.assertNotIn(
            '"hook":',
            anti_loop_panel,
            "Anti-Loop workbench snippet must not include forbidden 'hook' wire key",
        )

    def test_telemetry_observatory_provenance_and_legacy_filter_contract(self) -> None:
        telemetry_html = (WEBSITE_DIR / "telemetry" / "index.html").read_text(encoding="utf-8")
        telemetry_js = (WEBSITE_DIR / "telemetry" / "telemetry.js").read_text(encoding="utf-8")

        self.assertIn("@kuasha420", telemetry_html)
        self.assertIn("Purrfect Software Limited (PSL)", telemetry_html)
        self.assertIn("voluntary", telemetry_html.lower())
        self.assertIn("server/", telemetry_html)
        self.assertIn("POST /api/v1/auth/verify", telemetry_html)

        parsed_telemetry = self.parsed_routes["telemetry/index.html"]
        legacy_input = parsed_telemetry.input_attrs_by_id.get("include-legacy-toggle")
        self.assertIsNotNone(legacy_input, "Missing #include-legacy-toggle checkbox in telemetry/index.html")
        self.assertNotIn(
            "checked",
            legacy_input or {},
            "#include-legacy-toggle must default to unchecked (OFF) in HTML",
        )
        self.assertIn("legacyToggle.checked = false", telemetry_js)
        self.assertIn("unattributed_legacy", telemetry_js)

    def test_all_five_route_footers_contain_stewardship_and_trademark_notice(self) -> None:
        for rel_route in EXPECTED_ROUTES:
            footer = self.parsed_routes[rel_route].footer_text
            self.assertIn(
                "Copyright (c) 2026 Arafat Zahan (@kuasha420)",
                footer,
                f"{rel_route} footer missing founder copyright",
            )
            self.assertIn(
                "Purrfect Software Limited (PSL)",
                footer,
                f"{rel_route} footer missing PSL stewardship notice",
            )
            self.assertIn(
                "ICARO-42/b",
                footer,
                f"{rel_route} footer missing ICARO-42/b governance reference",
            )
            self.assertIn(
                "Google Antigravity",
                footer,
                f"{rel_route} footer missing Google Antigravity trademark notice",
            )
            self.assertIn(
                "trademark of Google LLC",
                footer,
                f"{rel_route} footer missing Google LLC trademark disclaimer",
            )

    def test_pages_ci_workflow_declares_race_free_build_and_deploy_jobs(self) -> None:
        self.assertTrue(PAGES_WORKFLOW.is_file(), "Missing .github/workflows/pages.yml")
        wf = PAGES_WORKFLOW.read_text(encoding="utf-8")
        build_idx = wf.find("\n  build:")
        deploy_idx = wf.find("\n  deploy:")
        self.assertGreater(build_idx, 0, "pages.yml missing 'build' job")
        self.assertGreater(deploy_idx, build_idx, "pages.yml missing 'deploy' job after 'build'")

        build_block = wf[build_idx:deploy_idx]
        deploy_block = wf[deploy_idx:]
        self.assertIn("actions/upload-pages-artifact@v3", build_block)
        self.assertIn("needs: build", deploy_block)
        self.assertIn("actions/deploy-pages@v4", deploy_block)

    def test_light_dark_theme_and_polarity_adaptive_chart_contract(self) -> None:
        for rel_route in EXPECTED_ROUTES:
            parsed = self.parsed_routes[rel_route]
            self.assertEqual(
                parsed.color_scheme_meta_content,
                "light dark",
                f"{rel_route} missing <meta name='color-scheme' content='light dark'>",
            )
            self.assertIn(
                'localStorage.getItem("color-scheme")',
                parsed.fouc_script_after_meta,
                f"{rel_route} missing immediate inline FOUC-prevention script after color-scheme meta",
            )
            self.assertTrue(
                parsed.has_theme_toggle_in_nav_actions,
                f"{rel_route} missing #theme-toggle inside .nav-actions",
            )

        styles_text = (WEBSITE_DIR / "styles.css").read_text(encoding="utf-8")
        for required_css in (
            "color-scheme: light dark;",
            ':has(> head > meta[name="color-scheme"][content="dark"])',
            "@supports (color: light-dark(white, black))",
            "--chart-grid: light-dark(",
            "--chart-ink: light-dark(",
        ):
            self.assertIn(required_css, styles_text, f"website/styles.css missing {required_css!r}")

        telemetry_js = (WEBSITE_DIR / "telemetry" / "telemetry.js").read_text(encoding="utf-8")
        for chart_var in (
            "var(--chart-grid)",
            "var(--chart-axis)",
            "var(--chart-ink)",
            "var(--chart-line)",
            "var(--chart-bar)",
            "var(--chart-bar-strong)",
            "var(--chart-dot-fill)",
        ):
            self.assertIn(chart_var, telemetry_js, f"telemetry.js missing polarity-adaptive token {chart_var}")
        telemetry_js_lower = telemetry_js.lower()
        for legacy_hex in ("#9aa8be", "#1e2c47"):
            self.assertNotIn(
                legacy_hex,
                telemetry_js_lower,
                f"telemetry.js still contains dark-only hardcoded color {legacy_hex}",
            )

        for rel_route, image_name in (
            ("index.html", "art-deterministic-gate.png"),
            ("hud-re/index.html", "art-telemetry-optics.png"),
        ):
            img_matches = [
                attrs
                for attrs in self.parsed_routes[rel_route].img_attrs
                if (attrs.get("src") or "").endswith(image_name)
            ]
            self.assertGreater(
                len(img_matches),
                0,
                f"{rel_route} missing primary 3D illustration {image_name}",
            )
            for attrs in img_matches:
                self.assertNotEqual(
                    (attrs.get("loading") or "").strip().lower(),
                    "lazy",
                    f"{rel_route} primary illustration {image_name} must not carry loading='lazy'",
                )

    def test_website_index_and_workspace_sync_check_parity(self) -> None:
        report = sync_check.run_sync_check(REPO_ROOT, include_site=True)
        self.assertEqual(
            report["mismatches"],
            [],
            f"SSOT sync-check mismatches detected: {report['mismatches']}",
        )
        self.assertEqual(report["status"], "PASS")

        live_tests = int(report["tests"]["live_tests"])
        self.assertGreaterEqual(live_tests, 2548)

        index_text = (WEBSITE_DIR / "index.html").read_text(encoding="utf-8")
        matched_counts: List[int] = []
        for match in sync_check._TOTAL_TEST_RE.finditer(index_text):
            raw = (match.group("badge") or match.group("bold") or match.group("count") or "").replace(",", "")
            if raw.isdigit() and int(raw) >= 1500:
                matched_counts.append(int(raw))
        self.assertGreater(
            len(matched_counts),
            0,
            "website/index.html must state the live test count matching sync_check._TOTAL_TEST_RE",
        )
        for claimed in matched_counts:
            self.assertEqual(
                claimed,
                live_tests,
                f"website/index.html claims {claimed:,} tests != live {live_tests:,}",
            )


if __name__ == "__main__":
    unittest.main()
