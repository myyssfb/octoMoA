"""
octoMoA 桌面窗口 — 与 Web 版一致的深色侧边栏 + 卡片式布局。
四个 Tab: 仪表盘 | 端点管理 | 编排配置 | 模型评测
"""

import json
import httpx
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QLineEdit, QTextEdit, QComboBox,
    QTableWidget, QTableWidgetItem, QGroupBox, QFormLayout,
    QDoubleSpinBox, QSpinBox, QMessageBox, QHeaderView, QApplication,
    QSizePolicy, QStackedWidget, QFrame, QScrollArea,
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QSize
from PySide6.QtGui import QFont, QColor, QIcon, QPainter, QPixmap

API = "http://127.0.0.1:18990"

# ── 颜色常量（对齐 Web 版 CSS 变量）──
C_SIDEBAR = "#1a1a2e"
C_SIDEBAR_ACTIVE = "#4f46e5"
C_SIDEBAR_TEXT = "#a0a0b0"
C_BG = "#f0f2f5"
C_CARD = "#ffffff"
C_BORDER = "#e8e8e8"
C_PRIMARY = "#4f46e5"
C_PRIMARY_HOVER = "#6366f1"
C_PRIMARY_LIGHT = "#eef2ff"
C_SUCCESS = "#10b981"
C_DANGER = "#ef4444"
C_TEXT = "#1f2937"
C_TEXT_SEC = "#6b7280"
C_TEXT_MUTED = "#9ca3af"


class Worker(QThread):
    result = Signal(bool, object)
    run_finished = Signal()

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def run(self):
        try:
            result = self.fn()
            self.result.emit(True, result)
        except Exception as e:
            self.result.emit(False, str(e))
        finally:
            self.run_finished.emit()


# 旧 Worker 保活列表 — 防止 QThread 在 OS 线程运行中被 GC 回收
_worker_registry: list[Worker] = []


def safe_set_worker(container, attr_name, new_worker):
    """安全替换 Worker：断开旧线程信号，保活直到线程结束"""
    old = getattr(container, attr_name, None)
    if old is not None:
        try:
            old.result.disconnect()
        except:
            pass
        _worker_registry.append(old)
        def _cleanup(w=old):
            try:
                _worker_registry.remove(w)
            except ValueError:
                pass
        old.run_finished.connect(_cleanup)

    new_worker.run_finished.connect(lambda w=new_worker: (
        _worker_registry.remove(w) if w in _worker_registry else None
    ))
    setattr(container, attr_name, new_worker)


def _request(method, path, data=None):
    try:
        r = httpx.request(method, f"{API}{path}", json=data, timeout=10)
        r.raise_for_status()
        return r.json()
    except httpx.ConnectError:
        raise Exception("无法连接到服务，请确认服务已启动")
    except httpx.TimeoutException:
        raise Exception("请求超时")
    except httpx.HTTPStatusError as e:
        raise Exception(f"HTTP {e.response.status_code}: {e.response.text[:200]}")
    except Exception as e:
        raise Exception(f"请求失败: {e}")


# ═══════════════════════════════════════════
#  通用组件
# ═══════════════════════════════════════════

def make_stat_card(label_text, value_text="--"):
    """创建统计卡片（对标 Web 版 .stat-card）"""
    frame = QFrame()
    frame.setStyleSheet(f"""
        QFrame {{
            background: {C_CARD};
            border: 1px solid {C_BORDER};
            border-radius: 10px;
            padding: 0px;
        }}
    """)
    frame.setFixedHeight(90)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(18, 14, 18, 14)
    lbl = QLabel(label_text)
    lbl.setStyleSheet(f"font-size:12px; color:{C_TEXT_MUTED}; font-weight:500; border:none;")
    val = QLabel(value_text)
    val.setStyleSheet(f"font-size:26px; font-weight:700; color:{C_TEXT}; border:none;")
    layout.addWidget(lbl)
    layout.addWidget(val)
    return frame, val


def make_card(title, parent_layout):
    """创建白色卡片容器，返回内部 layout"""
    frame = QFrame()
    frame.setStyleSheet(f"""
        QFrame {{
            background: {C_CARD};
            border: 1px solid {C_BORDER};
            border-radius: 10px;
        }}
    """)
    outer = QVBoxLayout(frame)
    outer.setContentsMargins(20, 20, 20, 20)
    outer.setSpacing(12)
    lbl = QLabel(title)
    lbl.setStyleSheet(f"font-size:13px; font-weight:600; color:{C_TEXT_SEC}; text-transform:uppercase; letter-spacing:0.5px; border:none;")
    outer.addWidget(lbl)
    parent_layout.addWidget(frame)
    return outer


def make_btn(text, color=C_PRIMARY, hover=C_PRIMARY_HOVER):
    btn = QPushButton(text)
    btn.setCursor(Qt.PointingHandCursor)
    btn.setStyleSheet(f"""
        QPushButton {{
            background: {color}; color: white; border: none;
            border-radius: 6px; padding: 7px 16px;
            font-size: 13px; font-weight: 500;
        }}
        QPushButton:hover {{ background: {hover}; }}
        QPushButton:disabled {{ background: #dfe6e9; color: #b2bec3; }}
    """)
    return btn


def make_ghost_btn(text):
    btn = QPushButton(text)
    btn.setCursor(Qt.PointingHandCursor)
    btn.setStyleSheet(f"""
        QPushButton {{
            background: transparent; color: {C_TEXT_SEC};
            border: 1px solid {C_BORDER}; border-radius: 6px;
            padding: 7px 16px; font-size: 13px; font-weight: 500;
        }}
        QPushButton:hover {{ background: #f9fafb; }}
    """)
    return btn


# ═══════════════════════════════════════════
#  Tab 1: 仪表盘
# ═══════════════════════════════════════════

class DashboardTab(QWidget):
    def __init__(self):
        super().__init__()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        inner = QWidget()
        inner.setStyleSheet(f"background:{C_BG};")
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # 统计卡片行
        stats_row = QHBoxLayout()
        stats_row.setSpacing(16)
        self.card_total, self.val_total = make_stat_card("总请求")
        self.card_ok, self.val_ok = make_stat_card("成功请求")
        self.card_latency, self.val_latency = make_stat_card("平均延迟")
        self.card_token, self.val_token = make_stat_card("总 Token")
        for c in [self.card_total, self.card_ok, self.card_latency, self.card_token]:
            stats_row.addWidget(c)
        layout.addLayout(stats_row)

        # 最近请求表格
        card_layout = make_card("最近请求", layout)
        self.req_table = QTableWidget(0, 5)
        self.req_table.setHorizontalHeaderLabels(["时间", "策略", "模型", "延迟", "状态"])
        self.req_table.horizontalHeader().setStretchLastSection(True)
        self.req_table.verticalHeader().setVisible(False)
        self.req_table.setStyleSheet(self._table_style())
        self.req_table.setSelectionBehavior(QTableWidget.SelectRows)
        card_layout.addWidget(self.req_table)

        layout.addStretch()
        scroll.setWidget(inner)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        QTimer.singleShot(0, self.refresh)

    def _table_style(self):
        return f"""
            QTableWidget {{
                background: {C_CARD}; color: {C_TEXT};
                gridline-color: #f0f0f0; border: none;
                selection-background-color: {C_PRIMARY_LIGHT};
            }}
            QTableWidget::item {{ padding: 8px 14px; font-size:13px; }}
            QHeaderView::section {{
                background: #fafafa; color: {C_TEXT_MUTED}; padding: 10px 14px;
                border: none; border-bottom: 1px solid {C_BORDER};
                font-weight:600; font-size:11px; text-transform:uppercase;
            }}
        """

    def refresh(self):
        safe_set_worker(self, 'worker', Worker(self._load))
        self.worker.result.connect(self._on_loaded)
        self.worker.start()

    def _load(self):
        stats = _request("GET", "/admin/api/stats")
        reqs = _request("GET", "/admin/api/requests?limit=15")
        try:
            tokens = _request("GET", "/admin/api/token-stats")
        except Exception:
            tokens = {"grand_total": 0}
        return stats, reqs, tokens

    def _on_loaded(self, ok, data):
        if not ok:
            self.val_total.setText("离线")
            self.val_total.setStyleSheet(f"font-size:26px;font-weight:700;color:{C_DANGER};border:none;")
            return
        stats, reqs, tokens = data
        self.val_total.setText(str(stats["total_requests"]))
        self.val_ok.setText(str(stats["ok_requests"]))
        self.val_latency.setText(f"{stats['avg_latency_ms']}ms")
        self.val_token.setText(f"{tokens.get('grand_total', 0):,}")

        self.req_table.setRowCount(len(reqs))
        for i, r in enumerate(reqs):
            self.req_table.setItem(i, 0, QTableWidgetItem(r.get("created_at", "")[-8:]))
            self.req_table.setItem(i, 1, QTableWidgetItem(r.get("strategy", "")))
            self.req_table.setItem(i, 2, QTableWidgetItem(r.get("model_name", "")))
            self.req_table.setItem(i, 3, QTableWidgetItem(f"{r.get('elapsed_ms', 0)}ms"))
            status = r.get("status", "")
            item = QTableWidgetItem("成功" if status == "ok" else "失败")
            item.setForeground(QColor(C_SUCCESS if status == "ok" else C_DANGER))
            self.req_table.setItem(i, 4, item)


# ═══════════════════════════════════════════
#  Tab 2: 端点管理
# ═══════════════════════════════════════════

class EndpointsTab(QWidget):
    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        lbl = QLabel("端点管理 - 加载中...")
        lbl.setStyleSheet(f"font-size:14px;color:{C_TEXT};")
        outer.addWidget(lbl)
        self._init_full()

    def _init_full(self):
        # 清除临时内容
        while self.layout().count():
            item = self.layout().takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        inner = QWidget()
        inner.setStyleSheet(f"background:{C_BG};")
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # 表单卡片
        form_layout = make_card("添加 / 编辑端点", layout)
        form = QFormLayout()
        form.setSpacing(10)

        def make_input(placeholder=""):
            w = QLineEdit()
            w.setPlaceholderText(placeholder)
            w.setStyleSheet(f"""
                QLineEdit {{
                    background:white; color:{C_TEXT}; border:1px solid {C_BORDER};
                    border-radius:6px; padding:8px 12px; font-size:13px;
                }}
                QLineEdit:focus {{ border:1px solid {C_PRIMARY}; }}
            """)
            return w

        lbl_style = f"font-size:12px;font-weight:600;color:{C_TEXT_SEC};border:none;"

        self.ep_name = make_input("deepseek-chat")
        l = QLabel("名称"); l.setStyleSheet(lbl_style)
        form.addRow(l, self.ep_name)

        self.ep_type = QComboBox()
        self.ep_type.addItems(["openai", "anthropic"])
        self.ep_type.setStyleSheet(f"""
            QComboBox {{
                background:white; color:{C_TEXT}; border:1px solid {C_BORDER};
                border-radius:6px; padding:8px 12px; font-size:13px;
            }}
        """)
        l = QLabel("类型"); l.setStyleSheet(lbl_style)
        form.addRow(l, self.ep_type)

        self.ep_url = make_input("https://api.deepseek.com/v1")
        l = QLabel("Base URL"); l.setStyleSheet(lbl_style)
        form.addRow(l, self.ep_url)

        self.ep_key = make_input("sk-...")
        self.ep_key.setEchoMode(QLineEdit.Password)
        l = QLabel("API Key"); l.setStyleSheet(lbl_style)
        form.addRow(l, self.ep_key)

        self.ep_model = make_input("点击「获取模型」自动填充")
        l = QLabel("Model"); l.setStyleSheet(lbl_style)
        form.addRow(l, self.ep_model)

        form_layout.addLayout(form)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self.fetch_btn = make_btn("获取模型", C_SUCCESS, "#059669")
        self.test_btn = make_ghost_btn("测试连通性")
        self.add_btn = make_btn("保存")
        self.del_btn = make_btn("删除", C_DANGER, "#dc2626")
        self.fetch_btn.clicked.connect(self.fetch_models)
        self.test_btn.clicked.connect(self.test_endpoint)
        self.add_btn.clicked.connect(self.add_endpoint)
        self.del_btn.clicked.connect(self.delete_endpoint)
        btn_row.addWidget(self.fetch_btn)
        btn_row.addWidget(self.test_btn)
        btn_row.addWidget(self.add_btn)
        btn_row.addWidget(self.del_btn)
        btn_row.addStretch()
        form_layout.addLayout(btn_row)

        # 表格卡片
        table_layout = make_card("已配置端点", layout)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["名称", "类型", "Base URL", "Model", "API Key"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.itemSelectionChanged.connect(self._on_select)
        self.table.setStyleSheet(f"""
            QTableWidget {{
                background: {C_CARD}; color: {C_TEXT};
                gridline-color: #f0f0f0; border: none;
                selection-background-color: {C_PRIMARY_LIGHT};
            }}
            QTableWidget::item {{ padding: 8px 14px; font-size:13px; }}
            QHeaderView::section {{
                background: #fafafa; color: {C_TEXT_MUTED}; padding: 10px 14px;
                border: none; border-bottom: 1px solid {C_BORDER};
                font-weight:600; font-size:11px; text-transform:uppercase;
            }}
        """)
        table_layout.addWidget(self.table)

        layout.addStretch()
        scroll.setWidget(inner)
        self.layout().addWidget(scroll)
        QTimer.singleShot(0, self.refresh)

    def refresh(self):
        safe_set_worker(self, 'worker', Worker(lambda: _request("GET", "/admin/api/endpoints")))
        self.worker.result.connect(self._on_loaded)
        self.worker.start()

    def _on_loaded(self, ok, data):
        if not ok:
            return
        self.table.setRowCount(len(data))
        for i, ep in enumerate(data):
            self.table.setItem(i, 0, QTableWidgetItem(ep["name"]))
            self.table.setItem(i, 1, QTableWidgetItem(ep["api_type"]))
            self.table.setItem(i, 2, QTableWidgetItem(ep["base_url"]))
            self.table.setItem(i, 3, QTableWidgetItem(ep["model"]))
            key = ep.get("api_key", "")
            self.table.setItem(i, 4, QTableWidgetItem(key[:8] + "..." if len(key) > 8 else key))

    def _on_select(self):
        rows = self.table.selectedIndexes()
        if not rows:
            return
        r = rows[0].row()
        self.ep_name.setText(self.table.item(r, 0).text())
        self.ep_type.setCurrentText(self.table.item(r, 1).text())
        self.ep_url.setText(self.table.item(r, 2).text())
        self.ep_model.setText(self.table.item(r, 3).text())
        self.ep_key.clear()

    def fetch_models(self):
        url = self.ep_url.text().strip()
        key = self.ep_key.text().strip()
        if not url:
            QMessageBox.warning(self, "提示", "请先填写 Base URL")
            return
        self.fetch_btn.setEnabled(False)
        self.fetch_btn.setText("获取中...")

        def _do():
            headers = {"Authorization": f"Bearer {key}"} if key else {}
            resp = httpx.get(f"{url}/models", headers=headers, timeout=15)
            resp.raise_for_status()
            return [m["id"] for m in resp.json().get("data", [])]

        safe_set_worker(self, 'worker', Worker(_do))
        self.worker.result.connect(self._on_fetch)
        self.worker.start()

    def _on_fetch(self, ok, data):
        self.fetch_btn.setEnabled(True)
        self.fetch_btn.setText("获取模型")
        if not ok:
            QMessageBox.warning(self, "获取失败", str(data))
            return
        if data:
            self.ep_model.setText(data[0])
            QMessageBox.information(self, "成功", f"获取到 {len(data)} 个模型，已选中: {data[0]}")

    def add_endpoint(self):
        model = self.ep_model.text().strip()
        if not model:
            QMessageBox.warning(self, "错误", "请选择或输入 Model")
            return
        data = {
            "name": self.ep_name.text().strip(),
            "api_type": self.ep_type.currentText(),
            "base_url": self.ep_url.text().strip(),
            "api_key": self.ep_key.text().strip(),
            "model": model,
        }
        if not all([data["name"], data["base_url"]]):
            QMessageBox.warning(self, "错误", "名称、Base URL 为必填项")
            return
        self.add_btn.setEnabled(False)
        self.add_btn.setText("保存中...")

        def _save():
            try:
                return True, _request("PUT", f"/admin/api/endpoints/{data['name']}", data)
            except Exception:
                return True, _request("POST", "/admin/api/endpoints", data)

        safe_set_worker(self, 'worker', Worker(_save))
        self.worker.result.connect(self._after_save)
        self.worker.start()

    def _after_save(self, ok, data):
        self.add_btn.setEnabled(True)
        self.add_btn.setText("保存")
        if ok:
            QMessageBox.information(self, "成功", "端点已保存")
            self.refresh()
            self.ep_key.clear()
            self.ep_model.clear()
        else:
            QMessageBox.warning(self, "失败", str(data))

    def delete_endpoint(self):
        rows = self.table.selectedIndexes()
        if not rows:
            return
        name = self.table.item(rows[0].row(), 0).text()
        reply = QMessageBox.question(self, "确认", f"删除端点 '{name}'?")
        if reply == QMessageBox.Yes:
            safe_set_worker(self, 'worker', Worker(lambda: _request("DELETE", f"/admin/api/endpoints/{name}")))
            self.worker.result.connect(lambda ok, d: (QMessageBox.information(self, "成功", "已删除"), self.refresh()) if ok else QMessageBox.warning(self, "失败", str(d)))
            self.worker.start()

    def test_endpoint(self):
        url = self.ep_url.text().strip()
        key = self.ep_key.text().strip()
        model = self.ep_model.text().strip()
        if not url:
            QMessageBox.warning(self, "提示", "请先填写 Base URL")
            return
        self.test_btn.setEnabled(False)
        self.test_btn.setText("测试中...")

        def _do():
            headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            payload = {"model": model or "gpt-3.5-turbo", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 5}
            import time
            t0 = time.perf_counter()
            resp = httpx.post(f"{url}/chat/completions", json=payload, headers=headers, timeout=15)
            elapsed = int((time.perf_counter() - t0) * 1000)
            return {"ok": resp.status_code == 200, "ms": elapsed}

        safe_set_worker(self, 'worker', Worker(_do))
        self.worker.result.connect(self._on_test)
        self.worker.start()

    def _on_test(self, ok, data):
        self.test_btn.setEnabled(True)
        self.test_btn.setText("测试连通性")
        if ok and data.get("ok"):
            QMessageBox.information(self, "成功", f"连接成功! 延迟: {data['ms']}ms")
        else:
            QMessageBox.warning(self, "失败", str(data))


# ═══════════════════════════════════════════
#  Tab 3: 编排配置
# ═══════════════════════════════════════════

class StrategyCard(QFrame):
    """可点击的策略卡片（对标 Web 版 .strategy-card）"""
    clicked = Signal(str)

    def __init__(self, name, desc, parent=None):
        super().__init__(parent)
        self.strategy_name = name
        self._selected = False
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(70)
        self._update_style()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        lbl_name = QLabel(name)
        lbl_name.setStyleSheet(f"font-size:14px;font-weight:600;color:{C_TEXT};border:none;")
        lbl_desc = QLabel(desc)
        lbl_desc.setStyleSheet(f"font-size:11px;color:{C_TEXT_MUTED};border:none;")
        layout.addWidget(lbl_name)
        layout.addWidget(lbl_desc)

    def set_selected(self, selected):
        self._selected = selected
        self._update_style()

    def _update_style(self):
        if self._selected:
            self.setStyleSheet(f"""
                QFrame {{
                    border: 2px solid {C_PRIMARY};
                    background: {C_PRIMARY_LIGHT};
                    border-radius: 8px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QFrame {{
                    border: 2px solid {C_BORDER};
                    background: white;
                    border-radius: 8px;
                }}
                QFrame:hover {{ border-color: {C_PRIMARY}; }}
            """)

    def mousePressEvent(self, event):
        self.clicked.emit(self.strategy_name)


class PresetItem(QFrame):
    """预设列表项（对标 Web 版 .preset-item）"""
    activate_clicked = Signal(int)
    delete_clicked = Signal(int)

    def __init__(self, preset_id, name, desc, is_active, parent=None):
        super().__init__(parent)
        self.preset_id = preset_id
        self.setCursor(Qt.PointingHandCursor)

        border_color = C_PRIMARY if is_active else C_BORDER
        bg = C_PRIMARY_LIGHT if is_active else "white"
        self.setStyleSheet(f"""
            QFrame {{
                border: 1px solid {border_color};
                background: {bg};
                border-radius: 8px;
            }}
            QFrame:hover {{ border-color: {C_PRIMARY}; }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)

        info_layout = QVBoxLayout()
        name_lbl = QLabel(name)
        name_lbl.setStyleSheet(f"font-size:14px;font-weight:600;color:{C_TEXT};border:none;")
        desc_lbl = QLabel(desc or "")
        desc_lbl.setStyleSheet(f"font-size:12px;color:{C_TEXT_MUTED};border:none;")
        info_layout.addWidget(name_lbl)
        if desc:
            info_layout.addWidget(desc_lbl)
        layout.addLayout(info_layout, 1)

        if is_active:
            badge = QLabel("当前")
            badge.setStyleSheet(f"""
                background:{C_PRIMARY}; color:white;
                font-size:10px; font-weight:600;
                padding:2px 8px; border-radius:4px; border:none;
            """)
            layout.addWidget(badge)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(6)
        if not is_active:
            act_btn = make_btn("应用", C_PRIMARY)
            act_btn.setFixedHeight(30)
            act_btn.clicked.connect(lambda: self.activate_clicked.emit(self.preset_id))
            btn_layout.addWidget(act_btn)
        del_btn = make_btn("删除", C_DANGER, "#dc2626")
        del_btn.setFixedHeight(30)
        del_btn.clicked.connect(lambda: self.delete_clicked.emit(self.preset_id))
        btn_layout.addWidget(del_btn)
        layout.addLayout(btn_layout)


class OrchestrationTab(QWidget):
    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        lbl = QLabel("编排配置 - 加载中...")
        lbl.setStyleSheet(f"font-size:14px;color:{C_TEXT};")
        outer.addWidget(lbl)
        QTimer.singleShot(0, self._init_full)

    def _init_full(self):
        while self.layout().count():
            item = self.layout().takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        inner = QWidget()
        inner.setStyleSheet(f"background:{C_BG};")
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # ── Proposers ──
        proposer_card = make_card("Proposers（多选）", layout)
        self.proposer_checks = []
        self.proposer_container = QVBoxLayout()
        proposer_card.addLayout(self.proposer_container)

        # ── Aggregator ──
        agg_card = make_card("Aggregator", layout)
        form = QGridLayout()
        form.setSpacing(12)
        l1 = QLabel("聚合模型")
        l1.setStyleSheet(f"font-size:12px;font-weight:600;color:{C_TEXT_SEC};border:none;")
        self.agg_combo = QComboBox()
        self.agg_combo.setStyleSheet(f"""
            QComboBox {{
                background:white; color:{C_TEXT}; border:1px solid {C_BORDER};
                border-radius:6px; padding:8px 12px; font-size:13px;
            }}
        """)
        form.addWidget(l1, 0, 0)
        form.addWidget(self.agg_combo, 0, 1)

        l2 = QLabel("System Prompt")
        l2.setStyleSheet(f"font-size:12px;font-weight:600;color:{C_TEXT_SEC};border:none;")
        self.agg_prompt = QTextEdit()
        self.agg_prompt.setMaximumHeight(80)
        self.agg_prompt.setPlaceholderText("System prompt for aggregator...")
        self.agg_prompt.setStyleSheet(f"""
            QTextEdit {{
                background:white; color:{C_TEXT}; border:1px solid {C_BORDER};
                border-radius:6px; padding:8px 12px; font-size:13px;
            }}
            QTextEdit:focus {{ border:1px solid {C_PRIMARY}; }}
        """)
        form.addWidget(l2, 1, 0)
        form.addWidget(self.agg_prompt, 1, 1)
        agg_card.addLayout(form)

        # ── 策略卡片 ──
        strat_card = make_card("MoA 策略", layout)
        strat_grid = QHBoxLayout()
        strat_grid.setSpacing(10)
        self.strategy_cards = {}
        strategies = [
            ("simple", "直接合并"), ("vote", "投票选优"),
            ("debate", "辩论改进"), ("cascade", "分层精炼"),
        ]
        for name, desc in strategies:
            card = StrategyCard(name, desc)
            card.clicked.connect(self._on_strategy_click)
            self.strategy_cards[name] = card
            strat_grid.addWidget(card)
        strat_card.addLayout(strat_grid)

        # ── 超时设置 ──
        timeout_card = make_card("超时设置", layout)
        tform = QGridLayout()
        tform.setSpacing(12)
        spin_style = f"""
            QSpinBox {{
                background:white; color:{C_TEXT}; border:1px solid {C_BORDER};
                border-radius:6px; padding:8px 12px; font-size:13px;
            }}
            QSpinBox:focus {{ border:1px solid {C_PRIMARY}; }}
        """
        l3 = QLabel("普通超时（秒）")
        l3.setStyleSheet(f"font-size:12px;font-weight:600;color:{C_TEXT_SEC};border:none;")
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(10, 600)
        self.timeout_spin.setValue(120)
        self.timeout_spin.setStyleSheet(spin_style)
        l4 = QLabel("流式超时（秒）")
        l4.setStyleSheet(f"font-size:12px;font-weight:600;color:{C_TEXT_SEC};border:none;")
        self.stream_timeout_spin = QSpinBox()
        self.stream_timeout_spin.setRange(30, 900)
        self.stream_timeout_spin.setValue(300)
        self.stream_timeout_spin.setStyleSheet(spin_style)
        tform.addWidget(l3, 0, 0)
        tform.addWidget(self.timeout_spin, 0, 1)
        tform.addWidget(l4, 1, 0)
        tform.addWidget(self.stream_timeout_spin, 1, 1)
        timeout_card.addLayout(tform)

        # ── 温度设置 ──
        temp_card = make_card("温度设置", layout)
        hint = QLabel("温度越高，回答越多样有创意；温度越低，回答越稳定保守。")
        hint.setStyleSheet(f"font-size:12px;color:{C_TEXT_MUTED};border:none;")
        temp_card.addWidget(hint)
        tform2 = QGridLayout()
        tform2.setSpacing(12)
        dspin_style = f"""
            QDoubleSpinBox {{
                background:white; color:{C_TEXT}; border:1px solid {C_BORDER};
                border-radius:6px; padding:8px 12px; font-size:13px;
            }}
            QDoubleSpinBox:focus {{ border:1px solid {C_PRIMARY}; }}
        """
        l5 = QLabel("提案者温度（参谋，建议 0.6-0.8）")
        l5.setStyleSheet(f"font-size:12px;font-weight:600;color:{C_TEXT_SEC};border:none;")
        self.proposer_temp = QDoubleSpinBox()
        self.proposer_temp.setRange(0, 2)
        self.proposer_temp.setSingleStep(0.1)
        self.proposer_temp.setValue(0.6)
        self.proposer_temp.setStyleSheet(dspin_style)
        l6 = QLabel("聚合器温度（主持人，建议 0.3-0.5）")
        l6.setStyleSheet(f"font-size:12px;font-weight:600;color:{C_TEXT_SEC};border:none;")
        self.agg_temp = QDoubleSpinBox()
        self.agg_temp.setRange(0, 2)
        self.agg_temp.setSingleStep(0.1)
        self.agg_temp.setValue(0.4)
        self.agg_temp.setStyleSheet(dspin_style)
        tform2.addWidget(l5, 0, 0)
        tform2.addWidget(self.proposer_temp, 0, 1)
        tform2.addWidget(l6, 1, 0)
        tform2.addWidget(self.agg_temp, 1, 1)
        temp_card.addLayout(tform2)

        # ── 保存按钮 ──
        self.save_btn = make_btn("  保存并应用")
        self.save_btn.setFixedHeight(40)
        self.save_btn.setStyleSheet(f"""
            QPushButton {{
                background:{C_PRIMARY}; color:white; border:none;
                border-radius:6px; padding:10px 24px;
                font-size:15px; font-weight:bold;
            }}
            QPushButton:hover {{ background:{C_PRIMARY_HOVER}; }}
            QPushButton:disabled {{ background:#dfe6e9; color:#b2bec3; }}
        """)
        self.save_btn.clicked.connect(self.save_config)
        layout.addWidget(self.save_btn)

        # ── 配置预设 ──
        preset_card = make_card("配置预设", layout)
        hint2 = QLabel("保存当前配置为预设，可快速切换不同的编排方案。")
        hint2.setStyleSheet(f"font-size:12px;color:{C_TEXT_MUTED};border:none;")
        preset_card.addWidget(hint2)

        pform = QHBoxLayout()
        pform.setSpacing(12)
        l7 = QLabel("预设名称")
        l7.setStyleSheet(f"font-size:12px;font-weight:600;color:{C_TEXT_SEC};border:none;")
        self.preset_name = QLineEdit()
        self.preset_name.setPlaceholderText("deepseek+mimo simple")
        self.preset_name.setStyleSheet(f"""
            QLineEdit {{
                background:white; color:{C_TEXT}; border:1px solid {C_BORDER};
                border-radius:6px; padding:8px 12px; font-size:13px;
            }}
            QLineEdit:focus {{ border:1px solid {C_PRIMARY}; }}
        """)
        l8 = QLabel("说明")
        l8.setStyleSheet(f"font-size:12px;font-weight:600;color:{C_TEXT_SEC};border:none;")
        self.preset_desc = QLineEdit()
        self.preset_desc.setPlaceholderText("日常问答用")
        self.preset_desc.setStyleSheet(f"""
            QLineEdit {{
                background:white; color:{C_TEXT}; border:1px solid {C_BORDER};
                border-radius:6px; padding:8px 12px; font-size:13px;
            }}
            QLineEdit:focus {{ border:1px solid {C_PRIMARY}; }}
        """)
        pform.addWidget(l7)
        pform.addWidget(self.preset_name, 1)
        pform.addWidget(l8)
        pform.addWidget(self.preset_desc, 1)
        preset_card.addLayout(pform)

        save_preset_btn = make_btn("保存当前配置", C_SUCCESS, "#059669")
        save_preset_btn.clicked.connect(self.save_preset)
        preset_card.addWidget(save_preset_btn)

        l9 = QLabel("已保存的预设")
        l9.setStyleSheet(f"font-size:13px;font-weight:600;color:{C_TEXT_SEC};margin-top:8px;border:none;")
        preset_card.addWidget(l9)
        self.preset_list_layout = QVBoxLayout()
        self.preset_list_layout.setSpacing(8)
        preset_card.addLayout(self.preset_list_layout)

        layout.addStretch()
        scroll.setWidget(inner)
        self.layout().addWidget(scroll)
        QTimer.singleShot(0, self.refresh)

    def _on_strategy_click(self, name):
        for n, card in self.strategy_cards.items():
            card.set_selected(n == name)

    def _clear_proposers(self):
        while self.proposer_container.count():
            item = self.proposer_container.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self.proposer_checks.clear()

    def _add_proposer_check(self, name, model, checked):
        frame = QFrame()
        border = C_PRIMARY if checked else C_BORDER
        bg = C_PRIMARY_LIGHT if checked else "white"
        frame.setStyleSheet(f"""
            QFrame {{
                border:1px solid {border}; background:{bg};
                border-radius:6px; padding:0px;
            }}
            QFrame:hover {{ border-color:{C_PRIMARY}; }}
        """)
        h = QHBoxLayout(frame)
        h.setContentsMargins(12, 10, 12, 10)
        cb_label = QLabel("  " + name)
        cb_label.setStyleSheet(f"font-size:13px;font-weight:500;color:{C_TEXT};border:none;")
        model_label = QLabel(model)
        model_label.setStyleSheet(f"font-size:12px;color:{C_TEXT_MUTED};border:none;")
        h.addWidget(cb_label)
        h.addStretch()
        h.addWidget(model_label)

        # 用属性存储状态
        frame._checked = checked
        frame._name = name
        frame.setCursor(Qt.PointingHandCursor)
        frame.mousePressEvent = lambda e, f=frame: self._toggle_proposer(f)
        self.proposer_container.addWidget(frame)
        self.proposer_checks.append(frame)

    def _toggle_proposer(self, frame):
        frame._checked = not frame._checked
        border = C_PRIMARY if frame._checked else C_BORDER
        bg = C_PRIMARY_LIGHT if frame._checked else "white"
        frame.setStyleSheet(f"""
            QFrame {{
                border:1px solid {border}; background:{bg};
                border-radius:6px; padding:0px;
            }}
            QFrame:hover {{ border-color:{C_PRIMARY}; }}
        """)

    def refresh(self):
        safe_set_worker(self, 'worker', Worker(lambda: _request("GET", "/admin/api/config")))
        self.worker.result.connect(self._on_loaded)
        self.worker.start()

    def _on_loaded(self, ok, data):
        if not ok:
            return
        avail = data.get("available_endpoints", [])

        # Proposers
        self._clear_proposers()
        enabled = {p["endpoint_name"] for p in data.get("proposers", [])}
        if not avail:
            lbl = QLabel("请先在「端点管理」中添加端点")
            lbl.setStyleSheet(f"color:{C_TEXT_MUTED};padding:20px;border:none;")
            self.proposer_container.addWidget(lbl)
        else:
            for ep in avail:
                self._add_proposer_check(ep["name"], ep["model"], ep["name"] in enabled)

        # Aggregator
        self.agg_combo.clear()
        for ep in avail:
            self.agg_combo.addItem(f"{ep['name']} ({ep['model']})", ep["name"])
        agg_ep = data.get("aggregator_endpoint", "")
        idx = self.agg_combo.findData(agg_ep)
        if idx >= 0:
            self.agg_combo.setCurrentIndex(idx)
        self.agg_prompt.setPlainText(data.get("aggregator_system_prompt", ""))

        # Strategy
        strat = data.get("strategy", "simple")
        for name, card in self.strategy_cards.items():
            card.set_selected(name == strat)

        # Timeout
        self.timeout_spin.setValue(data.get("timeout", 120))
        self.stream_timeout_spin.setValue(data.get("stream_timeout", 300))

        # Temperature
        self.proposer_temp.setValue(data.get("proposer_temperature", 0.6))
        self.agg_temp.setValue(data.get("aggregator_temperature", 0.4))

        # Presets
        self._load_presets()

    def _load_presets(self):
        safe_set_worker(self, 'worker2', Worker(lambda: _request("GET", "/admin/api/presets")))
        self.worker2.result.connect(self._on_presets)
        self.worker2.start()

    def _on_presets(self, ok, data):
        # 清空
        while self.preset_list_layout.count():
            item = self.preset_list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        if not ok or not data:
            lbl = QLabel("暂无预设")
            lbl.setStyleSheet(f"color:{C_TEXT_MUTED};padding:12px;border:none;")
            self.preset_list_layout.addWidget(lbl)
            return

        for p in data:
            item = PresetItem(p["id"], p["name"], p.get("description", ""), p.get("is_active", 0))
            item.activate_clicked.connect(self._activate_preset)
            item.delete_clicked.connect(self._delete_preset)
            self.preset_list_layout.addWidget(item)

    def save_config(self):
        proposers = []
        for frame in self.proposer_checks:
            if frame._checked:
                proposers.append({"endpoint": frame._name, "label": frame._name, "role": "strong"})

        if not proposers:
            QMessageBox.warning(self, "错误", "至少选择一个 Proposer")
            return

        agg = self.agg_combo.currentData()
        if not agg:
            QMessageBox.warning(self, "错误", "请选择 Aggregator")
            return

        strategy = "simple"
        for name, card in self.strategy_cards.items():
            if card._selected:
                strategy = name
                break

        data = {
            "proposers": proposers,
            "aggregator_endpoint": agg,
            "aggregator_system_prompt": self.agg_prompt.toPlainText(),
            "strategy": strategy,
            "timeout": self.timeout_spin.value(),
            "stream_timeout": self.stream_timeout_spin.value(),
            "proposer_temperature": self.proposer_temp.value(),
            "aggregator_temperature": self.agg_temp.value(),
        }

        self.save_btn.setEnabled(False)
        self.save_btn.setText("保存中...")
        safe_set_worker(self, 'worker', Worker(lambda: _request("PUT", "/admin/api/config", data)))
        self.worker.result.connect(self._on_saved)
        self.worker.start()

    def _on_saved(self, ok, data):
        self.save_btn.setEnabled(True)
        self.save_btn.setText("  保存并应用")
        if ok:
            QMessageBox.information(self, "成功", "配置已保存并生效")
        else:
            QMessageBox.warning(self, "失败", str(data))

    def save_preset(self):
        name = self.preset_name.text().strip()
        if not name:
            QMessageBox.warning(self, "错误", "请输入预设名称")
            return

        # 收集当前配置
        proposers = []
        for frame in self.proposer_checks:
            if frame._checked:
                proposers.append({"endpoint_name": frame._name, "label": frame._name, "role": "strong", "weight": 1.0, "sort_order": len(proposers)})

        strategy = "simple"
        for n, card in self.strategy_cards.items():
            if card._selected:
                strategy = n
                break

        config_json = {
            "proposers": proposers,
            "aggregator_endpoint": self.agg_combo.currentData() or "",
            "aggregator_system_prompt": self.agg_prompt.toPlainText(),
            "strategy": strategy,
            "timeout": self.timeout_spin.value(),
            "stream_timeout": self.stream_timeout_spin.value(),
            "proposer_temperature": self.proposer_temp.value(),
            "aggregator_temperature": self.agg_temp.value(),
        }

        payload = {
            "name": name,
            "description": self.preset_desc.text().strip(),
            "config_json": json.dumps(config_json, ensure_ascii=False),
        }

        self.save_btn.setEnabled(False)
        safe_set_worker(self, 'worker', Worker(lambda: _request("POST", "/admin/api/presets", payload)))
        self.worker.result.connect(lambda ok, d: self._on_preset_saved(ok, d, name))
        self.worker.start()

    def _on_preset_saved(self, ok, data, name):
        self.save_btn.setEnabled(True)
        if ok:
            QMessageBox.information(self, "成功", f"预设 '{name}' 已保存")
            self.preset_name.clear()
            self.preset_desc.clear()
            self._load_presets()
        else:
            QMessageBox.warning(self, "失败", str(data))

    def _activate_preset(self, preset_id):
        safe_set_worker(self, 'worker', Worker(lambda: _request("POST", f"/admin/api/presets/{preset_id}/activate")))
        self.worker.result.connect(lambda ok, d: (self.refresh(), QMessageBox.information(self, "成功", "预设已激活")) if ok else QMessageBox.warning(self, "失败", str(d)))
        self.worker.start()

    def _delete_preset(self, preset_id):
        reply = QMessageBox.question(self, "确认", "删除此预设?")
        if reply == QMessageBox.Yes:
            safe_set_worker(self, 'worker', Worker(lambda: _request("DELETE", f"/admin/api/presets/{preset_id}")))
            self.worker.result.connect(lambda ok, d: self._load_presets() if ok else QMessageBox.warning(self, "失败", str(d)))
            self.worker.start()


# ═══════════════════════════════════════════
#  Tab 4: 模型评测
# ═══════════════════════════════════════════

class BenchmarkTab(QWidget):
    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        lbl = QLabel("模型评测 - 加载中...")
        lbl.setStyleSheet(f"font-size:14px;color:{C_TEXT};")
        outer.addWidget(lbl)
        QTimer.singleShot(0, self._init_full)

    def _init_full(self):
        while self.layout().count():
            item = self.layout().takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        inner = QWidget()
        inner.setStyleSheet(f"background:{C_BG};")
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # 说明 + 开始按钮
        info_card = make_card("模型评测", layout)
        hint = QLabel("内置 5 道标准测试题，自动测试所有已配置的模型（单独 + MoA 组合），对比质量/延迟/Token 消耗。")
        hint.setStyleSheet(f"font-size:13px;color:{C_TEXT_SEC};border:none;")
        hint.setWordWrap(True)
        info_card.addWidget(hint)

        btn_row = QHBoxLayout()
        self.start_btn = make_btn("开始评测")
        self.start_btn.clicked.connect(self.start_benchmark)
        self.progress_label = QLabel("")
        self.progress_label.setStyleSheet(f"font-size:13px;color:{C_TEXT_MUTED};border:none;")
        btn_row.addWidget(self.start_btn)
        btn_row.addWidget(self.progress_label)
        btn_row.addStretch()
        info_card.addLayout(btn_row)

        # 排名表
        rank_card = make_card("综合排名", layout)
        self.ranking_table = QTableWidget(0, 5)
        self.ranking_table.setHorizontalHeaderLabels(["模型/组合", "类型", "平均得分", "平均延迟", "总 Token"])
        self.ranking_table.horizontalHeader().setStretchLastSection(True)
        self.ranking_table.verticalHeader().setVisible(False)
        self.ranking_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.ranking_table.setStyleSheet(self._table_style())
        rank_card.addWidget(self.ranking_table)

        # 详细结果
        detail_card = make_card("详细结果", layout)
        self.detail_table = QTableWidget(0, 6)
        self.detail_table.setHorizontalHeaderLabels(["模型", "题目", "得分", "延迟", "Token", "回答预览"])
        self.detail_table.horizontalHeader().setStretchLastSection(True)
        self.detail_table.verticalHeader().setVisible(False)
        self.detail_table.setStyleSheet(self._table_style())
        detail_card.addWidget(self.detail_table)

        # 应用推荐
        self.apply_btn = make_btn("应用推荐配置")
        self.apply_btn.setEnabled(False)
        self.apply_btn.clicked.connect(self.apply_recommendation)
        layout.addWidget(self.apply_btn)

        layout.addStretch()
        scroll.setWidget(inner)
        self.layout().addWidget(scroll)

        self.run_id = None
        self.timer = QTimer()
        self.timer.timeout.connect(self.poll_benchmark)

    def _table_style(self):
        return f"""
            QTableWidget {{
                background: {C_CARD}; color: {C_TEXT};
                gridline-color: #f0f0f0; border: none;
                selection-background-color: {C_PRIMARY_LIGHT};
            }}
            QTableWidget::item {{ padding: 8px 14px; font-size:13px; }}
            QHeaderView::section {{
                background: #fafafa; color: {C_TEXT_MUTED}; padding: 10px 14px;
                border: none; border-bottom: 1px solid {C_BORDER};
                font-weight:600; font-size:11px; text-transform:uppercase;
            }}
        """

    def start_benchmark(self):
        self.start_btn.setEnabled(False)
        self.start_btn.setText("评测中...")
        self.ranking_table.setRowCount(0)
        self.detail_table.setRowCount(0)
        safe_set_worker(self, 'worker', Worker(lambda: _request("POST", "/admin/api/benchmark")))
        self.worker.result.connect(self._on_started)
        self.worker.start()

    def _on_started(self, ok, data):
        if not ok:
            self.start_btn.setEnabled(True)
            self.start_btn.setText("开始评测")
            QMessageBox.warning(self, "错误", "启动评测失败")
            return
        self.run_id = data["run_id"]
        self.progress_label.setText("正在评测...")
        self.timer.start(3000)

    def poll_benchmark(self):
        if not self.run_id:
            return
        safe_set_worker(self, 'worker', Worker(lambda: _request("GET", f"/admin/api/benchmark/{self.run_id}")))
        self.worker.result.connect(self._on_polled)
        self.worker.start()

    def _on_polled(self, ok, data):
        if not ok:
            return
        self.progress_label.setText(f"进度: {data['progress']}/{data['total']}")
        if data["status"] == "done":
            self.timer.stop()
            self.start_btn.setEnabled(True)
            self.start_btn.setText("开始评测")
            self.progress_label.setText(f"评测完成!")
            self._show_results(data)
        elif data["status"] == "error":
            self.timer.stop()
            self.start_btn.setEnabled(True)
            self.start_btn.setText("开始评测")
            self.progress_label.setText(f"评测出错")

    def _show_results(self, data):
        ranking = data.get("ranking", [])
        self.ranking_table.setRowCount(len(ranking))
        for i, r in enumerate(ranking):
            self.ranking_table.setItem(i, 0, QTableWidgetItem(r["name"]))
            self.ranking_table.setItem(i, 1, QTableWidgetItem(r["type"]))
            self.ranking_table.setItem(i, 2, QTableWidgetItem(f"{r['avg_score']}"))
            self.ranking_table.setItem(i, 3, QTableWidgetItem(f"{r['avg_latency_s']}s"))
            self.ranking_table.setItem(i, 4, QTableWidgetItem(f"{r['total_tokens']:,}"))

        results = data.get("results", [])
        self.detail_table.setRowCount(len(results))
        for i, r in enumerate(results):
            self.detail_table.setItem(i, 0, QTableWidgetItem(f"{r['name']} ({r['model']})"))
            self.detail_table.setItem(i, 1, QTableWidgetItem(r["question"]))
            self.detail_table.setItem(i, 2, QTableWidgetItem(f"{r['score']}"))
            self.detail_table.setItem(i, 3, QTableWidgetItem(f"{r['latency_s']}s"))
            self.detail_table.setItem(i, 4, QTableWidgetItem(f"{r['prompt_tokens'] + r['completion_tokens']:,}"))
            self.detail_table.setItem(i, 5, QTableWidgetItem(r["content_preview"][:80]))

        if ranking:
            self.apply_btn.setEnabled(True)
            self._best = ranking[0]

    def apply_recommendation(self):
        if not hasattr(self, "_best"):
            return
        best = self._best
        reply = QMessageBox.question(
            self, "确认",
            f"将最佳配置应用到编排？\n\n推荐: {best['name']} (得分: {best['avg_score']})",
        )
        if reply == QMessageBox.Yes:
            if best["type"] == "moa":
                QMessageBox.information(self, "提示", "当前 MoA 配置已是最佳，无需更改。")
            else:
                ep_name = best["name"].split(" (")[0]
                data = {
                    "proposers": [{"endpoint": ep_name, "label": ep_name, "role": "strong"}],
                    "aggregator_endpoint": ep_name,
                    "aggregator_system_prompt": "You are a helpful assistant.",
                    "strategy": "simple",
                    "timeout": 120,
                    "stream_timeout": 300,
                    "proposer_temperature": 0.6,
                    "aggregator_temperature": 0.4,
                }
                safe_set_worker(self, 'worker', Worker(lambda: _request("PUT", "/admin/api/config", data)))
                self.worker.result.connect(lambda ok, d: QMessageBox.information(self, "成功", "配置已更新!") if ok else QMessageBox.warning(self, "失败", str(d)))
                self.worker.start()


# ═══════════════════════════════════════════
#  侧边栏导航按钮
# ═══════════════════════════════════════════

class NavButton(QFrame):
    """侧边栏导航项"""
    clicked = Signal(int)

    def __init__(self, text, index, parent=None):
        super().__init__(parent)
        self.index = index
        self._active = False
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(40)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 14, 0)
        self.label = QLabel(text)
        self.label.setStyleSheet(f"font-size:13px;font-weight:500;color:{C_SIDEBAR_TEXT};border:none;")
        layout.addWidget(self.label)
        self._update_style()

    def set_active(self, active):
        self._active = active
        self._update_style()

    def _update_style(self):
        if self._active:
            self.setStyleSheet(f"QFrame{{background:{C_SIDEBAR_ACTIVE};border-radius:8px;}}")
            self.label.setStyleSheet(f"font-size:13px;font-weight:500;color:white;border:none;")
        else:
            self.setStyleSheet("QFrame{background:transparent;border-radius:8px;} QFrame:hover{background:rgba(255,255,255,0.06);}")
            self.label.setStyleSheet(f"font-size:13px;font-weight:500;color:{C_SIDEBAR_TEXT};border:none;")

    def mousePressEvent(self, event):
        self.clicked.emit(self.index)


# ═══════════════════════════════════════════
#  主窗口
# ═══════════════════════════════════════════

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("octoMoA — 多模型聚合代理")
        self.resize(1080, 720)
        self.setMinimumSize(800, 520)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── 侧边栏 ──
        sidebar = QFrame()
        sidebar.setFixedWidth(220)
        sidebar.setStyleSheet(f"background:{C_SIDEBAR};")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(10, 24, 10, 16)
        sidebar_layout.setSpacing(0)

        # Logo
        logo_title = QLabel("octoMoA")
        logo_title.setStyleSheet(f"font-size:18px;font-weight:700;color:white;border:none;padding:0 14px;")
        logo_sub = QLabel("多模型聚合代理 v1.0")
        logo_sub.setStyleSheet(f"font-size:11px;color:{C_SIDEBAR_TEXT};border:none;padding:0 14px;")
        sidebar_layout.addWidget(logo_title)
        sidebar_layout.addWidget(logo_sub)
        sidebar_layout.addSpacing(20)

        # 导航项
        nav_items = ["  仪表盘", "  端点管理", "  编排配置", "  模型评测"]
        self.nav_buttons = []
        for i, text in enumerate(nav_items):
            btn = NavButton(text, i)
            btn.clicked.connect(self._switch_tab)
            sidebar_layout.addWidget(btn)
            self.nav_buttons.append(btn)

        sidebar_layout.addStretch()

        # 状态指示
        self.status_dot = QLabel("  ")
        self.status_dot.setFixedSize(8, 8)
        self.status_dot.setStyleSheet(f"background:{C_SUCCESS};border-radius:4px;border:none;")
        self.status_text = QLabel("检查中...")
        self.status_text.setStyleSheet(f"font-size:12px;color:{C_SIDEBAR_TEXT};border:none;")
        status_row = QHBoxLayout()
        status_row.setContentsMargins(14, 0, 14, 0)
        status_row.addWidget(self.status_dot)
        status_row.addWidget(self.status_text)
        sidebar_layout.addLayout(status_row)

        main_layout.addWidget(sidebar)

        # ── 右侧内容区 ──
        right = QWidget()
        right.setStyleSheet(f"background:{C_BG};")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # 顶栏
        topbar = QFrame()
        topbar.setFixedHeight(56)
        topbar.setStyleSheet(f"background:{C_CARD};border-bottom:1px solid {C_BORDER};")
        topbar_layout = QHBoxLayout(topbar)
        topbar_layout.setContentsMargins(24, 0, 24, 0)
        self.page_title = QLabel("仪表盘")
        self.page_title.setStyleSheet(f"font-size:15px;font-weight:600;color:{C_TEXT};border:none;")
        topbar_layout.addWidget(self.page_title)
        topbar_layout.addStretch()
        refresh_btn = make_ghost_btn("刷新")
        refresh_btn.clicked.connect(self._refresh_current)
        topbar_layout.addWidget(refresh_btn)
        right_layout.addWidget(topbar)

        # 内容堆叠
        self.dashboard = DashboardTab()
        self.endpoints = EndpointsTab()
        self.orchestration = OrchestrationTab()
        self.benchmark = BenchmarkTab()
        self.stack = QStackedWidget()
        self.stack.addWidget(self.dashboard)
        self.stack.addWidget(self.endpoints)
        self.stack.addWidget(self.orchestration)
        self.stack.addWidget(self.benchmark)
        right_layout.addWidget(self.stack)

        main_layout.addWidget(right)

        # 初始选中
        self._switch_tab(0)

        # 定时刷新
        self.timer = QTimer()
        self.timer.timeout.connect(self.dashboard.refresh)
        self.timer.start(30000)

        self.health_timer = QTimer()
        self.health_timer.timeout.connect(self._check_health)
        self.health_timer.start(10000)

    def _switch_tab(self, index):
        titles = ["仪表盘", "端点管理", "编排配置", "模型评测"]
        self.page_title.setText(titles[index])
        self.stack.setCurrentIndex(index)
        for i, btn in enumerate(self.nav_buttons):
            btn.set_active(i == index)
        # 切换时刷新
        if index == 0:
            self.dashboard.refresh()
        elif index == 1:
            self.endpoints.refresh()
        elif index == 2:
            self.orchestration.refresh()

    def _refresh_current(self):
        idx = self.stack.currentIndex()
        if idx == 0:
            self.dashboard.refresh()
        elif idx == 1:
            self.endpoints.refresh()
        elif idx == 2:
            self.orchestration.refresh()

    def _check_health(self):
        try:
            r = httpx.get(f"{API}/admin/api/stats", timeout=3)
            if r.status_code == 200:
                self.status_dot.setStyleSheet(f"background:{C_SUCCESS};border-radius:4px;border:none;")
                self.status_text.setText("服务运行中")
            else:
                raise Exception()
        except Exception:
            self.status_dot.setStyleSheet(f"background:{C_DANGER};border-radius:4px;border:none;")
            self.status_text.setText("服务未响应")


def run_desktop():
    """启动桌面窗口。由 desktop.py 调用。"""
    window = MainWindow()
    window.show()
    return window
