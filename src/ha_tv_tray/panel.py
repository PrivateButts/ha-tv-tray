import json
import logging
import os
import signal
import sys

from PySide6.QtCore import (
    QEvent,
    QObject,
    QPropertyAnimation,
    QPoint,
    QRect,
    QTimer,
    QUrl,
    Qt,
)
from PySide6.QtGui import QIcon, QPixmap, QCursor
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
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


class ClickCatcher(QObject):
    def __init__(self, panel: "RemotePanel") -> None:
        super().__init__(panel)
        self.panel = panel

    def eventFilter(self, obj, event) -> bool:
        if (
            self.panel.isVisible()
            and event.type() == QEvent.MouseButtonPress
        ):
            pos = event.globalPosition().toPoint()
            if not self.panel.geometry().contains(pos):
                log.debug("click outside panel, hiding")
                self.panel.hide_slide()
        return False


class RemotePanel(QWidget):
    def __init__(self, config: Config) -> None:
        super().__init__()
        self.config = config
        self._fading = False

        self.setWindowTitle("TV Remote")
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_DeleteOnClose, False)

        self.setStyleSheet(
            "RemotePanel { background: palette(window); "
            "border: 1px solid palette(mid); }"
        )

        self._setup_webview()
        self._setup_ui()

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
        # Load URL deferred — avoids SIGTRAP during init on some GPU configs
        self._load_url = f"{self.config.ha_url}{self.config.dashboard_path}"
        QTimer.singleShot(0, self._do_load)

    def _do_load(self) -> None:
        log.info("loading HA dashboard: %s", self._load_url)
        self.webview.page().loadFinished.connect(self._on_page_loaded)
        self.webview.load(QUrl(self._load_url))

    def _on_page_loaded(self, ok: bool) -> None:
        log.info("page loaded: ok=%s", ok)

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

    def content_size(self) -> tuple:
        return self.config.panel_width, self.config.panel_height

    def show_slide(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()
        self._fade_in()

    def position_near(self, pos: QPoint) -> None:
        w, h = self.content_size()
        margin = 8
        screen = QApplication.primaryScreen().availableGeometry()

        near_right = pos.x() > screen.width() // 2
        near_bottom = pos.y() > screen.height() // 2

        x = screen.right() - w - margin if near_right else margin
        y = screen.bottom() - h - margin if near_bottom else 26

        log.debug("position near (%d,%d) → (%d,%d)", pos.x(), pos.y(), x, y)
        self.setGeometry(QRect(x, y, w, h))
        wh = self.windowHandle()
        if wh is not None:
            wh.setPosition(QPoint(x, y))

    def position_default(self) -> None:
        w, h = self.content_size()
        margin = 8
        screen = QApplication.primaryScreen().availableGeometry()
        if self.config.position == "top-right":
            self.setGeometry(QRect(screen.right() - w - margin, 26, w, h))
        else:
            self.setGeometry(
                QRect(screen.right() - w - margin, screen.bottom() - h - margin, w, h)
            )

    def hide_slide(self) -> None:
        log.debug("hiding panel")
        self.hide()

    def _fade_in(self) -> None:
        if self._fading:
            return
        self._fading = True
        self.setWindowOpacity(0.0)
        anim = QPropertyAnimation(self, b"windowOpacity")
        anim.setDuration(150)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.finished.connect(lambda: setattr(self, "_fading", False))
        anim.start()


# ---------------------------------------------------------------------------
# SystrayApp
# ---------------------------------------------------------------------------


class SystrayApp:
    def __init__(self, config: Config, browser_mode: bool = False) -> None:
        self.config = config
        self._browser_mode = browser_mode

        log.info("session type: %s", os.environ.get("XDG_SESSION_TYPE", "unknown"))
        log.info("Qt platform: %s", QApplication.platformName())

        self.app = QApplication(sys.argv)
        self.app.setApplicationName("HA TV Tray")
        self.app.setOrganizationName("ha-tv-tray")

        self._setup_signal_handling()
        self._setup_tick_timer()

        # Tray and menu first (no WebEngine involved)
        self._tray_menu = QMenu()
        show_act = self._tray_menu.addAction("Show/Hide Remote")
        show_act.triggered.connect(self._toggle_panel)
        self._tray_menu.addSeparator()
        quit_act = self._tray_menu.addAction("Quit")
        quit_act.triggered.connect(self._quit)

        self._panel_ready = False
        self.panel = None
        self._click_catcher = None

        self._init_tray()

        # Defer WebEngine init — GPU process may fail before event loop
        QTimer.singleShot(0, lambda: self._init_panel(config))

    def _init_tray(self) -> None:
        self.tray = QSystemTrayIcon()
        self.tray.setIcon(self._make_icon())
        self.tray.setToolTip("TV Remote")
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.setContextMenu(self._tray_menu)
        QTimer.singleShot(0, self.tray.show)
        log.info("tray icon shown")

    def _init_panel(self, config) -> None:
        if self._browser_mode:
            log.info("browser mode — no panel needed")
            self._panel_ready = True
            return
        log.info("initializing panel (deferred)")
        self.panel = RemotePanel(config)
        self._click_catcher = ClickCatcher(self.panel)
        self.app.installEventFilter(self._click_catcher)
        self._panel_ready = True
        log.info("panel ready")

    def _on_tray_activated(self, reason: int) -> None:
        log.debug("tray activated: reason=%s", reason.name if hasattr(reason, "name") else reason)
        if not self._panel_ready:
            log.debug("panel not ready yet, ignoring")
            return
        if reason == QSystemTrayIcon.Context:
            self._tray_menu.exec(QCursor.pos())
        elif reason in (
            QSystemTrayIcon.Trigger,
            QSystemTrayIcon.DoubleClick,
            QSystemTrayIcon.Unknown,
        ):
            self._toggle_panel()

    # -- shared -------------------------------------------------------------

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

    def _toggle_panel(self) -> None:
        if self._browser_mode:
            import webbrowser
            url = f"{self.config.ha_url}{self.config.dashboard_path}"
            log.info("opening browser: %s", url)
            webbrowser.open(url)
            return
        if not self._panel_ready or self.panel is None:
            return
        log.debug("toggle panel")
        if self.panel.isVisible():
            self.panel.hide_slide()
        else:
            cursor = QCursor.pos()
            if cursor.x() != 0 or cursor.y() != 0:
                self.panel.position_near(cursor)
            else:
                self.panel.position_default()
            self.panel.show_slide()

    def _quit(self) -> None:
        log.info("quitting")
        if self.panel is not None:
            self.panel.close()
        self._tick_timer.stop()
        QTimer.singleShot(0, self.app.quit)

    def run(self) -> int:
        return self.app.exec()
