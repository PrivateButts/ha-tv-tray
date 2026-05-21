import json
import logging
import os
import signal
import sys

from PySide6.QtCore import QEvent, QPoint, QTimer, QUrl, Qt
from PySide6.QtGui import QIcon, QPainter, QColor, QPixmap, QCursor, QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QSystemTrayIcon,
    QMenu,
    QVBoxLayout,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import (
    QWebEngineUrlRequestInterceptor,
    QWebEngineScript,
    QWebEngineProfile,
)

from .config import Config

log = logging.getLogger("ha-tv-tray")

ESC_MARKER = "__ha_tv_tray_escape__"


class AuthInterceptor(QWebEngineUrlRequestInterceptor):
    def __init__(self, ha_url: str, token: str) -> None:
        super().__init__()
        self.ha_url = ha_url.rstrip("/")
        self.token = token

    def interceptRequest(self, info) -> None:
        url = info.requestUrl().toString()
        if url.startswith(self.ha_url):
            info.setHttpHeader(
                b"Authorization", f"Bearer {self.token}".encode()
            )


class RemoteWindow(QMainWindow):
    """Frameless tool window holding the webview. Closes on WindowDeactivate."""

    def __init__(self, config: Config) -> None:
        super().__init__()
        self.config = config
        self._panel_open = False

        self.setWindowTitle("TV Remote")
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_DeleteOnClose, False)

        self.setStyleSheet(
            "RemoteWindow { background: palette(window); "
            "border: 1px solid palette(mid); }"
        )

        self._setup_webview()
        self._setup_ui()

        esc = QShortcut(QKeySequence(Qt.Key_Escape), self,
                        context=Qt.ApplicationShortcut)
        esc.activated.connect(self._on_escape)
        esc.activatedAmbiguously.connect(self._on_escape)

    def _on_escape(self) -> None:
        if self._panel_open:
            log.debug("Escape, closing")
            self.hide_slide()

    def _setup_webview(self) -> None:
        profile = QWebEngineProfile.defaultProfile()
        profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.MemoryHttpCache)

        self._inject_auth_script(profile)
        self._setup_interceptor(profile)

        self.webview = QWebEngineView()
        page = self.webview.page()
        page.certificateError.connect(
            lambda error: error.acceptCertificate()
        )
        page.titleChanged.connect(self._on_title_changed)
        page.loadFinished.connect(self._on_page_loaded)

        url = f"{self.config.ha_url}{self.config.dashboard_path}"
        log.info("loading HA dashboard: %s", url)
        self.webview.load(QUrl(url))

    def _on_page_loaded(self, ok: bool) -> None:
        log.info("page loaded: ok=%s", ok)
        if ok:
            self.webview.page().runJavaScript(f"""
                document.addEventListener('keydown', function(e) {{
                    if (e.key === 'Escape') {{
                        e.preventDefault();
                        e.stopPropagation();
                        document.title = '{ESC_MARKER}';
                    }}
                }}, true);
            """)

    def _on_title_changed(self, title: str) -> None:
        if title == ESC_MARKER and self._panel_open:
            log.debug("Escape from webview, closing")
            self.hide_slide()

    def _inject_auth_script(self, profile: QWebEngineProfile) -> None:
        tokens = {
            "access_token": self.config.ha_token,
            "token_type": "Bearer",
            "expires_in": 86400,
            "refresh_token": self.config.ha_token,
            "client_id": f"{self.config.ha_url}/",
            "hassUrl": self.config.ha_url,
        }
        script = QWebEngineScript()
        script.setName("hass_auth")
        script.setWorldId(QWebEngineScript.MainWorld)
        script.setInjectionPoint(QWebEngineScript.DocumentCreation)
        script.setRunsOnSubFrames(False)
        script.setSourceCode(
            "localStorage.setItem('hassTokens', JSON.stringify("
            f"{json.dumps(tokens)}"
            "));"
        )
        profile.scripts().insert(script)

    def _setup_interceptor(self, profile: QWebEngineProfile) -> None:
        interceptor = AuthInterceptor(
            self.config.ha_url, self.config.ha_token
        )
        profile.setUrlRequestInterceptor(interceptor)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.webview)
        self.setFixedSize(self.config.panel_width, self.config.panel_height)

    # -- Show / hide --------------------------------------------------------

    def show_slide(self) -> None:
        self.setFixedSize(self.config.panel_width, self.config.panel_height)
        screen = QApplication.primaryScreen().availableGeometry()
        margin = 8
        w = self.width()
        h = self.height()
        x = screen.right() - w - margin
        y = screen.bottom() - h - margin
        log.debug("showing at (%d,%d)", x, y)

        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()
        self.webview.setFocus()
        self._panel_open = True

    def hide_slide(self) -> None:
        log.debug("hiding")
        self.hide()
        self._panel_open = False

    def changeEvent(self, e) -> None:
        if e.type() == QEvent.WindowDeactivate and self._panel_open:
            log.debug("window deactivated, closing")
            self.hide_slide()
        super().changeEvent(e)


class SystrayApp:
    def __init__(self, config: Config) -> None:
        self.config = config

        if os.environ.get("XDG_SESSION_TYPE") == "wayland":
            os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
            log.info("Wayland detected, forcing Qt platform to xcb")

        self.app = QApplication(sys.argv)
        log.info("Qt platform: %s", QApplication.platformName())
        self.app.setApplicationName("HA TV Tray")
        self.app.setOrganizationName("ha-tv-tray")

        self._setup_signal_handling()
        self._setup_tick_timer()

        self.panel = RemoteWindow(config)

        self._tray_menu = QMenu()
        show_act = self._tray_menu.addAction("Show/Hide Remote")
        show_act.triggered.connect(self._toggle_panel)
        self._tray_menu.addSeparator()
        quit_act = self._tray_menu.addAction("Quit")
        quit_act.triggered.connect(self._quit)

        self.tray = QSystemTrayIcon()
        self.tray.setIcon(self._make_icon())
        self.tray.setToolTip("TV Remote")
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.setContextMenu(self._tray_menu)
        QTimer.singleShot(0, self.tray.show)

        log.info("tray icon shown")

    def _make_icon(self) -> QIcon:
        icon = QIcon.fromTheme("video-television")
        if not icon.isNull():
            return icon
        icon = QIcon.fromTheme("tv")
        if not icon.isNull():
            return icon

        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.transparent)
        p = QPainter(pixmap)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#3a7bd5"))
        p.drawRoundedRect(3, 5, 26, 18, 3, 3)
        p.drawRect(12, 23, 8, 4)
        p.drawRect(8, 27, 4, 3)
        p.drawRect(20, 27, 4, 3)
        p.end()
        return QIcon(pixmap)

    def _on_tray_activated(self, reason: int) -> None:
        name = getattr(reason, "name", str(reason))
        log.debug("tray activated: %s", name)
        if reason == QSystemTrayIcon.Context:
            self._tray_menu.exec(QCursor.pos())
        elif reason in (
            QSystemTrayIcon.Trigger,
            QSystemTrayIcon.DoubleClick,
            QSystemTrayIcon.Unknown,
        ):
            self._toggle_panel()

    def _toggle_panel(self) -> None:
        log.debug("toggle panel")
        if self.panel._panel_open:
            self.panel.hide_slide()
        else:
            self.panel.show_slide()

    def _setup_signal_handling(self) -> None:
        for s in (signal.SIGINT, signal.SIGTERM):
            signal.signal(s, self._handle_signal)

    def _handle_signal(self, signum: int, _frame) -> None:
        log.warning("received signal %d, quitting", signum)
        self._quit()

    def _setup_tick_timer(self) -> None:
        self._tick_timer = QTimer()
        self._tick_timer.timeout.connect(lambda: None)
        self._tick_timer.start(200)

    def _quit(self) -> None:
        log.info("quitting")
        self._tick_timer.stop()
        self.panel.close()
        QTimer.singleShot(0, self.app.quit)

    def run(self) -> int:
        return self.app.exec()
