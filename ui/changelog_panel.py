"""
ui/changelog_panel.py — Changelog tab
Fetches all GitHub releases from the configured repo and renders them as
readable HTML inside a QTextBrowser.  Fetching is done in a background
QThread so the UI never blocks.  Remote images embedded in release notes
are loaded asynchronously and injected into the document without blocking.
"""

import json
import re
import urllib.request
from datetime import datetime

from PySide6.QtCore import Qt, QThread, Signal, QUrl, QByteArray, QTimer
from PySide6.QtGui import QImage, QTextDocument
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTextBrowser,
)

from version import APP_VERSION, GITHUB_REPO

# Maximum display width (px) for images — scaled down if wider
_IMG_MAX_WIDTH = 560


# ─────────────────────────────────────────────────────────────────────────────
#  Async image loader thread
# ─────────────────────────────────────────────────────────────────────────────

class _ImageLoader(QThread):
    """Downloads a single remote image in background and emits (url, QByteArray)."""

    loaded = Signal(str, QByteArray)   # url_str, raw bytes

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self._url = url

    def run(self):
        try:
            req = urllib.request.Request(
                self._url,
                headers={'User-Agent': 'MewgenicsStorageQOL/changelog'},
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                self.loaded.emit(self._url, QByteArray(resp.read()))
        except Exception:
            pass  # silently ignore — image just won't appear


# ─────────────────────────────────────────────────────────────────────────────
#  QTextBrowser subclass that loads remote images on demand
# ─────────────────────────────────────────────────────────────────────────────

class _RemoteImageBrowser(QTextBrowser):
    """
    QTextBrowser that intercepts ImageResource requests for http/https URLs,
    downloads them asynchronously, then re-renders the document so images
    appear at their correct size and position.

    Design:
    - _img_cache survives setHtml() calls → on re-render, cached images
      are returned synchronously from loadResource(), so layout is correct.
    - A 100 ms debounce timer batches multiple simultaneous image loads into
      a single re-render pass (avoids flicker from many rapid re-renders).
    - setHtml() is overridden to store _current_html so re-render can replay it.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._img_cache: dict[str, QImage] = {}    # url → QImage (survives setHtml)
        self._loading:   set[str]          = set()  # urls currently downloading
        self._loaders:   list[_ImageLoader] = []    # keep thread refs alive

        # Debounced re-layout: fires 120 ms after the last image arrives
        self._relayout_timer = QTimer(self)
        self._relayout_timer.setSingleShot(True)
        self._relayout_timer.setInterval(120)
        self._relayout_timer.timeout.connect(self._do_relayout)
        self._current_html: str = ''

    # ── Override setHtml to store current content ────────────────────────

    def setHtml(self, html: str):
        self._current_html = html
        super().setHtml(html)

    # ── loadResource: serve cached or kick off download ──────────────────

    def loadResource(self, resource_type: int, url: QUrl):
        if resource_type == QTextDocument.ResourceType.ImageResource:
            url_str = url.toString()
            if url_str.startswith(('http://', 'https://')):
                if url_str in self._img_cache:
                    return self._img_cache[url_str]   # served immediately
                if url_str not in self._loading:
                    self._loading.add(url_str)
                    loader = _ImageLoader(url_str, self)
                    loader.loaded.connect(self._on_image_loaded)
                    self._loaders.append(loader)
                    loader.start()
                return None   # placeholder while downloading
        return super().loadResource(resource_type, url)

    # ── Image arrives ────────────────────────────────────────────────────

    def _on_image_loaded(self, url_str: str, data: QByteArray):
        self._loading.discard(url_str)
        img = QImage()
        img.loadFromData(data)
        if img.isNull():
            return
        # Scale down to max display width
        if img.width() > _IMG_MAX_WIDTH:
            img = img.scaledToWidth(
                _IMG_MAX_WIDTH,
                Qt.TransformationMode.SmoothTransformation,
            )
        self._img_cache[url_str] = img
        # Schedule a debounced re-render so layout reflects the real image size
        self._relayout_timer.start()

    # ── Debounced re-render ───────────────────────────────────────────────

    def _do_relayout(self):
        """Re-apply current HTML; cached images now return synchronously → correct layout."""
        if not self._current_html:
            return
        scroll = self.verticalScrollBar().value()
        # super().setHtml avoids overwriting _current_html again
        super().setHtml(self._current_html)
        self.verticalScrollBar().setValue(scroll)

    # ── Cache management ─────────────────────────────────────────────────

    def clear_image_cache(self):
        """Reset all image state before loading a new changelog."""
        self._img_cache.clear()
        self._loading.clear()
        self._relayout_timer.stop()
        self._current_html = ''


# ─────────────────────────────────────────────────────────────────────────────
#  Markdown → HTML helpers (Qt-compatible subset)
# ─────────────────────────────────────────────────────────────────────────────

def _inline_md(text: str) -> str:
    """
    Apply inline Markdown to an already-HTML-escaped string.
    Handles: images, links, bold, italic, inline code.
    Images MUST be processed before links (![...] shares the link pattern).
    """
    # Images  ![alt text](url)  — add default width so Qt allocates layout space
    text = re.sub(
        r'!\[([^\]]*)\]\(([^)]+)\)',
        rf'<img src="\2" alt="\1" width="{_IMG_MAX_WIDTH}" />',
        text,
    )
    # Links  [text](url)
    text = re.sub(
        r'\[([^\]]+)\]\(([^)]+)\)',
        r'<a href="\2">\1</a>',
        text,
    )
    # Bold  **text**
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    # Italic  *text*
    text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<i>\1</i>', text)
    # Inline code  `text`
    text = re.sub(
        r'`([^`]+)`',
        r'<code style="background:#2a2a2a;color:#e0c060;padding:0 3px;">\1</code>',
        text,
    )
    return text


# Regex that matches a standalone Markdown image line  ![alt](url)
_STANDALONE_IMG_RE = re.compile(r'^!\[([^\]]*)\]\(([^)]+)\)$')

# Regexes for raw HTML <img> tags that GitHub sometimes injects
_RAW_IMG_TAG_RE = re.compile(r'<img\b([^>]*?)/?>', re.IGNORECASE)
_ATTR_SRC_RE    = re.compile(r'\bsrc=["\']([^"\']+)["\']',    re.IGNORECASE)
_ATTR_ALT_RE    = re.compile(r'\balt=["\']([^"\']*)["\']',    re.IGNORECASE)
_ATTR_WIDTH_RE  = re.compile(r'\bwidth=["\']?(\d+)["\']?',    re.IGNORECASE)
_ATTR_HEIGHT_RE = re.compile(r'\bheight=["\']?(\d+)["\']?',   re.IGNORECASE)
# Matches a line that is *only* a raw <img> tag (possibly with whitespace)
_ONLY_RAW_IMG_RE = re.compile(r'^\s*<img\b[^>]*/?>\s*$', re.IGNORECASE)


def _rebuild_img_tag(raw_attrs: str) -> str:
    """
    Extract src/alt/width/height from a raw <img> attribute string.
    Returns a clean <img> tag with dimensions scaled down to _IMG_MAX_WIDTH,
    so Qt pre-allocates the correct layout space before the image loads.
    """
    src_m = _ATTR_SRC_RE.search(raw_attrs)
    alt_m = _ATTR_ALT_RE.search(raw_attrs)
    w_m   = _ATTR_WIDTH_RE.search(raw_attrs)
    h_m   = _ATTR_HEIGHT_RE.search(raw_attrs)

    src = src_m.group(1) if src_m else ''
    alt = (alt_m.group(1) if alt_m else '').replace('"', '&quot;')

    if not src:
        return ''

    # Compute display dimensions
    if w_m and h_m:
        w = int(w_m.group(1))
        h = int(h_m.group(1))
        if w > _IMG_MAX_WIDTH:
            h = int(h * _IMG_MAX_WIDTH / w)
            w = _IMG_MAX_WIDTH
        size_attr = f' width="{w}" height="{h}"'
    elif w_m:
        w = min(int(w_m.group(1)), _IMG_MAX_WIDTH)
        size_attr = f' width="{w}"'
    else:
        # No dimension info — cap at max width; height will adjust on load
        size_attr = f' width="{_IMG_MAX_WIDTH}"'

    return f'<img src="{src}" alt="{alt}"{size_attr} />'


def _process_mixed_line(line: str) -> str:
    """
    Process a line that may contain raw HTML <img> tags mixed with plain text.
    HTML-escapes everything except <img> tags, which are rebuilt cleanly.
    """
    result   = []
    last_end = 0
    for m in _RAW_IMG_TAG_RE.finditer(line):
        before = line[last_end:m.start()]
        if before:
            esc = before.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            result.append(_inline_md(esc))
        img_tag = _rebuild_img_tag(m.group(1))
        if img_tag:
            result.append(img_tag)
        last_end = m.end()
    after = line[last_end:]
    if after:
        esc = after.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        result.append(_inline_md(esc))
    return ''.join(result)


def _markdown_to_html(text: str) -> str:
    """Convert a GitHub release body (Markdown) to Qt-friendly HTML."""
    lines   = text.replace('\r\n', '\n').split('\n')
    parts: list[str] = []
    in_list = False

    for line in lines:
        stripped = line.strip()

        # ── Bullet list item ──────────────────────────────────────────────
        if stripped.startswith('- ') or stripped.startswith('* '):
            if not in_list:
                parts.append('<ul style="margin:4px 0;padding-left:18px;">')
                in_list = True
            content = stripped[2:]
            content = content.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            parts.append(f'<li style="margin:1px 0;">{_inline_md(content)}</li>')
            continue

        # Close open list
        if in_list:
            parts.append('</ul>')
            in_list = False

        # ── Standalone Markdown image  ![alt](url) ────────────────────────
        md_img = _STANDALONE_IMG_RE.match(stripped)
        if md_img:
            alt = md_img.group(1).replace('&', '&amp;').replace('"', '&quot;')
            url = md_img.group(2)
            parts.append(
                f'<p style="text-align:center;margin:8px 0;">'
                f'<img src="{url}" alt="{alt}" width="{_IMG_MAX_WIDTH}" /></p>'
            )
            continue

        # ── Raw HTML <img> tag (e.g. from GitHub's renderer) ─────────────
        if '<img' in stripped.lower():
            raw_match = _RAW_IMG_TAG_RE.search(stripped)
            # Standalone: centre the image
            if _ONLY_RAW_IMG_RE.match(stripped) and raw_match:
                img_tag = _rebuild_img_tag(raw_match.group(1))
                if img_tag:
                    parts.append(
                        f'<p style="text-align:center;margin:8px 0;">{img_tag}</p>'
                    )
            else:
                # Mixed content: preserve img tags, escape the rest
                inner = _process_mixed_line(stripped)
                parts.append(f'<p style="margin:2px 0;color:#c0c0c0;">{inner}</p>')
            continue

        # HTML-escape the whole line before processing block elements
        esc = stripped.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

        # ── Headers ───────────────────────────────────────────────────────
        if stripped.startswith('### '):
            parts.append(
                f'<p style="font-size:13px;font-weight:bold;color:#a0c8ff;'
                f'margin:6px 0 2px 0;">{_inline_md(esc[4:])}</p>'
            )
        elif stripped.startswith('## '):
            parts.append(
                f'<p style="font-size:14px;font-weight:bold;color:#a0c8ff;'
                f'margin:8px 0 2px 0;">{_inline_md(esc[3:])}</p>'
            )
        elif stripped.startswith('# '):
            parts.append(
                f'<p style="font-size:15px;font-weight:bold;color:#a0c8ff;'
                f'margin:10px 0 2px 0;">{_inline_md(esc[2:])}</p>'
            )
        # ── Horizontal rule ───────────────────────────────────────────────
        elif stripped in ('---', '***', '___'):
            parts.append('<hr style="color:#333;"/>')
        # ── Blank line ────────────────────────────────────────────────────
        elif stripped == '':
            parts.append('<p style="margin:2px 0;"></p>')
        # ── Normal paragraph ─────────────────────────────────────────────
        else:
            parts.append(
                f'<p style="margin:2px 0;color:#c0c0c0;">{_inline_md(esc)}</p>'
            )

    if in_list:
        parts.append('</ul>')

    return '\n'.join(parts)


def _releases_to_html(releases: list[dict]) -> str:
    """Convert a list of GitHub release dicts to a full HTML document."""
    body_parts: list[str] = []

    for idx, rel in enumerate(releases):
        tag       = rel.get('tag_name', '')
        name      = rel.get('name') or tag
        body      = rel.get('body') or ''
        published = rel.get('published_at', '')
        is_pre    = rel.get('prerelease', False)
        is_draft  = rel.get('draft', False)
        is_cur    = (tag == APP_VERSION)

        # ── Date ─────────────────────────────────────────────────────────
        date_str = ''
        if published:
            try:
                dt = datetime.fromisoformat(published.replace('Z', '+00:00'))
                date_str = dt.strftime('%B %d, %Y')
            except Exception:
                date_str = published[:10]

        # ── Badge ────────────────────────────────────────────────────────
        if is_cur:
            badge = (
                '&nbsp;<span style="font-size:11px;font-weight:normal;'
                'color:#a5d6a7;">✔ Current</span>'
            )
        elif is_draft:
            badge = (
                '&nbsp;<span style="font-size:11px;font-weight:normal;'
                'color:#b0bec5;">Draft</span>'
            )
        elif is_pre:
            badge = (
                '&nbsp;<span style="font-size:11px;font-weight:normal;'
                'color:#ffcc80;">Pre-release</span>'
            )
        else:
            badge = ''

        # ── Separator between releases ────────────────────────────────────
        if idx > 0:
            body_parts.append('<hr style="color:#2a2a2a;margin:12px 0;"/>')

        # ── Title ─────────────────────────────────────────────────────────
        title_color = '#4a9eff' if is_cur else '#e0c060'
        body_parts.append(
            f'<p style="font-size:15px;font-weight:bold;color:{title_color};'
            f'margin:0 0 4px 0;">{name}{badge}</p>'
        )

        # ── Meta (tag + date) ─────────────────────────────────────────────
        meta_tokens: list[str] = []
        if tag and tag != name:
            meta_tokens.append(
                f'<code style="background:#2a2a2a;color:#a0c8ff;'
                f'padding:0 5px;">{tag}</code>'
            )
        if date_str:
            meta_tokens.append(
                f'<span style="color:#888;">{date_str}</span>'
            )
        if meta_tokens:
            body_parts.append(
                f'<p style="margin:0 0 8px 0;">'
                f'{"&nbsp;&nbsp;·&nbsp;&nbsp;".join(meta_tokens)}</p>'
            )

        # ── Body ──────────────────────────────────────────────────────────
        if body.strip():
            body_parts.append(_markdown_to_html(body))
        else:
            body_parts.append(
                '<p style="color:#555;font-style:italic;">No release notes.</p>'
            )

    html = (
        '<html>'
        '<body style="background:#1a1a1a;color:#d0d0d0;'
        'font-family:\'Segoe UI\',Arial,sans-serif;font-size:13px;">'
        '<div style="padding:8px 4px;">'
        + '\n'.join(body_parts)
        + '</div></body></html>'
    )
    return html


# ─────────────────────────────────────────────────────────────────────────────
#  Background fetch thread (releases JSON)
# ─────────────────────────────────────────────────────────────────────────────

class _FetchThread(QThread):
    """Fetches GitHub releases JSON in a background thread."""

    finished = Signal(list)   # list of release dicts
    error    = Signal(str)    # error message

    def __init__(self, repo: str, parent=None):
        super().__init__(parent)
        self._repo = repo

    def run(self):
        try:
            url = (
                f'https://api.github.com/repos/{self._repo}/releases'
                f'?per_page=100'
            )
            req = urllib.request.Request(
                url,
                headers={'User-Agent': 'MewgenicsStorageQOL/changelog'},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode('utf-8'))
            if not isinstance(data, list):
                self.error.emit(f'Unexpected response: {str(data)[:120]}')
                return
            self.finished.emit(data)
        except Exception as exc:
            self.error.emit(str(exc))


# ─────────────────────────────────────────────────────────────────────────────
#  Public widget
# ─────────────────────────────────────────────────────────────────────────────

class ChangelogPanel(QWidget):
    """
    Full-height panel shown when the Changelog tab is active.
    Fetches GitHub releases once (lazy) and renders them as styled HTML,
    including remote images loaded asynchronously.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._loaded       = False
        self._fetch_thread: _FetchThread | None = None
        self._build_ui()

    # ── Construction ─────────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(8)

        # Header row: title + refresh button
        header = QWidget()
        hl = QHBoxLayout(header)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(8)

        title_lbl = QLabel("📋  Changelog")
        title_lbl.setStyleSheet('font-size:20px;font-weight:bold;color:#e0c060;')
        hl.addWidget(title_lbl)
        hl.addStretch()

        self._refresh_btn = QPushButton('🔄 Refresh')
        self._refresh_btn.setStyleSheet(
            'QPushButton { font-size:11px;padding:4px 12px;border:1px solid #555;'
            'border-radius:4px;background:#2d2d2d;color:#ccc; }'
            'QPushButton:hover { background:#3a3a3a; }'
            'QPushButton:disabled { color:#555; }'
        )
        self._refresh_btn.clicked.connect(self._start_fetch)
        hl.addWidget(self._refresh_btn)
        layout.addWidget(header)

        # Status / loading label
        self._status_lbl = QLabel('Loading…')
        self._status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_lbl.setTextFormat(Qt.TextFormat.RichText)
        self._status_lbl.setStyleSheet('color:#888;font-size:13px;')
        layout.addWidget(self._status_lbl)

        # Remote-image-capable HTML browser
        self._browser = _RemoteImageBrowser()
        self._browser.setOpenExternalLinks(True)
        self._browser.setStyleSheet(
            'QTextBrowser { background:#1a1a1a;color:#d0d0d0;'
            'border:1px solid #333;border-radius:6px;'
            'font-size:13px;padding:6px; }'
            'QScrollBar:vertical { background:#1a1a1a;width:8px; }'
            'QScrollBar::handle:vertical { background:#444;border-radius:4px; }'
            'QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }'
        )
        self._browser.setVisible(False)
        layout.addWidget(self._browser, 1)

    # ── Public API ────────────────────────────────────────────────────────────

    def load_if_needed(self):
        """Lazily fetch releases the first time the tab is activated."""
        if not self._loaded:
            self._start_fetch()

    def force_reload(self):
        """Force a fresh network request regardless of cached state."""
        self._loaded = False
        self._start_fetch()

    # ── Fetch logic ──────────────────────────────────────────────────────────

    def _start_fetch(self):
        if self._fetch_thread and self._fetch_thread.isRunning():
            return

        self._browser.setVisible(False)
        self._status_lbl.setVisible(True)
        self._status_lbl.setText('🔄&nbsp;&nbsp;Loading changelog…')
        self._refresh_btn.setEnabled(False)

        self._fetch_thread = _FetchThread(GITHUB_REPO, parent=self)
        self._fetch_thread.finished.connect(self._on_releases_fetched)
        self._fetch_thread.error.connect(self._on_fetch_error)
        self._fetch_thread.start()

    def _on_releases_fetched(self, releases: list):
        self._loaded = True
        self._refresh_btn.setEnabled(True)
        self._status_lbl.setVisible(False)

        if not releases:
            self._browser.setHtml(
                '<html><body style="background:#1a1a1a;color:#888;">'
                '<p style="text-align:center;">No releases found.</p>'
                '</body></html>'
            )
            self._browser.setVisible(True)
            return

        # Clear stale images before rendering new HTML
        self._browser.clear_image_cache()
        self._browser.setHtml(_releases_to_html(releases))
        self._browser.setVisible(True)

    def _on_fetch_error(self, message: str):
        self._loaded = False
        self._refresh_btn.setEnabled(True)
        self._status_lbl.setText(
            f'<span style="color:#e57373;">⚠&nbsp;Failed to load changelog: {message}</span>'
        )
        self._status_lbl.setVisible(True)
        self._browser.setVisible(False)

