import json
import logging
import os
import signal
import sys

from PySide6.QtCore import QRect, QTimer, QUrl, Qt
from PySide6.QtGui import QIcon, QPainter, QColor, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QSystemTrayIcon,
    QMenu,
    QWidget,
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

_REASON_NAMES = {
    QSystemTrayIcon.Unknown: "Unknown",
    QSystemTrayIcon.Context: "Context",
    QSystemTrayIcon.DoubleClick: "DoubleClick",
    QSystemTrayIcon.Trigger: "Trigger",
    QSystemTrayIcon.MiddleClick: "MiddleClick",
}


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


class RemotePanel(QMainWindow):
    def __init__(self, config: Config) -> None:
        super().__init__()
        self.config = config

        self.setWindowTitle("TV Remote")
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.setAttribute(Qt.WA_TranslucentBackground, False)

        self._setup_webview()
        self._setup_ui()
        self._calculate_geometry()

    def _setup_webview(self) -> None:
        profile = QWebEngineProfile.defaultProfile()
        profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.MemoryHttpCache)
        profile.setHttpUserAgent(
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) QtWebEngine/6.0 Chrome/120.0"
        )

        self._inject_auth_script(profile)
        self._setup_interceptor(profile)

        self.webview = QWebEngineView()
        page = self.webview.page()
        if hasattr(page, "certificateError"):
            page.certificateError.connect(
                lambda error: error.acceptCertificate()
            )
        url = f"{self.config.ha_url}{self.config.dashboard_path}"
        log.info("loading HA dashboard: %s", url)
        self.webview.load(QUrl(url))

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
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.webview)
        self.setCentralWidget(container)

    def _calculate_geometry(self) -> None:
        screen = QApplication.primaryScreen().availableGeometry()
        w = self.config.panel_width
        h = self.config.panel_height
        margin = 8

        if self.config.position == "top-right":
            self._geo = QRect(screen.right() - w - margin, 26, w, h)
        else:
            self._geo = QRect(
                screen.right() - w - margin,
                screen.bottom() - h - margin,
                w,
                h,
            )

        log.debug(
            "panel geo: (%d, %d) %dx%d on screen %dx%d",
            self._geo.x(), self._geo.y(),
            self._geo.width(), self._geo.height(),
            screen.width(), screen.height(),
        )

    def show_slide(self) -> None:
        self.setGeometry(self._geo)
        log.debug("showing panel at (%d, %d)", self._geo.x(), self._geo.y())
        self.show()
        self.raise_()
        self.activateWindow()

    def hide_slide(self) -> None:
        log.debug("hiding panel")
        self.hide()


class SystrayApp:
    def __init__(self, config: Config) -> None:
        self.config = config

        platform = os.environ.get("XDG_SESSION_TYPE", "unknown")
        log.info("session type: %s", platform)
        log.info("Qt platform: %s", QApplication.platformName())

        self.app = QApplication(sys.argv)
        self.app.setApplicationName("HA TV Tray")
        self.app.setOrganizationName("ha-tv-tray")

        self._setup_signal_handling()
        self._setup_tick_timer()

        self.panel = RemotePanel(config)
        self.tray = QSystemTrayIcon()
        self.tray.setIcon(self._make_icon())
        self.tray.setToolTip("TV Remote")
        self.tray.activated.connect(self._on_tray_activated)

        self._tray_menu = QMenu()
        help_act = self._tray_menu.addAction("Show/Hide Remote")
        help_act.triggered.connect(self._toggle_panel)
        self._tray_menu.addSeparator()
        quit_act = self._tray_menu.addAction("Quit")
        quit_act.triggered.connect(self._quit)
        self.tray.setContextMenu(self._tray_menu)

        # Wait for event loop before showing tray
        QTimer.singleShot(0, self._init_tray)

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

    def _init_tray(self) -> None:
        self.tray.show()
        log.info("tray icon shown")
        if not self.tray.isVisible():
            log.warning("tray icon is NOT visible on attempt")

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
        name = _REASON_NAMES.get(reason, f"UNKNOWN({reason})")
        log.debug("tray activated: %s", name)

        if reason == QSystemTrayIcon.Context:
            self._tray_menu.exec(self.tray.geometry().center())
        elif reason in (
            QSystemTrayIcon.Trigger,
            QSystemTrayIcon.DoubleClick,
            QSystemTrayIcon.Unknown,
        ):
            self._toggle_panel()

    def _toggle_panel(self) -> None:
        log.debug("toggle panel (visible=%s)", self.panel.isVisible())
        if self.panel.isVisible():
            self.panel.hide_slide()
        else:
            self.panel.show_slide()

    def _quit(self) -> None:
        log.info("quitting")
        self.panel.close()
        self._tick_timer.stop()
        QTimer.singleShot(0, self.app.quit)

    def run(self) -> int:
        return self.app.exec()
