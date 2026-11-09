"""Presentation workspace UI. Rendering and navigation remain in the controller."""
from pathlib import Path
import re
from PyQt5.QtCore import Qt, QEvent, QTimer
from PyQt5.QtWidgets import (QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
                             QSizePolicy, QMenu, QProgressBar, QSplitter, QSplitterHandle, QLayout)
from PyQt5.QtGui import QIntValidator, QColor, QPalette, QPainter, QPen


class ResizeHandle(QSplitterHandle):
    def __init__(self, orientation, parent):
        super().__init__(orientation, parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAccessibleName('영역 크기 조절')
        self.setToolTip('드래그하여 크기 조절 · 방향키로도 조절할 수 있습니다.')
        self.setCursor(Qt.SplitHCursor if orientation == Qt.Horizontal else Qt.SplitVCursor)

    def event(self, event):
        keys = (Qt.Key_Left, Qt.Key_Right) if self.orientation() == Qt.Horizontal else (Qt.Key_Up, Qt.Key_Down)
        if event.type() == QEvent.ShortcutOverride and event.key() in keys:
            event.accept()
            return True
        return super().event(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if event.button() == Qt.LeftButton:
            # Dragging is complete: restore presentation shortcuts. Keyboard
            # users can still focus the handle with Tab to resize with arrows.
            self.window().setFocus(Qt.MouseFocusReason)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor('#D5E7FF' if self.hasFocus() or self.underMouse() else '#8496AC'), 3, Qt.SolidLine, Qt.RoundCap))
        c = self.rect().center()
        if self.orientation() == Qt.Horizontal:
            painter.drawLine(c.x(), c.y()-20, c.x(), c.y()+20)
        else:
            painter.drawLine(c.x()-20, c.y(), c.x()+20, c.y())
        painter.end()

    def keyPressEvent(self, event):
        keys = (Qt.Key_Left, Qt.Key_Right) if self.orientation() == Qt.Horizontal else (Qt.Key_Up, Qt.Key_Down)
        if event.key() in keys:
            sizes = self.splitter().sizes()
            delta = -24 if event.key() == keys[0] else 24
            self.splitter().setSizes([max(1, sizes[0]+delta), max(1, sizes[1]-delta)])
            self.splitter().splitterMoved.emit(self.splitter().sizes()[0], 1)
            event.accept()
        else:
            super().keyPressEvent(event)


class AdjustableSplitter(QSplitter):
    def __init__(self, orientation):
        super().__init__(orientation)
        self.setChildrenCollapsible(False)
        self.setHandleWidth(18)
        self.setStyleSheet('QSplitter {background: transparent; border: none;}')

    def createHandle(self):
        return ResizeHandle(self.orientation(), self)


class NavigationDock(QWidget):
    def __init__(self, window):
        super().__init__()
        self.controller = window
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.scale_timer = QTimer(self)
        self.scale_timer.setSingleShot(True)
        self.scale_timer.timeout.connect(self.scale_controls)
        self.last_dimensions = None

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.scale_timer.start(0)

    def scale_controls(self):
        w = self.controller
        if not hasattr(w, 'page_progress'):
            return
        # Keep the font/width scale within the available horizontal space;
        # touch height continues growing even on a narrower window.
        height = round(min(160, 48 + max(0, self.height()-112)*0.8))
        scale = min(2.3, height/48, max(1.0, (self.width()-40)/760))
        key = (height, round(scale, 3))
        if key == self.last_dimensions:
            return
        self.last_dimensions = key
        for view in (w.btn_prev, w.btn_next):
            view.setFixedSize(round(112*scale), height)
            view.setStyleSheet(view.base_touch_style +
                f'QPushButton {{font-size: {round(14*scale)}px; padding: 0; border-radius: {min(32, height//2)}px;}}')
        w.edit_page.setFixedSize(round(86*scale), height)
        w.edit_page.setStyleSheet(w.edit_page.base_touch_style +
            f'QLineEdit {{font-size: {round(25*scale)}px;}}')
        w.page_box.setFixedWidth(round(210*scale))
        for view, size in ((w.lbl_prefix,13), (w.lbl_suffix,16), (w.lbl_remaining,14)):
            view.setStyleSheet(re.sub(r'font-size: \d+px', f'font-size: {round(size*scale)}px', view.base_touch_style))
        w.page_progress.setFixedHeight(max(3, round(3*height/48)))


def unavailable(view, value):
    if view.property('unavailable') != value:
        view.setProperty('unavailable', value)
        view.style().unpolish(view)
        view.style().polish(view)
        view.update()


def label(text, size=14, color='#A7B5C8', bold=False):
    view = QLabel(text)
    view.setStyleSheet(f'background: transparent; border: none; color: {color}; font-size: {size}px; font-weight: {600 if bold else 400};')
    return view


def button(text, primary=False):
    view = QPushButton(text)
    view.setMinimumHeight(48)
    view.setCursor(Qt.PointingHandCursor)
    view.setStyleSheet(f"""
        QPushButton {{ background: {'#D5E7FF' if primary else '#202D3E'};
            color: {'#112339' if primary else '#E8EEF7'}; border: 2px solid transparent;
            border-radius: 24px; padding: 0 20px; font-size: 14px; font-weight: 600; }}
        QPushButton:enabled:hover {{ background: {'#E9F2FF' if primary else '#2C3D53'}; }}
        QPushButton:enabled:pressed {{ background: {'#B6CFF0' if primary else '#354A62'}; }}
        QPushButton:focus {{ border: 2px dashed {"#112339" if primary else "#D5E7FF"}; }}
        QPushButton:disabled {{ background: {'#D5E7FF' if primary else '#202D3E'}; color: {'#334D69' if primary else '#A7B5C8'}; }}
        QPushButton[unavailable="true"] {{ background: #202D3E; color: #ACBCD0; border: 1px solid #8496AC; }}
        QPushButton::menu-indicator {{ image: none; width: 0; }}
    """)
    return view


def build_ui(window, PageEdit):
    window.resize(1280, 820)
    window.setMinimumSize(900, 640)
    main = QWidget()
    main.setObjectName('presentationWorkspace')
    main.setStyleSheet('QWidget#presentationWorkspace {background: #0C121C;}')
    window.setCentralWidget(main)
    layout = QVBoxLayout(main)
    layout.setContentsMargins(28, 24, 28, 18)
    layout.setSpacing(20)

    top = QHBoxLayout()
    top.setSpacing(16)
    file_heading = QVBoxLayout()
    file_heading.setSpacing(4)
    window.file_label = label('발표할 PDF를 열어 주세요', 15, '#D2DCEC', True)
    window.file_label.setTextFormat(Qt.PlainText)
    window.file_label.setMinimumWidth(0)
    window.file_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
    file_heading.addWidget(window.file_label)
    window.display_status = label('발표 모니터 · 자동 선택', 12, '#9DADC1')
    window.display_status.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
    file_heading.addWidget(window.display_status)
    top.addLayout(file_heading, 1)
    window.screen_button = button('발표 모니터: 확인 중  ▾')
    window.screen_button.setAccessibleName('발표 모니터 선택')
    window.screen_button.setToolTip('청중에게 표시할 모니터를 선택합니다.')
    window.screen_menu = QMenu(window.screen_button)
    window.screen_menu.setStyleSheet('''
        QMenu { background: #202D3E; color: #E8EEF7; border: 1px solid #36465D;
                border-radius: 4px; padding: 8px 0; font-size: 14px; }
        QMenu::item { background: transparent; min-height: 48px; padding: 0 24px 0 16px; border: none; }
        QMenu::item:selected { background: #34455C; color: #FFFFFF; }
        QMenu::item:checked { color: #80CBC4; }
        QMenu::indicator { width: 0; height: 0; image: none; }
        QMenu::icon { padding-left: 12px; }
    ''')
    window.screen_button.setMenu(window.screen_menu)
    top.addWidget(window.screen_button)
    window.btn_presentation = button('발표 시작', primary=True)
    window.btn_presentation.setStyleSheet(window.btn_presentation.styleSheet() + """
        QPushButton[danger="true"] { background: #FFB4AB; color: #690005; }
        QPushButton[danger="true"]:enabled:hover { background: #FFC4BD; }
        QPushButton[danger="true"]:enabled:pressed { background: #EFA79F; }
        QPushButton[danger="true"]:focus { border: 2px dashed #690005; }
    """)
    window.btn_presentation.clicked.connect(window.toggle_presentation)
    top.addWidget(window.btn_presentation)
    window.btn_open = button('PDF 파일 열기', primary=True)
    window.btn_open.setToolTip('PDF 파일 열기 · Ctrl+O')
    window.btn_open.clicked.connect(window.open_pdf_dialog)
    top.addWidget(window.btn_open)
    layout.addLayout(top)

    stage = AdjustableSplitter(Qt.Horizontal)
    window.stage_splitter = stage
    stage.setAccessibleName("현재 화면과 다음 페이지 비율 조절")
    for key, title, detail, emphasis in [('current', '현재 화면', '', True),
                                           ('next', '다음 페이지', '한발 앞서 확인하는 미리보기', False)]:
        card = QWidget()
        card.setObjectName(key + 'Card')
        card.setStyleSheet(f'QWidget#{key}Card {{background: #172232; border: 1px solid {"#34475D" if emphasis else "#26354A"}; border-radius: 20px;}}')
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 18, 18, 18)
        card_layout.setSpacing(10)
        row = QHBoxLayout()
        row.addWidget(label(('●  ' if emphasis else '') + title, 15, '#80CBC4' if emphasis else '#C2CFE1', True))
        row.addStretch()
        badge = label('CURRENT' if emphasis else 'UP NEXT', 10, '#7890A9', True)
        row.addWidget(badge)
        card_layout.addLayout(row)
        note = label(detail, 12, '#94A5BA')
        note.setFixedHeight(22)
        note.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        if key == 'next':
            window.preview_note = note
            note.clear()
        card_layout.addWidget(note)
        view = QLabel()
        view.setAlignment(Qt.AlignCenter)
        view.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        view.setAttribute(Qt.WA_StyledBackground, True)
        palette = view.palette()
        palette.setColor(QPalette.Window, QColor('#0C131E'))
        view.setPalette(palette)
        view.setAutoFillBackground(True)
        view.setStyleSheet('background-color: #0C131E; background-image: none; border-image: none; color: #96A8BF; border: none; border-radius: 8px; padding: 0; font-size: 15px;')
        if key == 'current':
            window.current_view = view
            view.setText('PDF 파일을 열어 주세요.')
        else:
            window.next_view = view
            window.preview_overlay = QLabel(view)
            window.preview_overlay.setAlignment(Qt.AlignCenter)
            window.preview_overlay.setWordWrap(True)
            window.preview_overlay.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            window.preview_overlay.setStyleSheet('background-color: rgba(12,19,30,240); color: #D5E7FF; font-size: 18px; font-weight: 600; padding: 16px; border-radius: 8px;')
            window.preview_overlay.hide()
            view.setText('PDF 파일을 열어 주세요.')
        card_layout.addWidget(view, 1)
        card.setMinimumSize(200, 180)
        stage.addWidget(card)
    stage.setSizes([700, 400])
    stage.setStretchFactor(0, 7)
    stage.setStretchFactor(1, 4)

    dock = NavigationDock(window)
    window.navigation_dock = dock
    dock.setObjectName('navigationDock')
    dock.setStyleSheet('QWidget#navigationDock {background: #172232; border: 1px solid #2D3D53; border-radius: 20px;}')
    dock_layout = QVBoxLayout(dock)
    dock_layout.setSizeConstraint(QLayout.SetNoConstraint)
    dock_layout.setContentsMargins(20, 14, 20, 12)
    dock_layout.setSpacing(12)
    controls = QHBoxLayout()
    controls.setSpacing(12)
    window.btn_prev = button('←  이전', primary=True)
    window.btn_prev.setAccessibleName('이전 페이지')
    window.btn_prev.clicked.connect(lambda: (window.prev_page(), window.setFocus()))
    window.btn_next = button('다음  →', primary=True)
    window.btn_next.setAccessibleName('다음 페이지')
    window.btn_next.clicked.connect(lambda: (window.next_page(), window.setFocus()))
    controls.addWidget(window.btn_prev)
    window.page_info_layout = QHBoxLayout()
    window.page_info_layout.setSpacing(10)
    window.lbl_prefix = label('페이지', 13)
    window.page_info_layout.addWidget(window.lbl_prefix)
    window.edit_page = PageEdit('-')
    window.edit_page.setFixedSize(86, 48)
    window.edit_page.setAlignment(Qt.AlignCenter)
    window.edit_page.setValidator(QIntValidator(1, 2147483647, window.edit_page))
    window.edit_page.setToolTip('페이지 번호 입력 후 Enter · Esc 또는 여백 클릭으로 취소')
    window.edit_page.setAccessibleName('이동할 페이지 번호')
    window.edit_page.setEnabled(False)
    window.edit_page.setStyleSheet('''
        QLineEdit {background: #0D1724; color: #80CBC4; border: 2px solid #34475D;
                   border-radius: 12px; padding: 0; font-size: 25px; font-weight: 600;}
        QLineEdit:hover {border-color: #80CBC4;}
        QLineEdit:focus {border-color: #34475D;}
    ''')
    window.edit_page.focusInSignal.connect(window.disable_shortcuts)
    window.edit_page.focusOutSignal.connect(window.enable_shortcuts)
    window.edit_page.cancelRequested.connect(window.cancel_page_edit)
    window.edit_page.returnPressed.connect(window.jump_to_page_inline)
    window.edit_page.focusOutSignal.connect(window.restore_page_text)
    window.page_info_layout.addWidget(window.edit_page)
    window.lbl_suffix = label('/ -', 16, '#D2DCEC')
    window.page_info_layout.addWidget(window.lbl_suffix)
    page_box = QWidget()
    window.page_box = page_box
    page_box.setFixedWidth(210)
    page_box.setStyleSheet("background: transparent; border: none;")
    page_box.setLayout(window.page_info_layout)
    window.page_info_layout.setContentsMargins(0, 0, 0, 0)
    controls.addWidget(page_box)
    controls.addWidget(window.btn_next)
    controls.addStretch()
    window.lbl_remaining = label('남은 페이지  —', 14, '#C2CFE1')
    controls.addWidget(window.lbl_remaining)
    dock_layout.addLayout(controls)
    window.page_progress = QProgressBar()
    window.page_progress.setRange(0, 100)
    window.page_progress.setValue(0)
    window.page_progress.setTextVisible(False)
    window.page_progress.setFixedHeight(3)
    window.page_progress.setStyleSheet('QProgressBar {background: #2A394E; border: none; border-radius: 1px;} QProgressBar::chunk {background: #80CBC4; border-radius: 1px;}')
    dock_layout.addWidget(window.page_progress)
    for view in (window.btn_prev, window.btn_next, window.edit_page, window.lbl_prefix, window.lbl_suffix, window.lbl_remaining):
        view.base_touch_style = view.styleSheet()
    dock.setMinimumHeight(112)
    window.workspace_splitter = AdjustableSplitter(Qt.Vertical)
    window.workspace_splitter.setAccessibleName('슬라이드와 페이지 조작 영역 높이 조절')
    window.workspace_splitter.addWidget(stage)
    window.workspace_splitter.addWidget(dock)
    window.workspace_splitter.setStretchFactor(0, 1)
    window.workspace_splitter.setStretchFactor(1, 0)
    window.workspace_splitter.setSizes([560, 112])
    layout.addWidget(window.workspace_splitter, 1)
    stage.splitterMoved.connect(window.refresh_layout)
    window.workspace_splitter.splitterMoved.connect(window.refresh_layout)

    footer = QHBoxLayout()
    footer.addWidget(label('← ↑ 이전    → ↓ 다음    ·    번호 입력 후 Enter로 이동', 12, '#8697AE'))
    footer.addStretch()
    credits = QVBoxLayout()
    credits.setSpacing(2)
    mail = label('개발 & 문의  freeballooning@gmail.com', 12, '#A4B4C9')
    mail.setAlignment(Qt.AlignRight)
    credits.addWidget(mail)
    window.version_label = label('ver.2.4', 10, '#778499')
    window.version_label.setAlignment(Qt.AlignRight)
    credits.addWidget(window.version_label)
    footer.addLayout(credits)
    layout.addLayout(footer)
    window.statusBar().setSizeGripEnabled(False)
    window.statusBar().setStyleSheet('QStatusBar {background: #0C121C; color: #AFC0D6; font-size: 12px; border: none;}')
    window.statusBar().setFixedHeight(24)
    sync_navigation(window)


def sync_navigation(window):
    loaded = window.pdf_doc is not None
    busy = window.navigation_pending
    target = window.navigation_target if window.navigation_target is not None else window.current_page
    prev_available = loaded and target > 0
    next_available = loaded and target < window.total_pages - 1
    unavailable(window.btn_prev, not prev_available)
    unavailable(window.btn_next, not next_available)
    window.btn_prev.setToolTip('이전 페이지' if prev_available else '첫 페이지입니다.' if loaded else 'PDF를 열어 주세요.')
    window.btn_next.setToolTip('다음 페이지' if next_available else '마지막 페이지입니다.' if loaded else 'PDF를 열어 주세요.')
    window.btn_prev.setEnabled(prev_available and not window.opening_pdf)
    window.btn_next.setEnabled(next_available and not window.opening_pdf)
    window.btn_open.setEnabled(not busy)
    can_start = loaded and not busy and not window.presentation_active
    active = window.presentation_active
    if window.btn_presentation.property('danger') != active:
        window.btn_presentation.setProperty('danger', active)
        window.btn_presentation.style().unpolish(window.btn_presentation)
        window.btn_presentation.style().polish(window.btn_presentation)
        window.btn_presentation.update()
    window.btn_presentation.setText('발표 정지' if active else '발표 시작')
    window.btn_presentation.setAccessibleName('프레젠테이션 정지' if active else '프레젠테이션 시작')
    window.btn_presentation.setToolTip('청중 화면을 숨깁니다. 제어 화면에서는 계속 준비할 수 있습니다.' if active else '현재 페이지부터 청중 화면에 표시합니다.')
    window.btn_presentation.setEnabled(active or can_start)
    unavailable(window.btn_presentation, not (active or can_start))
    state = '발표 중' if window.presentation_active else '발표 대기'
    window.display_status.setText(f'{state} · {window.screen_summary}')
    if loaded:
        name = Path(window.pdf_path).name
        metrics = window.file_label.fontMetrics()
        window.file_label.setText(metrics.elidedText(name, Qt.ElideMiddle, max(100, window.file_label.width())))
        window.file_label.setToolTip(window.pdf_path)
        window.page_progress.setValue(round(100 * window.current_page / (window.total_pages - 1)) if window.total_pages > 1 else 0)


def sync_screen(window, target, presenter_screen):
    mode = '전체 화면' if target != presenter_screen else '창 모드'
    chosen = '자동' if window.selected_screen is None else '선택'
    name = target.name() or '모니터'
    caption = f'발표 모니터: {name}'
    # QPushButton treats ampersands as shortcut markers; keep monitor names literal.
    window.screen_button.setText(caption.replace('&', '&&') + '  ▾')
    window.screen_button.setAccessibleName(caption)
    window.screen_button.setToolTip(f'{caption} ({chosen} 선택)\n청중에게 표시할 모니터를 선택합니다.')
    window.screen_summary = f'{chosen} · {name} · {mode}'
    sync_navigation(window)
    window.display_status.setToolTip('다른 모니터: 전체 화면 / 같은 모니터: 창 모드')
