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
from PySide6.QtGui import (
    QIcon,
    QPainter,
    QColor,
    QPixmap,
    QPainterPath,
)
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

CORNER_RADIUS = 8
SHADOW_MARGIN = 14


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
        self.setAttribute(Qt.WA_TranslucentBackground)

        self._setup_webview()
        self._setup_ui()

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
        if hasattr(page, "backgroundColor"):
            page.setBackgroundColor(QColor(0, 0, 0, 0))
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
        m = SHADOW_MARGIN
        self._inner = QWidget(self)
        self._inner.setObjectName("popup-body")
        self._inner.setStyleSheet(
            f"""
            #popup-body {{
                background: palette(window);
                border: 1px solid palette(mid);
                border-radius: {CORNER_RADIUS}px;
            }}
            """
        )
        self._inner.setGeometry(
            m, m,
            self.config.panel_width,
            self.config.panel_height,
        )

        layout = QVBoxLayout(self._inner)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.webview)

    def _content_rect(self) -> QRect:
        m = SHADOW_MARGIN
        return QRect(m, m, self.config.panel_width, self.config.panel_height)

    def paintEvent(self, event) -> None:
        base = self.rect().adjusted(4, 4, -4, -4)
        path = QPainterPath()
        path.addRoundedRect(base, CORNER_RADIUS + 2, CORNER_RADIUS + 2)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        for i in range(10, 0, -1):
            c = QColor(0, 0, 0, 8 + i * 2)
            painter.setBrush(c)
            d = i * 2
            painter.drawRoundedRect(
                base.adjusted(-d, -d, d, d),
                CORNER_RADIUS + 2,
                CORNER_RADIUS + 2,
            )
        painter.end()

    def show_slide(self) -> None:
        self._position_and_show()
        self._fade_in()

    def hide_slide(self) -> None:
        log.debug("hiding panel")
        self.hide()

    def _position_and_show(self) -> None:
        cr = self._content_rect()
        total_w = cr.width() + SHADOW_MARGIN * 2
        total_h = cr.height() + SHADOW_MARGIN * 2

        screen = QApplication.primaryScreen().availableGeometry()
        margin = 8

        if self.config.position == "top-right":
            x = screen.right() - total_w - margin
            y = 26
        else:
            x = screen.right() - total_w - margin
            y = screen.bottom() - total_h - margin

        self.setGeometry(QRect(x, y, total_w, total_h))
        log.debug("showing panel at (%d, %d) %dx%d", x, y, total_w, total_h)
        self.show()
        self.raise_()
        self.activateWindow()

        # On Wayland, KWin may override position; try window handle
        wh = self.windowHandle()
        if wh is not None:
            wh.setPosition(QPoint(x, y))

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

        self._click_catcher = ClickCatcher(self.panel)
        self.app.installEventFilter(self._click_catcher)

        self.tray = QSystemTrayIcon()
        self.tray.setIcon(self._make_icon())
        self.tray.setToolTip("TV Remote")
        self.tray.activated.connect(self._on_tray_activated)

        self._tray_menu = QMenu()
        show_act = self._tray_menu.addAction("Show/Hide Remote")
        show_act.triggered.connect(self._toggle_panel)
        self._tray_menu.addSeparator()
        quit_act = self._tray_menu.addAction("Quit")
        quit_act.triggered.connect(self._quit)
        self.tray.setContextMenu(self._tray_menu)

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
        log.debug("tray activated: reason=%d", reason)
        if reason == QSystemTrayIcon.Context:
            self._tray_menu.exec(self.tray.geometry().center())
        elif reason in (
            QSystemTrayIcon.Trigger,
            QSystemTrayIcon.DoubleClick,
            QSystemTrayIcon.Unknown,
        ):
            self._toggle_panel()

    def _toggle_panel(self) -> None:
        log.debug("toggle panel")
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
