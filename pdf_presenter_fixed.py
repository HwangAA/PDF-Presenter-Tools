import sys
import os
import pymupdf as fitz
import logging
import math
import multiprocessing as mp
import queue
import time
from collections import OrderedDict
from pathlib import Path

# 고해상도(High DPI) 디스플레이 대응 설정
os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
os.environ["QT_SCALE_FACTOR_ROUNDING_POLICY"] = "PassThrough"

os.environ['QT_API'] = 'pyqt5' 

from PyQt5.QtWidgets import (QApplication, QMainWindow, QLabel, QVBoxLayout,
                             QHBoxLayout, QWidget, QPushButton, QFileDialog, QSizePolicy, QShortcut, QLineEdit,
                             QGraphicsDropShadowEffect, QAction, QActionGroup, QMenu, QStyle, QStyleOptionFrame)
from PyQt5.QtGui import QPixmap, QImage, QKeySequence, QFont, QFontDatabase, QIntValidator, QColor, QIcon, QPainter, QPen
from PyQt5.QtCore import Qt, qInstallMessageHandler, pyqtSignal, pyqtProperty, QTimer, QPropertyAnimation, QEasingCurve, QPointF, QRectF, QEvent

# Qt 5 may misread a Python installation path containing Korean characters.
import PyQt5
_platform_plugins = os.path.join(os.path.dirname(PyQt5.__file__), 'Qt5', 'plugins', 'platforms')
if os.path.isdir(_platform_plugins):
    os.environ.setdefault('QT_QPA_PLATFORM_PLUGIN_PATH', _platform_plugins)

def qt_message_handler(mode, context, message):
    if "splitter-horizontal.svg" in message:
        return
    if sys.stderr is not None:
        sys.stderr.write(f"Qt: {message}\n")
qInstallMessageHandler(qt_message_handler)
logger = logging.getLogger(__name__)


_bundled_font_ids = []


def ui_font_family():
    if not _bundled_font_ids:
        font_dir = Path(__file__).resolve().parent / 'assets' / 'fonts'
        for name in ('PRETENDARD-REGULAR.OTF', 'PRETENDARD-SEMIBOLD.OTF'):
            font_path = font_dir / name
            font_id = QFontDatabase.addApplicationFont(str(font_path))
            if font_id >= 0:
                _bundled_font_ids.append(font_id)
            else:
                logger.warning('Could not load bundled font: %s', font_path)
    available = QFontDatabase().families()
    return next((name for name in ('Pretendard', 'Malgun Gothic', '맑은 고딕', 'Noto Sans CJK KR')
                 if name in available), QApplication.font().family())


def selection_icon(selected):
    bitmap = QPixmap(48, 48)
    bitmap.fill(Qt.transparent)
    bitmap.setDevicePixelRatio(2)
    if selected:
        painter = QPainter(bitmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor('#80CBC4'), 2.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawLine(QPointF(5, 12), QPointF(10, 17))
        painter.drawLine(QPointF(10, 17), QPointF(19, 7))
        painter.end()
    return QIcon(bitmap)


def fit_label(pixmap, label):
    ratio = label.devicePixelRatioF()
    target = label.contentsRect().size() * ratio
    scaled = pixmap.scaled(target, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    scaled.setDevicePixelRatio(ratio)
    return scaled


def raster_matrix(rect, target_width, target_height):
    scale = min(target_width / rect.width, target_height / rect.height,
                math.sqrt(8_500_000 / (rect.width * rect.height)))
    # Fit both page boundaries to pixel boundaries. Uniform scaling can leave
    # a fractional last column blended against MuPDF's white page background.
    # The aspect-ratio adjustment is less than one output pixel; no content is cropped.
    width = max(1, math.floor(rect.width * scale + 1e-6))
    height = max(1, math.floor(rect.height * scale + 1e-6))
    # A 0.01-pixel tolerance prevents MuPDF fixed-point roundoff from leaving
    # partial coverage at an otherwise integer-aligned boundary.
    return fitz.Matrix((width + 0.01) / rect.width, (height + 0.01) / rect.height)


def render_page(page, target_width, target_height):
    matrix = raster_matrix(page.rect, target_width, target_height)
    pix = page.get_pixmap(matrix=matrix, colorspace=fitz.csRGB, alpha=False)
    width = round(page.rect.width * matrix.a)
    height = round(page.rect.height * matrix.d)
    # Discard only the raster allocation outside the intended pixel rectangle.
    if pix.width != width or pix.height != height:
        result = fitz.Pixmap(fitz.csRGB, fitz.IRect(pix.x, pix.y, pix.x + width, pix.y + height), False)
        result.copy(pix, result.irect)
        return result
    return pix


def render_worker(requests, results):
    """Keep one document per process; never share PyMuPDF objects with Qt."""
    doc = None
    document_key = None
    rendered_since_cleanup = 0
    try:
        while True:
            job = requests.get()
            if job is None:
                return
            job_id, path, page_num, target_width, target_height, token = job
            try:
                if document_key != (path, token):
                    if doc is not None:
                        doc.close()
                        doc = None
                    document_key = None
                    fitz.TOOLS.store_shrink(100)
                    doc = fitz.open(path)
                    document_key = (path, token)
                page = doc.load_page(page_num)
                if page.rect.width <= 0 or page.rect.height <= 0:
                    raise ValueError("페이지 크기가 올바르지 않습니다.")
                pix = render_page(page, target_width, target_height)
                rendered_since_cleanup += 1
                if rendered_since_cleanup >= 14:
                    fitz.TOOLS.store_shrink(100)
                    rendered_since_cleanup = 0
                results.put((job_id, (pix.samples, pix.width, pix.height, pix.stride), None))
                del pix, page
            except Exception as exc:
                results.put((job_id, None, str(exc)))
    finally:
        if doc is not None:
            doc.close()
        fitz.TOOLS.store_shrink(100)


class PageEdit(QLineEdit):
    cancelRequested = pyqtSignal()
    focusOutSignal = pyqtSignal()
    focusInSignal = pyqtSignal()
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._focus_glow = 0.0
        # Animate only a small painted outline. A changing drop-shadow blur
        # reallocates its offscreen surface and is expensive on high-DPI screens.
        self.anim = QPropertyAnimation(self, b"focusGlow", self)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        self.anim.setDuration(180)

    @pyqtProperty(float)
    def focusGlow(self):
        return self._focus_glow

    @focusGlow.setter
    def focusGlow(self, value):
        self._focus_glow = value
        self.update()

    def animate_focus(self, target):
        self.anim.stop()
        self.anim.setStartValue(self._focus_glow)
        self.anim.setEndValue(target)
        self.anim.start()

    def paintEvent(self, event):
        if self.hasFocus():
            super().paintEvent(event)
        else:
            # QLineEdit retains a caret-driven horizontal scroll offset during
            # rapid text/state changes. Display mode has no caret or scrolling:
            # draw the number directly in the same fixed rectangle every time.
            option = QStyleOptionFrame()
            self.initStyleOption(option)
            painter = QPainter(self)
            self.style().drawPrimitive(QStyle.PE_PanelLineEdit, option, painter, self)
            painter.setFont(self.font())
            painter.setPen(QColor('#80CBC4'))
            painter.drawText(self.rect().adjusted(4, 0, -4, 0), Qt.AlignCenter, self.text())
            painter.end()
        if self._focus_glow <= 0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(Qt.NoBrush)
        # Soft concentric strokes stay inside the widget's fixed bounds.
        for width, alpha in ((7, 16), (4, 35), (1.5, 220)):
            color = QColor('#4CDAFA')
            color.setAlpha(round(alpha * self._focus_glow))
            painter.setPen(QPen(color, width))
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(4, 4, -4, -4), 10, 10)
        painter.end()
    
    def event(self, event):
        if event.type() == QEvent.ShortcutOverride and event.key() == Qt.Key_Escape:
            event.accept()
            return True
        return super().event(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.cancelRequested.emit()
            event.accept()
            return
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            # QLineEdit suppresses returnPressed for validator-intermediate
            # input such as 0 or an out-of-range number. Always submit so the
            # controller can restore the actual page number.
            self.returnPressed.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.focusInSignal.emit()
        QTimer.singleShot(0, self.selectAll)
        self.animate_focus(1.0)
        
    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.focusOutSignal.emit()
        self.animate_focus(0.0)

class MaterialButton(QPushButton):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.shadow = QGraphicsDropShadowEffect(self)
        self.shadow.setBlurRadius(8)
        self.shadow.setColor(QColor(0, 0, 0, 100))
        self.shadow.setOffset(0, 2)
        self.setGraphicsEffect(self.shadow)

        self.anim_blur = QPropertyAnimation(self.shadow, b"blurRadius")
        self.anim_blur.setEasingCurve(QEasingCurve.OutCubic)
        self.anim_blur.setDuration(250)

        self.anim_offset = QPropertyAnimation(self.shadow, b"offset")
        self.anim_offset.setEasingCurve(QEasingCurve.OutCubic)
        self.anim_offset.setDuration(250)

    def enterEvent(self, event):
        self.anim_blur.setEndValue(24)
        self.anim_offset.setEndValue(QPointF(0, 8))
        self.anim_blur.start()
        self.anim_offset.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.anim_blur.setEndValue(8)
        self.anim_offset.setEndValue(QPointF(0, 2))
        self.anim_blur.start()
        self.anim_offset.start()
        super().leaveEvent(event)


class AudienceWindow(QMainWindow):
    stop_requested = pyqtSignal()
    next_page_signal = pyqtSignal()
    prev_page_signal = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("오디언스 뷰 (청중 화면)")
        self.label = QLabel(self)
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("background-color: #000000;")
        self.label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.setCentralWidget(self.label)
        
        self.allow_close = False
        self.current_pixmap = None
        
        self.resize_timer = QTimer()
        self.resize_timer.setSingleShot(True)
        self.resize_timer.timeout.connect(self.refresh_layout)

        QShortcut(QKeySequence(Qt.Key_Escape), self).activated.connect(self.ignore_escape)
        
    def ignore_escape(self):
        pass 

    def update_page(self, pixmap):
        self.current_pixmap = pixmap
        self.refresh_layout()

    def refresh_layout(self):
        if self.current_pixmap and not self.current_pixmap.isNull():
            target_size = self.label.contentsRect().size()
            if target_size.width() > 0 and target_size.height() > 0:
                scaled_pixmap = fit_label(self.current_pixmap, self.label)
                self.label.setPixmap(scaled_pixmap)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.resize_timer.start(100)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Right, Qt.Key_Down, Qt.Key_PageDown):
            self.next_page_signal.emit()
        elif event.key() in (Qt.Key_Left, Qt.Key_Up, Qt.Key_PageUp):
            self.prev_page_signal.emit()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        if self.allow_close:
            event.accept()
        else:
            event.ignore()
            self.hide()
            self.stop_requested.emit()


class PresenterWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDF 발표자 도구")
        self.pdf_doc = None
        self.resize(1100, 750)
        self.current_page = 0
        self.total_pages = 0
        
        self.cached_curr_pixmap = None
        self.cached_next_pixmap = None
        self.displayed_preview_page = None
        self.pdf_path = None
        self.preview_message = "PDF 파일을 열어 주세요."
        self.page_cache = OrderedDict()
        self.cache_budget_bytes = 256 * 1024 * 1024
        self.prefetch_attempted = set()
        self.jobs = {}
        self.job_serial = 0
        self.doc_serial = 0
        self.document_tokens = {}
        self.last_render_progress = time.monotonic()
        self.navigation_pending = False
        self.navigation_target = None
        self.force_navigation = False
        self.opening_pdf = False
        self.presentation_active = False
        self.screen_summary = ''
        self._audience_target = None
        self._audience_mode = None
        self._output_size = None
        self.worker = None
        self.closing = False
        self.selected_screen = None
        self.render_timer = QTimer(self)
        self.render_timer.timeout.connect(self.poll_render_results)
        self.render_timer.setInterval(30)
        self.screen_timer = QTimer(self)
        self.screen_timer.setSingleShot(True)
        self.screen_timer.timeout.connect(self.refresh_screens)
        self.dpi_layout_timer = QTimer(self)
        self.dpi_layout_timer.setSingleShot(True)
        self.dpi_layout_timer.timeout.connect(self.refresh_controller_layout)

        self.resize_timer = QTimer()
        self.resize_timer.setSingleShot(True)
        self.resize_timer.timeout.connect(self.refresh_layout)

        self.setAcceptDrops(True)
        self.audience_window = AudienceWindow()
        
        self.audience_window.next_page_signal.connect(self.next_page)
        self.audience_window.prev_page_signal.connect(self.prev_page)
        self.audience_window.stop_requested.connect(self.stop_presentation)

        self.initUI()
        self.setup_shortcuts()
        app = QApplication.instance()
        app.screenAdded.connect(self.screen_configuration_changed)
        app.screenRemoved.connect(self.screen_configuration_changed)
        self.watched_screens = []
        QTimer.singleShot(0, self.refresh_screens)
        
        QApplication.instance().installEventFilter(self)

    def initUI(self):
        from presenter_ui import build_ui
        build_ui(self, PageEdit)

    def sync_ui(self):
        from presenter_ui import sync_navigation
        sync_navigation(self)

    def eventFilter(self, obj, event):
        # Only leave page editing for a click on a non-interactive area of
        # this window. Once focus moves, propagated copies do no more work.
        if (event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton
                and self.edit_page.hasFocus() and QApplication.activeWindow() == self
                and isinstance(obj, QWidget) and obj.window() == self):
            widget = obj
            while widget is not None and widget is not self:
                if (widget.focusPolicy() != Qt.NoFocus
                        or isinstance(widget, QPushButton)
                        or widget.inherits("QSplitterHandle")):
                    break
                widget = widget.parentWidget()
            else:
                self.setFocus()
        return super().eventFilter(obj, event)

    def setup_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+O"), self).activated.connect(self.open_pdf_dialog)
        self.shortcuts = []
        
        next_keys = [Qt.Key_Right, Qt.Key_Down, Qt.Key_PageDown]
        for key in next_keys:
            sc = QShortcut(QKeySequence(key), self)
            sc.activated.connect(self.next_page)
            self.shortcuts.append(sc)
        
        for key in [Qt.Key_Left, Qt.Key_Up, Qt.Key_PageUp]:
            sc = QShortcut(QKeySequence(key), self)
            sc.activated.connect(self.prev_page)
            self.shortcuts.append(sc)

        QShortcut(QKeySequence(Qt.Key_Escape), self).activated.connect(self.ignore_escape)
        
    def ignore_escape(self):
        if self.edit_page.hasFocus():
            self.cancel_page_edit()

    def cancel_page_edit(self):
        self.restore_page_text()
        self.setFocus(Qt.OtherFocusReason)

    def disable_shortcuts(self):
        for sc in self.shortcuts:
            sc.setEnabled(False)

    def enable_shortcuts(self):
        for sc in self.shortcuts:
            sc.setEnabled(True)

    def show_error(self, message):
        logger.error(message)
        self.statusBar().showMessage(message, 10000)

    def next_page(self):
        page = self.navigation_target if self.navigation_target is not None else self.current_page
        self.navigate_to(page + 1)

    def prev_page(self):
        page = self.navigation_target if self.navigation_target is not None else self.current_page
        self.navigate_to(page - 1)

    def jump_to_page_inline(self):
        try:
            target = int(self.edit_page.text().strip()) - 1
        except ValueError:
            target = -1
        self.restore_page_text()
        self.setFocus()
        self.navigate_to(target)

    def restore_page_text(self):
        self.edit_page.setText(str(self.current_page + 1) if self.pdf_doc is not None else "-")

    def screen_configuration_changed(self, *args):
        if self.closing:
            return
        self.screen_timer.start(150)
        # Windows/Qt can deliver the screen, DPI and native resize messages
        # separately. Reflow once they settle, without changing the UI scale.
        self.dpi_layout_timer.start(350)

    def refresh_controller_layout(self):
        if self.closing or not self.windowHandle():
            return
        screen = self.windowHandle().screen()
        if screen is None:
            return
        # Keep a normal window usable on the smaller monitor. Maximized and
        # fullscreen geometry belongs to the window manager.
        if not self.isMaximized() and not self.isFullScreen() and not self.isMinimized():
            available = screen.availableGeometry()
            frame = self.frameGeometry()
            extra_w = max(0, frame.width() - self.width())
            extra_h = max(0, frame.height() - self.height())
            width = max(self.minimumWidth(), min(self.width(), available.width() - extra_w))
            height = max(self.minimumHeight(), min(self.height(), available.height() - extra_h))
            if (width, height) != (self.width(), self.height()):
                self.resize(width, height)
        # A resize event is not guaranteed when only the device pixel ratio
        # changes. Invalidate cached layout geometry even if logical size matches.
        self.layout().invalidate()
        self.layout().setGeometry(self.rect())
        self.layout().activate()
        central = self.centralWidget()
        for widget in [central] + central.findChildren(QWidget):
            widget.updateGeometry()
            layout = widget.layout()
            if layout is not None:
                layout.invalidate()
                layout.setGeometry(widget.contentsRect())
                layout.activate()
        self.navigation_dock.last_dimensions = None
        self.navigation_dock.scale_controls()
        central.layout().activate()
        self.refresh_layout()
        central.update()
        self.update()

    def refresh_screens(self):
        if self.closing:
            return
        screens = QApplication.screens()
        for screen in screens:
            if screen not in self.watched_screens:
                screen.geometryChanged.connect(self.screen_configuration_changed)
                screen.availableGeometryChanged.connect(self.screen_configuration_changed)
                screen.logicalDotsPerInchChanged.connect(self.screen_configuration_changed)
                screen.physicalDotsPerInchChanged.connect(self.screen_configuration_changed)
                self.watched_screens.append(screen)
        self.watched_screens = [screen for screen in self.watched_screens if screen in screens]
        if self.selected_screen not in screens:
            self.selected_screen = None
        self.screen_menu.clear()
        if hasattr(self, 'screen_actions'):
            self.screen_actions.deleteLater()
        self.screen_actions = QActionGroup(self)
        automatic = QAction("자동 선택 (발표자 화면과 다른 모니터)", self.screen_menu)
        automatic.setCheckable(True)
        automatic.setChecked(self.selected_screen is None)
        automatic.setIcon(selection_icon(self.selected_screen is None))
        automatic.triggered.connect(lambda: self.choose_screen(None))
        self.screen_actions.addAction(automatic)
        self.screen_menu.addAction(automatic)
        for index, screen in enumerate(screens):
            geometry = screen.geometry()
            action = QAction(f"{index + 1}: {screen.name()} ({geometry.width()} × {geometry.height()})", self.screen_menu)
            action.setCheckable(True)
            action.setChecked(screen == self.selected_screen)
            action.setIcon(selection_icon(screen == self.selected_screen))
            action.triggered.connect(lambda checked, chosen=screen: self.choose_screen(chosen))
            self.screen_actions.addAction(action)
            self.screen_menu.addAction(action)
        self.setup_screens()

    def choose_screen(self, screen):
        self.selected_screen = screen
        self.refresh_screens()

    def resolve_screens(self):
        screens = QApplication.screens()
        presenter_screen = self.windowHandle().screen() if self.windowHandle() else QApplication.primaryScreen()
        target = self.selected_screen
        if target not in screens:
            target = next((screen for screen in screens if screen != presenter_screen), presenter_screen)
        return presenter_screen, target

    def toggle_presentation(self):
        if self.presentation_active:
            self.stop_presentation()
        else:
            self.start_presentation()

    def start_presentation(self):
        if self.pdf_doc is None or self.navigation_pending or self.closing:
            return
        self.presentation_active = True
        self.audience_window.update_page(self.cached_curr_pixmap)
        self.setup_screens()
        self.sync_ui()
        self.activateWindow()
        self.setFocus()

    def stop_presentation(self):
        self.presentation_active = False
        self.audience_window.hide()
        self.sync_ui()

    def setup_screens(self):
        if self.closing or not QApplication.screens():
            return
        presenter_screen, target = self.resolve_screens()
        audience = self.audience_window
        mode = 'fullscreen' if target != presenter_screen else 'windowed'
        if self.presentation_active:
            changed = target != self._audience_target or mode != self._audience_mode
            if changed:
                if self._audience_mode == 'windowed':
                    self._windowed_geometry = audience.saveGeometry()
                audience.hide()
                audience.winId()  # Create the native handle without flashing on the wrong monitor.
                if audience.windowHandle():
                    audience.windowHandle().setScreen(target)
                if mode == 'fullscreen':
                    audience.setGeometry(target.geometry())
                    audience.showFullScreen()
                else:
                    audience.setWindowState(Qt.WindowNoState)
                    geometry = target.availableGeometry()
                    if hasattr(self, '_windowed_geometry'):
                        audience.restoreGeometry(self._windowed_geometry)
                        # A saved rectangle may belong to a disconnected monitor.
                        if not audience.frameGeometry().intersects(geometry):
                            audience.move(geometry.topLeft())
                    else:
                        audience.resize(min(640, geometry.width()), min(480, geometry.height()))
                        audience.move(geometry.topLeft())
                        audience.showNormal()
                self._audience_target, self._audience_mode = target, mode
            if audience.isHidden():
                audience.show()
            audience.refresh_layout()
        else:
            audience.hide()
        from presenter_ui import sync_screen
        sync_screen(self, target, presenter_screen)
        if not getattr(self, '_startup_focus_set', False):
            self.setFocus(Qt.OtherFocusReason)
            self._startup_focus_set = True
        size = self.render_size()
        old_size, self._output_size = self._output_size, size
        if self.pdf_doc is not None and old_size is not None and old_size != size and not self.opening_pdf:
            target_page = self.navigation_target if self.navigation_target is not None else self.current_page
            self.navigate_to(target_page)

    def showEvent(self, event):
        super().showEvent(event)
        if not getattr(self, 'screen_hooked', False) and self.windowHandle():
            self.windowHandle().screenChanged.connect(self.screen_configuration_changed)
            self.screen_hooked = True

    def open_pdf_dialog(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "PDF 파일 열기", "", "PDF Files (*.pdf)")
        if file_name:
            self.load_pdf(file_name)

    def load_pdf(self, file_path):
        if self.navigation_pending:
            self.statusBar().showMessage("페이지를 준비 중입니다. 잠시 후 다시 시도해 주세요.", 3000)
            return
        candidate = None
        try:
            candidate = fitz.open(file_path)
            if not candidate.is_pdf:
                raise ValueError("PDF 파일이 아닙니다.")
            if candidate.needs_pass:
                raise ValueError("비밀번호가 설정된 보안 PDF는 열 수 없습니다.")
            if len(candidate) == 0:
                raise ValueError("페이지가 없는 PDF입니다.")
            # A new document must not queue behind an obsolete speculative
            # render, or inherit its timeout. Replace the worker and queues.
            if self.jobs:
                self.stop_worker()
                self.jobs.clear()
                self.prefetch_attempted.clear()
            self.request_render(candidate, os.path.abspath(file_path), 0, 'open')
        except Exception as exc:
            if candidate is not None:
                self.document_tokens.pop(id(candidate), None)
                candidate.close()
            self.show_error(f"파일을 열 수 없습니다: {exc}")

    def render_size(self):
        _, screen = self.resolve_screens()
        if screen is None:
            return (1920, 1080)
        size = screen.size()
        ratio = screen.devicePixelRatio()
        return max(1, round(size.width() * ratio)), max(1, round(size.height() * ratio))

    def start_worker(self):
        if self.worker is None:
            context = mp.get_context('spawn')
            self.requests = context.Queue()
            self.results = context.Queue()
            self.worker = context.Process(target=render_worker, args=(self.requests, self.results), daemon=True)
            try:
                self.worker.start()
            except Exception:
                self.worker = None
                for channel in (self.requests, self.results):
                    channel.close()
                raise
            self.render_timer.start()

    def request_render(self, doc, path, page, kind):
        self.start_worker()
        self.job_serial += 1
        size = self.render_size()
        job = (doc, path, page, kind, size)
        if kind == 'open':
            self.doc_serial += 1
            self.document_tokens[id(doc)] = self.doc_serial
        token = self.document_tokens[id(doc)]
        self.requests.put((self.job_serial, path, page, *size, token))
        if not self.jobs:
            self.last_render_progress = time.monotonic()
        self.jobs[self.job_serial] = job
        if kind != 'preview':
            if kind == 'open':
                self.opening_pdf = True
            elif self.navigation_target is None:
                self.navigation_target = page
            self.navigation_pending = True
            self.edit_page.setEnabled(False)
            self.statusBar().showMessage("페이지를 준비하고 있습니다…")
            self.sync_ui()

    def navigate_to(self, page, force=False):
        if self.pdf_doc is None or self.opening_pdf or self.closing or not 0 <= page < self.total_pages:
            return
        self.navigation_target = page
        self.force_navigation = force
        self.navigation_pending = True
        self.drive_navigation()

    def drive_navigation(self):
        if self.navigation_target is None or self.opening_pdf or self.closing:
            return
        page, size = self.navigation_target, self.render_size()
        key = (page, size)
        if not self.force_navigation and key in self.page_cache:
            self.navigation_target = None
            self.navigation_pending = False
            self.edit_page.setEnabled(True)
            self.commit_page(page, self.page_cache[key])
            return
        # Promote the in-flight preview instead of throwing its work away.
        for job_id, job in list(self.jobs.items()):
            doc, path, target, kind, pending_size = job
            if doc is self.pdf_doc and target == page and pending_size == size:
                self.jobs[job_id] = (doc, path, target, 'navigate', pending_size)
        self.edit_page.setEnabled(False)
        self.statusBar().showMessage(f'{page + 1}페이지를 준비하고 있습니다…')
        self.sync_ui()
        # At most one speculative render exists; foreground work is next.
        if self.jobs:
            return
        try:
            self.request_render(self.pdf_doc, self.pdf_path, page, 'navigate')
        except Exception as exc:
            self.navigation_target = None
            self.navigation_pending = False
            self.force_navigation = False
            self.edit_page.setEnabled(True)
            self.sync_ui()
            self.show_error(f"페이지를 표시할 수 없습니다: {exc}")

    def prefetch_pages(self):
        offsets = [0, 1, -1, 2, -2, 3, -3] + list(range(4, 11))
        return [self.current_page + offset for offset in offsets
                if 0 <= self.current_page + offset < self.total_pages]

    def cache_bytes(self):
        return sum(p.width() * p.height() * max(1, p.depth() // 8)
                   for p in self.page_cache.values())

    def trim_cache(self):
        size = self.render_size()
        priorities = self.prefetch_pages()
        for key in list(self.page_cache):
            if key[0] not in priorities or key[1] != size:
                del self.page_cache[key]
        while self.page_cache and self.cache_bytes() > self.cache_budget_bytes:
            victim = max(self.page_cache, key=lambda key: priorities.index(key[0]))
            del self.page_cache[victim]

    def cache_page(self, page, size, pixmap):
        self.page_cache[(page, size)] = pixmap
        # Foreground results are trimmed after current_page is committed.

    def schedule_prefetch(self):
        if self.closing or self.pdf_doc is None or self.navigation_pending or self.jobs:
            return
        size = self.render_size()
        self.trim_cache()
        for page in self.prefetch_pages()[1:]:
            key = (page, size)
            if key in self.page_cache or key in self.prefetch_attempted:
                continue
            # Only one speculative job in flight; reevaluate after each result.
            self.prefetch_attempted.add(key)
            try:
                self.request_render(self.pdf_doc, self.pdf_path, page, 'preview')
            except Exception as exc:
                self.preview_note.setText("미리보기를 표시할 수 없습니다.")
                logger.error("Prefetch scheduling failed: %s", exc)
            return

    def poll_render_results(self):
        while True:
            try:
                job_id, payload, error = self.results.get_nowait()
            except queue.Empty:
                break
            except (EOFError, OSError, ValueError) as exc:
                self.fail_pending_renders(f"PDF 처리 통신 오류: {exc}. 다시 시도해 주세요.")
                return
            job = self.jobs.pop(job_id, None)
            if job is not None:
                self.last_render_progress = time.monotonic()
                self.finish_render(job, payload, error)
        if self.worker is not None and not self.worker.is_alive():
            self.fail_pending_renders("PDF 처리 프로세스가 종료되었습니다. 다시 시도해 주세요.")
        elif self.jobs and time.monotonic() - self.last_render_progress > 60:
            self.fail_pending_renders("PDF 처리 시간이 60초를 초과했습니다. 다시 시도해 주세요.")
        else:
            self.drive_navigation()
            self.schedule_prefetch()

    def fail_pending_renders(self, message):
        pending = list(self.jobs.values())
        self.jobs.clear()
        self.stop_worker()
        self.navigation_target = None
        self.navigation_pending = False
        self.force_navigation = False
        self.opening_pdf = False
        for job in pending:
            self.finish_render(job, None, message)
        self.edit_page.setEnabled(self.pdf_doc is not None)
        self.restore_page_text()
        self.sync_ui()
        self.show_error(message)

    def finish_render(self, job, payload, error):
        doc, path, page, kind, size = job
        if kind != 'open' and doc is not self.pdf_doc:
            return
        pixmap = None
        if error is None:
            try:
                samples, width, height, stride = payload
                image = QImage(samples, width, height, stride, QImage.Format_RGB888)
                pixmap = QPixmap.fromImage(image)
                if pixmap.isNull():
                    raise ValueError("페이지 이미지를 만들 수 없습니다.")
            except Exception as exc:
                error = str(exc)
        if error is not None:
            if kind == 'navigate' and (page != self.navigation_target or size != self.render_size()):
                # The user may already have chosen another page/resolution.
                # An obsolete failure must not cancel that newer request.
                self.drive_navigation()
                return
            if kind == 'open':
                self.document_tokens.pop(id(doc), None)
                doc.close()
                self.opening_pdf = False
                self.navigation_pending = False
            if kind == 'preview':
                if page == self.current_page + 1 and size == self.render_size():
                    self.preview_message = "미리보기를 표시할 수 없습니다."
                    self.cached_next_pixmap = None
                    self.displayed_preview_page = None
                    self.preview_note.clear()
                    self.refresh_layout()
                logger.error("Preview rendering failed: %s", error)
            else:
                if self.navigation_target in (None, page):
                    self.navigation_target = None
                    self.navigation_pending = False
                    self.force_navigation = False
                self.restore_page_text()
                self.show_error(f"페이지를 표시할 수 없습니다: {error}")
            self.edit_page.setEnabled(self.pdf_doc is not None and not self.navigation_pending)
            self.sync_ui()
            return
        if kind == 'open':
            self.opening_pdf = False
            self.navigation_pending = False
            self.navigation_target = None
            self.force_navigation = False
            self.stop_presentation()
            old_doc = self.pdf_doc
            self.pdf_doc = doc
            self.pdf_path = path
            self.total_pages = len(doc)
            self.page_cache.clear()
            self.prefetch_attempted.clear()
            # Never retain an image belonging to the previous document.
            self.cached_next_pixmap = None
            self.displayed_preview_page = None
            self.edit_page.validator().setRange(1, self.total_pages)
            self.edit_page.setEnabled(True)
            self.setWindowTitle(f"PDF 발표자 도구 - {os.path.basename(path)}")
            if old_doc is not None:
                self.document_tokens.pop(id(old_doc), None)
                old_doc.close()
        self.cache_page(page, size, pixmap)
        if kind == 'preview':
            self.trim_cache()
            if page == self.current_page + 1 and size == self.render_size():
                self.cached_next_pixmap = pixmap
                self.displayed_preview_page = page
                self.preview_note.clear()
                self.refresh_layout()
        elif kind == 'open' or (page == self.navigation_target and size == self.render_size()):
            self.navigation_pending = False
            self.navigation_target = None
            self.force_navigation = False
            self.edit_page.setEnabled(True)
            needs_resize = size != self.render_size()
            self.commit_page(page, pixmap, prefetch=not needs_resize)
            if needs_resize:
                self.navigate_to(page)
        else:
            # Obsolete foreground results can warm the cache, never move the display.
            self.trim_cache()
        self.drive_navigation()

    def commit_page(self, page, pixmap, prefetch=True):
        if page != self.current_page:
            self.prefetch_attempted.clear()
        self.current_page = page
        self.trim_cache()
        self.cached_curr_pixmap = pixmap
        self.audience_window.update_page(pixmap)
        self.restore_page_text()
        self.lbl_suffix.setText(f"/ {self.total_pages}")
        remaining = self.total_pages - page - 1
        self.lbl_remaining.setText(f"남은 페이지  <span style='color:#80CBC4;'>{remaining}</span>")
        self.statusBar().clearMessage()
        self.sync_ui()
        ready_preview = self.page_cache.get((page + 1, self.render_size()))
        if ready_preview is not None or not remaining:
            self.cached_next_pixmap = ready_preview if remaining else None
            self.displayed_preview_page = page + 1 if remaining else None
            self.preview_note.clear()
        else:
            # Keep the old image on screen until the replacement is complete.
            # Put progress outside the image so there is no blank/text flash.
            note = f"{page + 2}페이지 준비 중"
            if self.displayed_preview_page is not None:
                note += f" · {self.displayed_preview_page + 1}페이지 표시 중"
            self.preview_note.setText(note)
        self.preview_message = "마지막 페이지입니다." if remaining == 0 else "미리보기를 준비하고 있습니다…"
        self.refresh_layout()
        if prefetch:
            self.schedule_prefetch()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith('.pdf'):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if file_path.lower().endswith('.pdf'):
                self.load_pdf(file_path)
                event.acceptProposedAction()
                break

    def refresh_layout(self):
        self.sync_ui()
        target_size_curr = self.current_view.contentsRect().size()
        if self.cached_curr_pixmap and target_size_curr.width() > 0 and target_size_curr.height() > 0:
            self.current_view.setPixmap(fit_label(self.cached_curr_pixmap, self.current_view))
        
        target_size_next = self.next_view.contentsRect().size()
        if self.cached_next_pixmap and target_size_next.width() > 0 and target_size_next.height() > 0:
            self.next_view.setPixmap(fit_label(self.cached_next_pixmap, self.next_view))
        elif not self.cached_next_pixmap:
            self.next_view.clear()
            self.next_view.setText(self.preview_message)
        stale = (self.pdf_doc is not None and self.current_page + 1 < self.total_pages
                 and self.cached_next_pixmap is not None
                 and self.displayed_preview_page != self.current_page + 1)
        self.preview_overlay.setGeometry(self.next_view.rect())
        self.preview_overlay.setText(f"{self.current_page + 2}페이지 준비 중")
        self.preview_overlay.setVisible(stale)
        if stale:
            self.preview_overlay.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.pdf_doc:
            self.resize_timer.start(100)

    def stop_worker(self):
        self.render_timer.stop()
        if self.worker is not None:
            if self.worker.is_alive():
                self.worker.terminate()
            self.worker.join(timeout=1)
            if self.worker.is_alive():
                self.worker.kill()
                self.worker.join()
            self.worker.close()
            self.worker = None
            for channel in (self.requests, self.results):
                channel.cancel_join_thread()
                channel.close()

    def closeEvent(self, event):
        self.closing = True
        self.resize_timer.stop()
        self.screen_timer.stop()
        self.dpi_layout_timer.stop()
        self.stop_worker()
        for doc, path, page, kind, size in self.jobs.values():
            if kind == 'open':
                self.document_tokens.pop(id(doc), None)
                doc.close()
        self.jobs.clear()
        self.document_tokens.clear()
        if self.pdf_doc is not None:
            self.pdf_doc.close()
            self.pdf_doc = None
        self.page_cache.clear()
        self.prefetch_attempted.clear()
        self.cached_curr_pixmap = None
        self.cached_next_pixmap = None
        self.current_view.clear()
        self.next_view.clear()
        self.audience_window.current_pixmap = None
        self.audience_window.label.clear()
        self.audience_window.resize_timer.stop()
        self.audience_window.allow_close = True
        self.audience_window.close()
        event.accept()

if __name__ == '__main__':
    mp.freeze_support()
    diagnostic = len(sys.argv) == 3 and sys.argv[1] == '--self-test'
    if diagnostic:
        os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(str(Path(__file__).resolve().parent / 'assets' / 'app-icon.png')))
    font_family = ui_font_family()
    app.setFont(QFont(font_family, 12))
    
    from qt_material import apply_stylesheet
    
    extra_settings = {
        'font_family': font_family,
        'font_size': '16px',
    }
    
    apply_stylesheet(app, theme='dark_teal.xml', extra=extra_settings)
    
    presenter = PresenterWindow()
    presenter.show()
    if diagnostic:
        from build_diagnostics import start_diagnostics
        start_diagnostics(app, presenter, sys.argv[2], _bundled_font_ids)
    exit_code = app.exec_()
    # Release widgets while QApplication and its registered fonts still exist.
    from PyQt5 import sip
    sip.delete(presenter.audience_window)
    sip.delete(presenter)
    sys.exit(exit_code)
