"""
octoMoA 桌面入口 — PySide6 窗口 + 后台 FastAPI 服务。
双击 exe 直接弹出管理窗口，服务在后台静默启动。
支持系统托盘：最小化到托盘，双击托盘图标恢复窗口。
"""

import sys
import os
import threading
import socket

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _get_log_dir() -> str:
    if os.name == "nt":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
        d = os.path.join(base, "octoMoA")
    else:
        d = os.path.expanduser("~/.octomoa")
    os.makedirs(d, exist_ok=True)
    return d


def _is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0


def _run_server():
    """服务器线程入口 — 用 asyncio.run + server.serve() 避免 sys.exit()"""
    if _is_port_in_use(18990):
        return

    try:
        import asyncio
        import uvicorn
        from app.main import app

        config = uvicorn.Config(app, host="127.0.0.1", port=18990, log_level="warning")
        server = uvicorn.Server(config)
        asyncio.run(server.serve())
    except (OSError, SystemExit, KeyboardInterrupt):
        pass
    except Exception as e:
        import traceback
        log_path = os.path.join(_get_log_dir(), 'server_crash.log')
        try:
            with open(log_path, 'w', encoding='utf-8') as f:
                f.write(f"{type(e).__name__}: {e}\n")
                f.write(traceback.format_exc())
        except:
            pass


def run_desktop():
    try:
        _run_desktop_inner()
    except Exception as e:
        import traceback
        log_path = os.path.join(_get_log_dir(), 'crash.log')
        try:
            with open(log_path, 'w', encoding='utf-8') as f:
                f.write(traceback.format_exc())
        except:
            pass


def _run_desktop_inner():
    # PyInstaller windowed 模式下 stdout/stderr 为 None
    if sys.stdout is None:
        sys.stdout = open(os.devnull, 'w', encoding='utf-8')
    if sys.stderr is None:
        sys.stderr = open(os.devnull, 'w', encoding='utf-8')

    from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
    from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QPen, QPainterPath
    from PySide6.QtCore import Qt

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    def create_icon():
        pixmap = QPixmap(64, 64)
        pixmap.fill(QColor(0, 0, 0, 0))
        p = QPainter(pixmap)
        p.setRenderHint(QPainter.Antialiasing)
        body = QColor("#6c5ce7")
        p.setBrush(body)
        p.setPen(Qt.NoPen)
        p.drawEllipse(14, 6, 36, 32)
        for x1, y1, x2, y2 in [(20,36,10,54),(24,38,16,56),(28,38,22,58),(32,38,28,58),(36,38,34,58),(40,38,40,56),(44,36,48,54),(48,34,54,50)]:
            p.setPen(QPen(body, 3, Qt.SolidLine, Qt.RoundCap))
            path = QPainterPath()
            path.moveTo(x1, y1)
            path.quadTo((x1+x2)/2+(x2-x1)*0.3, (y1+y2)/2, x2, y2)
            p.drawPath(path)
        p.setBrush(QColor("white"))
        p.setPen(Qt.NoPen)
        p.drawEllipse(21, 14, 9, 10)
        p.drawEllipse(34, 14, 9, 10)
        p.setBrush(QColor("#2d3436"))
        p.drawEllipse(24, 17, 5, 6)
        p.drawEllipse(37, 17, 5, 6)
        p.setBrush(QColor("white"))
        p.drawEllipse(25, 18, 2, 2)
        p.drawEllipse(38, 18, 2, 2)
        p.end()
        return QIcon(pixmap)

    # 先启动服务器线程（daemon，进程退出自动清理）
    server_thread = threading.Thread(target=_run_server, daemon=True)
    server_thread.start()

    # 再创建 GUI
    from app.desktop_ui import MainWindow
    window = MainWindow()

    tray_icon = QSystemTrayIcon(create_icon())
    tray_icon.setToolTip("octoMoA — 多模型聚合代理\nhttp://127.0.0.1:18990")

    tray_menu = QMenu()
    show_action = tray_menu.addAction("显示主窗口")
    show_action.triggered.connect(lambda: (window.show(), window.activateWindow()))
    tray_menu.addSeparator()
    quit_action = tray_menu.addAction("退出")
    quit_action.triggered.connect(lambda: (tray_icon.hide(), app.quit()))
    tray_icon.setContextMenu(tray_menu)

    def on_tray_activated(reason):
        if reason == QSystemTrayIcon.DoubleClick:
            window.show()
            window.activateWindow()

    tray_icon.activated.connect(on_tray_activated)
    tray_icon.show()

    def on_close(event):
        event.ignore()
        window.hide()
        tray_icon.showMessage("octoMoA", "已最小化到系统托盘", QSystemTrayIcon.Information, 2000)

    window.closeEvent = on_close
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run_desktop()
