"""Opt-in packaged runtime check; never runs in normal presentation mode."""
import json
import tempfile
import time
from pathlib import Path

import pymupdf
from PyQt5.QtCore import QTimer, Qt, QEvent, QPointF
from PyQt5.QtGui import QFontDatabase, QMouseEvent, QKeyEvent


def start_diagnostics(app, window, output, font_ids):
    directory = tempfile.TemporaryDirectory()
    pdf_path = str(Path(directory.name) / 'check.pdf')
    with pymupdf.open() as doc:
        for number in range(3):
            page = doc.new_page(width=595.28, height=841.89)
            page.draw_rect(page.rect, color=None, fill=(0, 0, 0))
        doc.save(pdf_path)
    timer = QTimer(window)
    deadline = time.monotonic() + 30
    phase = [0]

    def finish(ok, detail):
        timer.stop()
        families = sorted({family for fid in font_ids for family in QFontDatabase.applicationFontFamilies(fid)})
        Path(output).write_text(json.dumps({'ok': ok, 'detail': detail, 'font_count': len(font_ids),
                                          'font_families': families}, ensure_ascii=False), encoding='utf-8')
        window.close()
        directory.cleanup()
        app.exit(0 if ok else 1)

    def tick():
        if time.monotonic() > deadline:
            finish(False, 'Rendering timeout')
        elif phase[0] == 0:
            if not window.audience_window.isHidden():
                finish(False, 'Audience visible before PDF load')
                return
            phase[0] = 1
            window.load_pdf(pdf_path)
        elif not window.navigation_pending and not window.jobs and window.pdf_doc is not None:
            if phase[0] == 1:
                if window.presentation_active or not window.audience_window.isHidden():
                    finish(False, 'PDF started presentation automatically')
                    return
                window.refresh_controller_layout()
                central = window.centralWidget()
                if not central.rect().contains(window.btn_open.mapTo(central, window.btn_open.rect().bottomRight())):
                    finish(False, 'Controller layout overflow after DPI reflow')
                    return
                window.activateWindow()
                window.edit_page.setFocus()
                if not window.edit_page.hasFocus():
                    finish(False, 'Page edit did not receive focus')
                    return
                for event_type in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
                    event = QMouseEvent(event_type, QPointF(1, 1), Qt.LeftButton,
                                        Qt.LeftButton if event_type == QEvent.MouseButtonPress else Qt.NoButton,
                                        Qt.NoModifier)
                    app.sendEvent(window.navigation_dock, event)
                if window.edit_page.hasFocus():
                    finish(False, 'Click outside page edit did not release focus')
                    return
                name = window.resolve_screens()[1].name() or '모니터'
                if window.screen_button.text() != '발표 모니터: ' + name.replace('&', '&&') + '  ▾':
                    finish(False, 'Selected monitor caption mismatch')
                    return
                window.start_presentation()
                if not window.presentation_active or window.audience_window.isHidden():
                    finish(False, 'Presentation start failed')
                    return
                app.sendEvent(window.btn_presentation, QEvent(QEvent.Leave))
                color = window.btn_presentation.grab().toImage().pixelColor(14, window.btn_presentation.height()//2).name()
                if color != '#ffb4ab':
                    finish(False, 'Stop button danger color mismatch: ' + color)
                    return
                window.grab().save(str(Path(output).with_suffix('.png')))
                for code, caption in [('en', 'Stop presentation'), ('ja', '発表停止'),
                                      ('zh_CN', '停止演示'), ('ko', '발표 정지')]:
                    window.language_actions[code].trigger()
                    if (window.btn_presentation.text() != caption or window.audience_window.isHidden()
                            or window.current_page != 0):
                        finish(False, 'Live language selection failed: ' + code)
                        return
                window.stop_presentation()
                if window.btn_presentation.property('danger'):
                    finish(False, 'Start button still has danger color')
                    return
                if window.presentation_active or not window.audience_window.isHidden():
                    finish(False, 'Presentation stop failed')
                    return
                phase[0] = 2
                handle = window.stage_splitter.handle(1)
                handle.setFocus(Qt.MouseFocusReason)
                point = QPointF(handle.rect().center())
                for event_type in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
                    app.sendEvent(handle, QMouseEvent(event_type, point, Qt.LeftButton,
                                  Qt.LeftButton if event_type == QEvent.MouseButtonPress else Qt.NoButton,
                                  Qt.NoModifier))
                if handle.hasFocus() or app.focusWidget() is None:
                    finish(False, 'Splitter retained keyboard focus after mouse release')
                    return
                for event_type in (QEvent.KeyPress, QEvent.KeyRelease):
                    app.sendEvent(app.focusWidget(), QKeyEvent(event_type, Qt.Key_Right, Qt.NoModifier))
            else:
                finish(window.current_page == 1 and window.audience_window.isHidden() and len(font_ids) == 2 and {'Regular', 'SemiBold'}.issubset(set(QFontDatabase().styles('Pretendard'))), 'PDF open, worker rendering, page navigation, bundled fonts, presentation start/stop, stopped navigation, page edit outside click, monitor caption, stop button color, arrow navigation after splitter release, controller DPI reflow, four live UI languages')

    timer.timeout.connect(tick)
    timer.start(50)
