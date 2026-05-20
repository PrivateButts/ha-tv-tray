import json
import sys

from PySide6.QtCore import (
    QPropertyAnimation,
    QEasingCurve,
    QRect,
    QUrl,
    Qt,
)
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
        self._animating = False

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
        self.webview.load(
            QUrl(f"{self.config.ha_url}{self.config.dashboard_path}")
        )

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
            top = 26
            self._target = QRect(screen.right() - w - margin, top, w, h)
            self._start = QRect(screen.right() - w - margin, top, w, 0)
        else:
            self._target = QRect(
                screen.right() - w - margin,
                screen.bottom() - h - margin,
                w,
                h,
            )
            self._start = QRect(
                screen.right() - w - margin,
                screen.bottom() - margin,
                w,
                0,
            )
        self.setGeometry(self._target)

    def show_slide(self) -> None:
        self.setGeometry(self._start)
        self.show()
        self.raise_()
        self.activateWindow()

        self._animate(self._start, self._target, hide_on_finish=False)

    def hide_slide(self) -> None:
        close = QRect(
            self._target.x(),
            self._target.y(),
            self._target.width(),
            0,
        )
        self._animate(
            self._target, close, hide_on_finish=True, duration_factor=0.5
        )

    def _animate(
        self,
        start: QRect,
        end: QRect,
        hide_on_finish: bool = False,
        duration_factor: float = 1.0,
    ) -> None:
        if self._animating:
            return
        self._animating = True

        anim = QPropertyAnimation(self, b"geometry")
        anim.setDuration(int(self.config.slide_duration_ms * duration_factor))
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.setEasingCurve(
            QEasingCurve.OutCubic if not hide_on_finish else QEasingCurve.InCubic
        )

        if hide_on_finish:
            anim.finished.connect(self.hide)

        anim.finished.connect(self._on_anim_done)
        anim.start()

    def _on_anim_done(self) -> None:
        self._animating = False


class SystrayApp:
    def __init__(self, config: Config) -> None:
        self.config = config

        self.app = QApplication(sys.argv)
        self.app.setApplicationName("HA TV Tray")
        self.app.setOrganizationName("ha-tv-tray")

        self.panel = RemotePanel(config)
        self.tray = QSystemTrayIcon()
        self.tray.setIcon(self._make_icon())
        self.tray.setToolTip("TV Remote")
        self.tray.activated.connect(self._on_tray_activated)

        menu = QMenu()
        show_act = menu.addAction("Show/Hide Remote")
        show_act.triggered.connect(self._toggle_panel)
        menu.addSeparator()
        quit_act = menu.addAction("Quit")
        quit_act.triggered.connect(self._quit)
        self.tray.setContextMenu(menu)

        self.tray.show()

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
        if reason == QSystemTrayIcon.Trigger:
            self._toggle_panel()
        elif reason == QSystemTrayIcon.Context:
            menu = self.tray.contextMenu()
            if menu:
                menu.exec(self.tray.geometry().center())

    def _toggle_panel(self) -> None:
        if self.panel._animating:
            return
        if self.panel.isVisible():
            self.panel.hide_slide()
        else:
            self.panel.show_slide()

    def _quit(self) -> None:
        self.panel.close()
        self.app.quit()

    def run(self) -> int:
        return self.app.exec()
