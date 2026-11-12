import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['QT_QPA_FONTDIR'] = os.path.join(os.environ.get('WINDIR', 'C:/Windows'), 'Fonts')
import PyQt5
os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = os.path.join(os.path.dirname(PyQt5.__file__), 'Qt5', 'plugins', 'platforms')

import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import pymupdf as fitz
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QPixmap, QFont
from PyQt5.QtCore import Qt
import pdf_presenter_fixed as presenter


class PresenterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)
        font_family = presenter.ui_font_family()
        cls.app.setFont(QFont(font_family, 12))
        cls.temp = tempfile.TemporaryDirectory()
        presenter.apply_session_theme(cls.app, font_family, Path(cls.temp.name) / 'theme')
        cls.path = str(Path(cls.temp.name) / 'slides.pdf')
        with fitz.open() as doc:
            for number in range(3):
                page = doc.new_page(width=960, height=540)
                page.insert_text((40, 50), f'Slide {number + 1}')
            doc.save(cls.path)
            cls.encrypted = str(Path(cls.temp.name) / 'encrypted.pdf')
            doc.save(cls.encrypted, encryption=fitz.PDF_ENCRYPT_AES_256,
                     owner_pw='owner', user_pw='secret')

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()
        from PyQt5.QtGui import QFontDatabase
        QFontDatabase.removeAllApplicationFonts()
        presenter._bundled_font_ids.clear()

    def setUp(self):
        self.system_ui = patch.object(presenter, "system_language", return_value="ko").start()
        self.addCleanup(patch.stopall)
        self.window = presenter.PresenterWindow()
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.app.processEvents()
        from PyQt5 import sip
        sip.delete(self.window.audience_window)
        sip.delete(self.window)
        self.app.processEvents()

    def wait_for(self, predicate):
        end = time.monotonic() + 15
        while time.monotonic() < end:
            self.app.processEvents()
            if predicate():
                return
            time.sleep(0.01)
        self.fail('Timed out waiting for rendering')

    def load(self):
        self.window.load_pdf(self.path)
        self.wait_for(lambda: not self.window.navigation_pending and self.window.pdf_doc is not None)
        self.wait_for(lambda: not self.window.jobs)

    def test_live_language_selection_preserves_presentation_and_edit(self):
        self.load()
        w = self.window
        w.next_page()
        w.start_presentation()
        worker, document, pixmap = w.worker, w.pdf_doc, w.cached_curr_pixmap.cacheKey()
        for code, name, stop in [('en', 'Open PDF', 'Stop presentation'), ('ja', 'PDF を開く', '発表停止'),
                                 ('zh_CN', '打开 PDF', '停止演示'), ('ko', 'PDF 파일 열기', '발표 정지')]:
            w.language_actions[code].trigger()
            self.assertEqual(w.btn_open.text(), name)
            self.assertEqual(w.btn_presentation.text(), stop)
            self.assertEqual(w.current_page, 1)
            self.assertTrue(w.presentation_active)
            self.assertTrue(w.audience_window.isVisible())
            self.assertIs(w.worker, worker)
            self.assertIs(w.pdf_doc, document)
            self.assertEqual(w.cached_curr_pixmap.cacheKey(), pixmap)
            self.assertEqual([k for k, a in w.language_actions.items() if a.isChecked()], [code])
        w.stop_presentation()
        w.edit_page.setFocus()
        w.edit_page.setText('3')
        w.select_language('en')
        self.assertEqual(w.edit_page.text(), '3')

    def test_language_is_session_only_and_menu_has_four_choices(self):
        from PyQt5 import sip
        w = self.window
        self.assertEqual(set(w.language_actions), {'ko', 'en', 'ja', 'zh_CN'})
        self.assertEqual(len(w.language_menu.actions()), 4)
        w.language_actions['en'].trigger()
        self.assertEqual(w.language, 'en')
        for system in ('ko', 'ja', 'en'):
            self.system_ui.return_value = system
            new = presenter.PresenterWindow()
            try:
                self.assertEqual(new.language, system)
                self.assertTrue(new.language_actions[system].isChecked())
            finally:
                new.close(); sip.delete(new.audience_window); sip.delete(new)

    def test_windows_language_ids(self):
        from presenter_i18n import language_from_langid
        for value, expected in [(0x0412,'ko'),(0x0809,'en'),(0x0411,'ja'),(0x0804,'zh_CN'),
                                (0x0404,'en'),(0x0c04,'en'),(0x1004,'zh_CN'),(0x040c,'en'),(0,'en')]:
            self.assertEqual(language_from_langid(value), expected)

    def test_language_button_shares_version_row(self):
        w = self.window
        w.resize(900, 640)
        self.app.processEvents()
        for language in w.language_actions:
            w.select_language(language)
            self.app.processEvents()
            button = w.language_button.geometry()
            version = w.version_label.geometry()
            self.assertLessEqual(abs(button.center().y()-version.center().y()), 2)
            self.assertLessEqual(version.left()-button.right(), 8)
            self.assertLess(button.right(), version.left())

    def test_translates_pending_preview_and_errors_without_translating_user_text(self):
        w = self.window
        w.set_note('{page}페이지 준비 중 · {shown}페이지 표시 중', {'page': 4, 'shown': 2})
        w.show_error('파일을 열 수 없습니다: {error}', error='비밀번호가 설정된 보안 PDF는 열 수 없습니다.')
        w.select_language('en')
        self.assertEqual(w.preview_note.text(), 'Preparing page 4 · Showing page 2')
        self.assertIn('Password-protected', w.statusBar().currentMessage())
        w.show_error('파일을 열 수 없습니다: {error}', error='C:/보고서/{demo}.pdf')
        w.select_language('zh_CN')
        self.assertEqual(w.statusBar().currentMessage(), '无法打开文件：C:/보고서/{demo}.pdf')

    def test_translations_preserve_all_placeholder_names(self):
        from presenter_i18n import CATALOG, LANGUAGES
        from string import Formatter
        def fields(value): return {f for _,f,_,_ in Formatter().parse(value) if f is not None}
        for key, translations in CATALOG.items():
            self.assertEqual(set(translations), set(LANGUAGES))
            for text in translations.values():
                self.assertTrue(text.strip())
                self.assertEqual(fields(key), fields(text))

    def test_real_render_navigation_cache_and_last_page_style(self):
        self.load()
        w = self.window
        style = w.next_view.styleSheet()
        self.assertEqual(w.total_pages, 3)
        self.assertFalse(w.audience_window.current_pixmap.isNull())
        prefetched = w.cached_next_pixmap.cacheKey()
        w.next_page()
        self.assertEqual(w.current_page, 1)
        self.assertEqual(w.cached_curr_pixmap.cacheKey(), prefetched)
        self.assertFalse(w.navigation_pending)
        self.wait_for(lambda: not w.jobs)
        w.next_page()
        self.assertEqual(w.next_view.text(), '마지막 페이지입니다.')
        w.prev_page()
        self.assertEqual(w.next_view.styleSheet(), style)
        self.assertIsNotNone(w.cached_next_pixmap)
        self.assertEqual(w.current_page, 1)
        self.assertLessEqual(len(w.page_cache), 3)
        evidence = Path(__file__).with_name('verification')
        evidence.mkdir(exist_ok=True)
        self.app.processEvents()
        w.grab().save(str(evidence / 'presenter.png'))

    def test_stalled_worker_unlocks_controls_and_allows_retry(self):
        self.load()
        w = self.window
        before = w.audience_window.current_pixmap.cacheKey()
        with patch.object(w.requests, 'put'):
            w.request_render(w.pdf_doc, w.pdf_path, 2, 'navigate')
        w.last_render_progress = time.monotonic() - 61
        w.poll_render_results()
        self.assertIsNone(w.worker)
        self.assertFalse(w.navigation_pending)
        self.assertTrue(w.btn_open.isEnabled())
        self.assertEqual(w.current_page, 0)
        self.assertEqual(w.audience_window.current_pixmap.cacheKey(), before)
        w.navigate_to(2)
        self.wait_for(lambda: not w.navigation_pending)
        self.assertEqual(w.current_page, 2)

    def test_render_channel_failure_preserves_page_and_allows_retry(self):
        self.load()
        w = self.window
        before = w.audience_window.current_pixmap.cacheKey()
        with patch.object(w.requests, 'put'):
            w.request_render(w.pdf_doc, w.pdf_path, 2, 'navigate')
        with patch.object(w.results, 'get_nowait', side_effect=OSError('broken pipe')):
            w.poll_render_results()
        self.assertFalse(w.navigation_pending)
        self.assertIsNone(w.worker)
        self.assertEqual(w.audience_window.current_pixmap.cacheKey(), before)
        w.navigate_to(2)
        self.wait_for(lambda: not w.navigation_pending)
        self.assertEqual(w.current_page, 2)

    def make_long_pdf(self):
        path = str(Path(self.temp.name) / 'long-slides.pdf')
        with fitz.open() as doc:
            for number in range(25):
                page = doc.new_page(width=640, height=360)
                page.insert_text((40, 50), f'Long slide {number + 1}')
            doc.save(path)
        return path

    def test_prefetch_window_moves_and_cached_navigation_is_immediate(self):
        w = self.window
        with patch.object(w, 'render_size', return_value=(640, 360)):
            w.load_pdf(self.make_long_pdf())
            self.wait_for(lambda: w.pdf_doc is not None and not w.jobs)
            self.assertEqual({p for p, size in w.page_cache}, set(range(11)))
            w.navigate_to(5)
            self.assertFalse(w.navigation_pending)
            self.assertEqual(w.current_page, 5)
            self.wait_for(lambda: not w.jobs)
            self.assertEqual({p for p, size in w.page_cache}, set(range(2, 16)))
            with patch.object(w, 'schedule_prefetch'):
                with patch.object(w, 'request_render') as request:
                    w.navigate_to(4)
                    self.assertEqual(w.current_page, 4)
                    self.assertFalse(w.navigation_pending)
                    request.assert_not_called()
            self.assertLessEqual(w.cache_bytes(), w.cache_budget_bytes)

    def test_prefetch_budget_replacement_and_close_release_images(self):
        w = self.window
        w.cache_budget_bytes = 2 * 1024 * 1024
        with patch.object(w, 'render_size', return_value=(640, 360)):
            w.load_pdf(self.make_long_pdf())
            self.wait_for(lambda: w.pdf_doc is not None and not w.jobs)
            self.assertLessEqual(w.cache_bytes(), w.cache_budget_bytes)
            self.assertLess(len(w.page_cache), 11)
            old = w.pdf_doc
            w.load_pdf(self.path)
            self.wait_for(lambda: w.pdf_doc is not old and not w.jobs)
            self.assertTrue(old.is_closed)
            self.assertTrue(all(page < 3 for page, size in w.page_cache))
            w.close()
            self.assertFalse(w.page_cache)
            self.assertIsNone(w.cached_curr_pixmap)
            self.assertIsNone(w.cached_next_pixmap)
            self.assertIsNone(w.audience_window.current_pixmap)
            self.assertIsNone(w.worker)

    def test_foreground_request_reuses_worker_and_waits_for_one_preview(self):
        self.load()
        w = self.window
        w.page_cache.pop((2, w.render_size()), None)
        with patch.object(w.requests, 'put'):
            w.request_render(w.pdf_doc, w.pdf_path, 1, 'preview')
        old_worker = w.worker
        w.navigate_to(2)
        self.assertIs(w.worker, old_worker)
        self.assertEqual(w.navigation_target, 2)
        job_id, job = next(iter(w.jobs.items()))
        del w.jobs[job_id]
        w.finish_render(job, self.image_payload(), None)
        self.wait_for(lambda: not w.navigation_pending)
        self.assertEqual(w.current_page, 2)
        self.assertIs(w.worker, old_worker)

    @staticmethod
    def image_payload():
        from PyQt5.QtGui import QImage
        image = QImage(320, 180, QImage.Format_RGB888)
        image.fill(Qt.red)
        return (image.bits().asstring(image.byteCount()), image.width(), image.height(), image.bytesPerLine())

    def test_jump_then_left_uses_late_result_for_next_preview_only(self):
        from PyQt5.QtTest import QTest
        w = self.window
        with tempfile.TemporaryDirectory() as td:
            path = str(Path(td) / 'colored.pdf')
            with fitz.open() as doc:
                for number in range(1, 49):
                    page = doc.new_page(width=128, height=96)
                    page.draw_rect(page.rect, color=None, fill=(number * 5 / 255, 0, 0))
                doc.save(path)
            try:
                for language in ('ko', 'en', 'ja', 'zh_CN', 'ko'):
                    w.load_pdf(path)
                    self.wait_for(lambda: not w.opening_pdf and not w.jobs)
                    w.select_language(language)
                    w.start_presentation()
                    self.app.processEvents()
                    QTest.mouseClick(w.edit_page, Qt.LeftButton)
                    w.edit_page.selectAll()
                    QTest.keyClicks(w.edit_page, '12')
                    QTest.keyClick(w.edit_page, Qt.Key_Return)
                    QTest.keyClick(w, Qt.Key_Left)
                    self.wait_for(lambda: not w.jobs and not w.navigation_pending)
                    self.assertEqual((w.current_page, w.displayed_preview_page), (10, 11))
                    self.assertTrue(w.presentation_active)
                    for pix, expected in [(w.cached_curr_pixmap, 55), (w.audience_window.current_pixmap, 55),
                                          (w.next_view.pixmap(), 60)]:
                        image = pix.toImage()
                        self.assertAlmostEqual(image.pixelColor(image.width()//2, image.height()//2).red(), expected, delta=1)
                    self.assertEqual(w.preview_note.text(), '')
                    self.assertFalse(w.preview_overlay.isVisible())
            finally:
                w.close()

    def test_preview_is_promoted_without_duplicate_request(self):
        self.load()
        w = self.window
        key = (1, w.render_size())
        w.page_cache.pop(key)
        with patch.object(w.requests, 'put'):
            w.request_render(w.pdf_doc, w.pdf_path, 1, 'preview')
        worker, serial = w.worker, w.job_serial
        w.next_page()
        self.assertEqual(w.job_serial, serial)
        self.assertIs(w.worker, worker)
        job_id, job = next(iter(w.jobs.items()))
        self.assertEqual(job[3], 'navigate')
        del w.jobs[job_id]
        w.finish_render(job, self.image_payload(), None)
        self.assertEqual(w.current_page, 1)
        self.assertFalse(w.navigation_pending)

    def test_presentation_defaults_to_hidden_and_buttons_control_visibility(self):
        from PyQt5.QtTest import QTest
        w = self.window
        self.assertTrue(w.audience_window.isHidden())
        self.assertFalse(w.btn_presentation.isEnabled())
        self.assertFalse(w.btn_presentation.isEnabled())
        self.load()
        self.assertTrue(w.audience_window.isHidden())
        self.assertTrue(w.btn_presentation.isEnabled())
        self.assertEqual(w.btn_presentation.text(), '발표 시작')
        self.assertEqual(w.screen_button.text(), '발표 모니터: ' + (w.resolve_screens()[1].name() or '모니터').replace('&', '&&') + '  ▾')
        w.next_page()
        self.wait_for(lambda: not w.jobs)
        self.assertTrue(w.audience_window.isHidden())
        QTest.mouseClick(w.btn_presentation, Qt.LeftButton)
        self.assertTrue(w.presentation_active)
        self.assertTrue(w.audience_window.isVisible())
        self.assertEqual(w.audience_window.current_pixmap.cacheKey(), w.cached_curr_pixmap.cacheKey())
        self.assertEqual(w.btn_presentation.text(), '발표 정지')
        self.assertTrue(w.btn_presentation.isEnabled())
        QTest.mouseClick(w.btn_presentation, Qt.LeftButton)
        w.next_page()
        self.wait_for(lambda: not w.jobs)
        self.assertFalse(w.presentation_active)
        self.assertTrue(w.audience_window.isHidden())
        w.start_presentation()
        self.assertEqual(w.current_page, 2)
        self.assertTrue(w.audience_window.isVisible())

    def test_successful_pdf_replacement_returns_to_stopped_state(self):
        self.load()
        w = self.window
        w.start_presentation()
        w.load_pdf(self.path + '.missing')
        self.assertTrue(w.presentation_active)
        old = w.pdf_doc
        w.load_pdf(self.path)
        self.wait_for(lambda: w.pdf_doc is not old and not w.jobs)
        self.assertFalse(w.presentation_active)
        self.assertTrue(w.audience_window.isHidden())
        self.assertTrue(w.btn_presentation.isEnabled())

    def test_stop_during_render_does_not_reopen_audience(self):
        self.load()
        w = self.window
        w.start_presentation()
        w.page_cache.clear()
        w.next_page()
        self.assertTrue(w.btn_presentation.isEnabled())
        self.assertEqual(w.btn_presentation.text(), '발표 정지')
        w.btn_presentation.click()
        self.assertEqual(w.btn_presentation.text(), '발표 시작')
        self.wait_for(lambda: not w.navigation_pending)
        self.assertEqual(w.current_page, 1)
        self.assertTrue(w.audience_window.isHidden())

    def test_escape_cancels_page_edit_and_restores_navigation(self):
        from PyQt5.QtTest import QTest
        self.load()
        w = self.window
        w.edit_page.setFocus()
        w.edit_page.setText('999')
        QTest.keyClick(w.edit_page, Qt.Key_Escape)
        self.assertFalse(w.edit_page.hasFocus())
        self.assertEqual(w.edit_page.text(), '1')
        self.assertTrue(all(shortcut.isEnabled() for shortcut in w.shortcuts))
        QTest.keyClick(w, Qt.Key_Right)
        self.assertEqual(w.current_page, 1)

    def test_rapid_inputs_keep_latest_target_and_skip_obsolete_result(self):
        self.load()
        w = self.window
        w.page_cache.clear()
        with patch.object(w.requests, 'put'):
            w.request_render(w.pdf_doc, w.pdf_path, 1, 'preview')
        worker = w.worker
        w.next_page()
        w.next_page()
        w.prev_page()
        w.next_page()
        self.assertEqual(w.navigation_target, 2)
        self.assertEqual(len(w.jobs), 1)
        self.assertTrue(w.btn_prev.isEnabled())
        self.assertFalse(w.btn_next.isEnabled())
        job_id, job = next(iter(w.jobs.items()))
        del w.jobs[job_id]
        w.finish_render(job, self.image_payload(), None)
        self.assertEqual(w.current_page, 0)
        self.assertTrue(any(job[2] == 2 for job in w.jobs.values()))
        self.wait_for(lambda: not w.navigation_pending)
        self.assertEqual(w.current_page, 2)
        self.assertIs(w.worker, worker)

    def test_return_to_cached_page_ignores_late_navigation_result(self):
        self.load()
        w = self.window
        with patch.object(w.requests, 'put'):
            w.request_render(w.pdf_doc, w.pdf_path, 1, 'navigate')
        w.navigate_to(0)
        self.assertFalse(w.navigation_pending)
        job_id, job = next(iter(w.jobs.items()))
        del w.jobs[job_id]
        w.finish_render(job, self.image_payload(), None)
        self.assertEqual(w.current_page, 0)

    def test_same_screen_refresh_preserves_size_and_skips_render(self):
        self.load()
        w = self.window
        w.selected_screen = QApplication.primaryScreen()
        w.start_presentation()
        self.wait_for(lambda: not w.jobs)
        w.audience_window.resize(780, 560)
        w.audience_window.move(30, 40)
        geometry = w.audience_window.geometry()
        with patch.object(w, 'request_render') as render:
            w.setup_screens()
            w.refresh_screens()
            render.assert_not_called()
        self.assertEqual(w.audience_window.geometry(), geometry)
        w.stop_presentation()
        w.start_presentation()
        self.assertEqual(w.audience_window.geometry(), geometry)

    def test_4k_landscape_renders_at_native_resolution(self):
        with fitz.open() as doc:
            page = doc.new_page(width=1920, height=1080)
            pix = presenter.render_page(page, 3840, 2160)
            self.assertEqual((pix.width, pix.height), (3840, 2160))
        matrix = presenter.raster_matrix(fitz.Rect(0, 0, 7680, 4320), 7680, 4320)
        self.assertLessEqual(round(7680 * matrix.a) * round(4320 * matrix.d), 8_500_000)

    def test_old_resolution_failure_does_not_cancel_new_resolution_request(self):
        self.load()
        w = self.window
        w.navigation_target = 1
        w.navigation_pending = True
        old_size = w.render_size()
        with patch.object(w, 'render_size', return_value=(640, 480)), patch.object(w, 'request_render') as render:
            w.finish_render((w.pdf_doc, w.pdf_path, 1, 'navigate', old_size), None, 'obsolete resolution failed')
            self.assertEqual(w.navigation_target, 1)
            self.assertTrue(w.navigation_pending)
            render.assert_called_once_with(w.pdf_doc, w.pdf_path, 1, 'navigate')

    def test_late_failure_after_cached_navigation_is_ignored(self):
        self.load()
        w = self.window
        w.navigate_to(2)
        before = w.cached_curr_pixmap.cacheKey()
        with patch.object(w, 'show_error') as error:
            w.finish_render((w.pdf_doc, w.pdf_path, 1, 'navigate', w.render_size()), None, 'obsolete page failed')
            error.assert_not_called()
        self.assertEqual(w.current_page, 2)
        self.assertEqual(w.cached_curr_pixmap.cacheKey(), before)
        self.assertFalse(w.navigation_pending)

    def test_worker_reuses_document_and_reopens_on_new_token(self):
        import queue
        requests, results = queue.Queue(), queue.Queue()
        for serial, token in [(1, 100), (2, 100), (3, 101)]:
            requests.put((serial, self.path, 0, 320, 180, token))
        requests.put(None)
        real_open = presenter.fitz.open
        with patch.object(presenter.fitz, 'open', wraps=real_open) as opened:
            presenter.render_worker(requests, results)
        self.assertEqual(opened.call_count, 2)
        self.assertEqual(results.qsize(), 3)
        while not results.empty():
            self.assertIsNone(results.get()[2])

    def test_navigation_failure_preserves_number_and_audience(self):
        self.load()
        w = self.window
        before = w.cached_curr_pixmap.cacheKey()
        w.navigation_pending = True
        w.navigation_target = 1
        w.finish_render((w.pdf_doc, w.pdf_path, 1, 'navigate', w.render_size()), None, 'injected failure')
        self.assertEqual(w.current_page, 0)
        self.assertEqual(w.edit_page.text(), '1')
        self.assertEqual(w.audience_window.current_pixmap.cacheKey(), before)
        self.assertFalse(w.navigation_pending)

    def test_new_document_render_failure_preserves_old_document(self):
        self.load()
        w = self.window
        old = w.pdf_doc
        before = w.cached_curr_pixmap.cacheKey()
        candidate = fitz.open(self.path)
        w.navigation_pending = True
        w.finish_render((candidate, self.path, 0, 'open', w.render_size()), None, 'injected failure')
        self.assertIs(w.pdf_doc, old)
        self.assertFalse(old.is_closed)
        self.assertTrue(candidate.is_closed)
        self.assertEqual(w.audience_window.current_pixmap.cacheKey(), before)

    def test_preview_failure_does_not_block_current_page(self):
        self.load()
        w = self.window
        before = w.audience_window.current_pixmap.cacheKey()
        w.finish_render((w.pdf_doc, w.pdf_path, 1, 'preview', w.render_size()), None, 'injected preview failure')
        self.assertEqual(w.audience_window.current_pixmap.cacheKey(), before)
        self.assertEqual(w.next_view.text(), '미리보기를 표시할 수 없습니다.')
        w.next_page()
        self.assertEqual(w.current_page, 1)

    def test_missing_encrypted_and_invalid_files_keep_old_document(self):
        self.load()
        old = self.window.pdf_doc
        invalid = Path(self.temp.name) / 'invalid.pdf'
        invalid.write_bytes(b'not a pdf')
        for path in [str(invalid), self.encrypted, str(invalid) + '.missing']:
            self.window.load_pdf(path)
            self.assertIs(self.window.pdf_doc, old)
            self.assertFalse(old.is_closed)
            self.assertFalse(self.window.navigation_pending)

    def test_successful_replacement_closes_old_document(self):
        self.load()
        old = self.window.pdf_doc
        self.window.load_pdf(self.path)
        self.assertIs(self.window.pdf_doc, old)
        self.assertFalse(old.is_closed)
        self.wait_for(lambda: not self.window.navigation_pending)
        self.assertTrue(old.is_closed)
        self.assertIsNot(self.window.pdf_doc, old)

    def test_page_bounds_and_input(self):
        self.load()
        w = self.window
        w.prev_page()
        self.assertEqual(w.current_page, 0)
        w.edit_page.setText('999')
        w.jump_to_page_inline()
        self.assertEqual(w.edit_page.text(), '1')
        w.edit_page.setText('3')
        w.jump_to_page_inline()
        self.wait_for(lambda: not w.navigation_pending)
        self.assertEqual(w.current_page, 2)
        w.next_page()
        self.assertEqual(w.current_page, 2)

    def test_screen_menu_and_reopen_hidden_audience(self):
        w = self.window
        self.assertEqual(len(w.screen_actions.actions()), len(QApplication.screens()) + 1)
        screen = QApplication.primaryScreen()
        w.choose_screen(screen)
        self.assertIs(w.selected_screen, screen)
        w.audience_window.close()
        self.assertTrue(w.audience_window.isHidden())
        w.setup_screens()
        self.assertTrue(w.audience_window.isHidden())
        self.load()
        w.start_presentation()
        self.assertFalse(w.audience_window.isHidden())
        w.audience_window.close()
        self.assertFalse(w.presentation_active)
        w.next_page()
        self.assertTrue(w.audience_window.isHidden())
        w.choose_screen(None)
        self.assertIsNone(w.selected_screen)

    def test_preview_keeps_image_until_replacement_is_ready(self):
        self.load()
        w = self.window
        before = w.next_view.pixmap().toImage()
        w.page_cache.pop((2, w.render_size()), None)
        with patch.object(w, 'request_render') as request:
            w.next_page()
            self.app.processEvents()
            self.assertEqual(w.current_page, 1)
            self.assertEqual(w.next_view.pixmap().toImage(), before)
            self.assertEqual(w.next_view.text(), '')
            self.assertIn('3페이지 준비 중', w.preview_note.text())
            self.assertFalse(w.preview_overlay.isHidden())
            self.assertEqual('3페이지 준비 중', w.preview_overlay.text())
            w.grab().save(str(Path(__file__).with_name('verification') / 'presentation-preview-pending.png'))
            request.assert_called_once()
        # Deliver a different, completely rendered image in one step.
        from PyQt5.QtGui import QImage
        image = QImage(320, 180, QImage.Format_RGB888)
        image.fill(Qt.red)
        payload = (image.bits().asstring(image.byteCount()), image.width(),
                   image.height(), image.bytesPerLine())
        w.finish_render((w.pdf_doc, w.pdf_path, 2, 'preview', w.render_size()), payload, None)
        self.assertNotEqual(w.next_view.pixmap().toImage(), before)
        self.assertEqual(w.preview_note.text(), '')
        self.assertEqual(w.displayed_preview_page, 2)

    def test_stale_preview_result_does_not_replace_current_preview(self):
        self.load()
        w = self.window
        with patch.object(w, 'request_render'):
            w.next_page()
            w.commit_page(2, w.cached_curr_pixmap)
        from PyQt5.QtGui import QImage
        image = QImage(64, 64, QImage.Format_RGB888)
        image.fill(Qt.red)
        payload = (image.bits().asstring(image.byteCount()), 64, 64, image.bytesPerLine())
        w.finish_render((w.pdf_doc, w.pdf_path, 2, 'preview', w.render_size()), payload, None)
        self.assertEqual(w.next_view.text(), '마지막 페이지입니다.')
        self.assertIsNone(w.cached_next_pixmap)

    def test_material_menu_keyboard_and_item_height(self):
        from PyQt5.QtTest import QTest
        w = self.window
        menu = w.screen_menu
        menu.popup(w.screen_button.mapToGlobal(w.screen_button.rect().bottomLeft()))
        self.app.processEvents()
        self.assertTrue(menu.isVisible())
        for action in w.screen_actions.actions():
            self.assertGreaterEqual(menu.actionGeometry(action).height(), 48)
        menu.setActiveAction(w.screen_actions.actions()[1])
        QTest.keyClick(menu, Qt.Key_Return)
        self.app.processEvents()
        self.assertIs(w.selected_screen, QApplication.screens()[0])
        menu.popup(w.screen_button.mapToGlobal(w.screen_button.rect().bottomLeft()))
        self.app.processEvents()
        evidence = Path(__file__).with_name('verification')
        evidence.mkdir(exist_ok=True)
        menu.grab().save(str(evidence / 'screen-menu.png'))
        QTest.keyClick(menu, Qt.Key_Escape)
        self.assertFalse(menu.isVisible())

    def test_worker_crash_preserves_presentation_and_allows_retry(self):
        self.load()
        w = self.window
        old = w.pdf_doc
        w.worker.terminate()
        w.worker.join(timeout=3)
        w.poll_render_results()
        self.assertIsNone(w.worker)
        self.assertIs(w.pdf_doc, old)
        w.navigate_to(2)
        self.wait_for(lambda: not w.navigation_pending)
        self.assertEqual(w.current_page, 2)

    def test_close_while_loading_stops_worker(self):
        self.window.load_pdf(self.path)
        process = self.window.worker
        self.window.close()
        self.assertIsNone(self.window.worker)
        self.assertTrue(process._closed)
        self.assertFalse(self.window.jobs)

    def test_redesigned_controls_and_compact_layout(self):
        from PyQt5.QtTest import QTest
        self.assertFalse(self.window.btn_prev.isEnabled())
        self.assertFalse(self.window.btn_next.isEnabled())
        self.load()
        w = self.window
        self.assertIn('slides.pdf', w.file_label.text())
        self.assertFalse(w.btn_prev.isEnabled())
        self.assertTrue(w.btn_next.isEnabled())
        QTest.mouseClick(w.btn_next, Qt.LeftButton)
        self.wait_for(lambda: not w.jobs)
        self.assertEqual(w.current_page, 1)
        self.assertEqual(w.page_progress.value(), 50)
        QTest.mouseClick(w.btn_prev, Qt.LeftButton)
        self.wait_for(lambda: not w.jobs)
        self.assertEqual(w.current_page, 0)
        self.assertFalse(w.edit_page.hasFocus())
        w.resize(900, 640)
        QTest.qWait(150)
        self.app.processEvents()
        self.assertLessEqual(w.width(), 960)
        self.assertTrue(w.edit_page.isVisible())
        self.assertTrue(w.btn_next.isVisible())
        evidence = Path(__file__).with_name('verification')
        w.grab().save(str(evidence / 'compact-ui.png'))

    def test_2_1_button_background_and_removed_labels(self):
        from PyQt5.QtWidgets import QLabel
        w = self.window
        texts = [item.text() for item in w.findChildren(QLabel)]
        for removed in ['P', 'PDF 발표자 도구', '발표에 집중할 수 있는 나만의 공간', '청중에게 표시되는 페이지']:
            self.assertNotIn(removed, texts)
        for view in [w.btn_prev, w.btn_next, w.btn_open]:
            for enabled in [True, False, True, False]:
                view.setEnabled(enabled)
                self.app.processEvents()
                image = view.grab().toImage()
                self.assertEqual(image.pixelColor(14, image.height()//2).name(), '#202d3e' if view.property('unavailable') else '#d5e7ff')
        for view in [w.current_view, w.next_view]:
            image = view.grab().toImage()
            self.assertEqual(image.pixelColor(14, 14).name(), '#0c131e')

    def test_boundary_button_styles_and_zero_initial_progress(self):
        self.load()
        w = self.window
        self.assertTrue(w.btn_prev.property('unavailable'))
        self.assertFalse(w.btn_next.property('unavailable'))
        self.assertEqual(w.page_progress.value(), 0)
        w.next_page()
        self.wait_for(lambda: not w.jobs)
        self.assertFalse(w.btn_prev.property('unavailable'))
        self.assertFalse(w.btn_next.property('unavailable'))
        w.navigation_pending = True
        w.sync_ui()
        self.assertFalse(w.btn_prev.property('unavailable'))
        self.assertFalse(w.btn_next.property('unavailable'))
        w.navigation_pending = False
        w.next_page()
        self.wait_for(lambda: not w.jobs)
        self.assertTrue(w.btn_next.property('unavailable'))
        self.assertEqual(w.page_progress.value(), 100)
        single = str(Path(self.temp.name) / 'single.pdf')
        with fitz.open() as doc:
            doc.new_page()
            doc.save(single)
        w.load_pdf(single)
        self.wait_for(lambda: not w.navigation_pending)
        self.assertEqual(w.page_progress.value(), 0)
        self.assertTrue(w.btn_prev.property('unavailable'))
        self.assertTrue(w.btn_next.property('unavailable'))

    def test_invalid_page_enter_restores_number(self):
        from PyQt5.QtTest import QTest
        self.load()
        w = self.window
        for value in ['', '0', '99', '-1', 'abc', '999999999999']:
            w.edit_page.setFocus()
            w.edit_page.setText(value)
            QTest.keyClick(w.edit_page, Qt.Key_Return)
            self.assertEqual(w.edit_page.text(), '1', value)
            self.assertEqual(w.current_page, 0)
            self.assertFalse(w.navigation_pending)
        w.edit_page.setFocus()
        w.edit_page.setText('2')
        QTest.keyClick(w.edit_page, Qt.Key_Enter)
        self.wait_for(lambda: not w.jobs)
        self.assertEqual(w.current_page, 1)

    def test_splitter_keyboard_and_drag_resizing(self):
        from PyQt5.QtTest import QTest
        from PyQt5.QtCore import QPoint, QPointF, QEvent
        from PyQt5.QtGui import QMouseEvent
        self.load()
        w = self.window
        for splitter in [w.stage_splitter, w.workspace_splitter]:
            handle = splitter.handle(1)
            before = splitter.sizes()
            key = Qt.Key_Left if splitter.orientation() == Qt.Horizontal else Qt.Key_Up
            QTest.keyClick(handle, key)
            self.assertNotEqual(splitter.sizes(), before)
            before = splitter.sizes()
            point = handle.rect().center()
            offset = QPoint(-40, 0) if splitter.orientation() == Qt.Horizontal else QPoint(0, -40)
            QTest.mousePress(handle, Qt.LeftButton, pos=point)
            move = QMouseEvent(QEvent.MouseMove, QPointF(point+offset),
                              QPointF(handle.mapToGlobal(point+offset)), Qt.NoButton, Qt.LeftButton, Qt.NoModifier)
            self.app.sendEvent(handle, move)
            QTest.mouseRelease(handle, Qt.LeftButton, pos=point+offset)
            self.assertNotEqual(splitter.sizes(), before)
            self.assertTrue(all(size > 0 for size in splitter.sizes()))
        self.assertFalse(w.current_view.pixmap().isNull())

    def test_dpi_reflow_repairs_stale_layout_without_page_change(self):
        self.load()
        w = self.window
        w.stage_splitter.setSizes([650, 350])
        self.app.processEvents()
        before = w.stage_splitter.sizes()
        central = w.centralWidget()
        central.resize(w.width()*2, w.height()*2)
        w.refresh_controller_layout()
        self.app.processEvents()
        self.assertLessEqual(central.width(), w.width())
        self.assertLessEqual(central.height(), w.height())
        self.assertTrue(central.rect().contains(w.btn_open.mapTo(central,w.btn_open.rect().bottomRight())))
        self.assertTrue(central.rect().contains(w.version_label.mapTo(central,w.version_label.rect().bottomRight())))
        self.assertEqual(w.current_page, 0)
        self.assertFalse(w.presentation_active)
        self.assertFalse(w.current_view.pixmap().isNull())
        # Reflow must preserve the user's split ratio (within rounding).
        after = w.stage_splitter.sizes()
        self.assertAlmostEqual(before[0]/sum(before), after[0]/sum(after), delta=0.02)

    def test_dpi_reflow_fits_smaller_screen(self):
        from unittest.mock import MagicMock
        from PyQt5.QtCore import QRect
        self.load()
        w = self.window
        w.resize(1600, 1000)
        self.app.processEvents()
        screen = MagicMock()
        screen.availableGeometry.return_value = QRect(0, 0, 1100, 760)
        with patch.object(w, 'windowHandle') as handle:
            handle.return_value.screen.return_value = screen
            w.refresh_controller_layout()
        self.assertLessEqual(w.frameGeometry().width(), 1100)
        self.assertLessEqual(w.frameGeometry().height(), 760)
        self.assertGreaterEqual(w.width(), w.minimumWidth())
        self.assertFalse(w.presentation_active)

    def test_dpi_events_coalesce_and_close_cancels_reflow(self):
        w = self.window
        for _ in range(5):
            w.screen_configuration_changed()
        self.assertTrue(w.dpi_layout_timer.isActive())
        with patch.object(w, 'refresh_layout') as refresh:
            self.wait_for(lambda: not w.dpi_layout_timer.isActive())
            self.assertTrue(refresh.called)
        w.screen_configuration_changed()
        w.close()
        self.assertFalse(w.dpi_layout_timer.isActive())

    def test_vertical_arrow_navigation_in_controller_and_audience(self):
        from PyQt5.QtTest import QTest
        self.load()
        w = self.window
        w.activateWindow()
        w.setFocus()
        self.app.processEvents()
        for key, expected in ((Qt.Key_Up,0), (Qt.Key_Down,1), (Qt.Key_Down,2),
                              (Qt.Key_Down,2), (Qt.Key_Up,1)):
            QTest.keyClick(w, key)
            self.assertEqual(w.current_page, expected)
        w.edit_page.setFocus()
        QTest.keyClick(w.edit_page, Qt.Key_Down)
        self.assertEqual(w.current_page, 1)
        w.start_presentation()
        w.audience_window.activateWindow()
        self.app.processEvents()
        for key, expected in ((Qt.Key_Down,2), (Qt.Key_Up,1)):
            QTest.keyClick(w.audience_window, key)
            self.assertEqual(w.current_page, expected)

    def test_arrow_navigation_after_splitter_drag(self):
        from PyQt5.QtTest import QTest
        from PyQt5.QtCore import QPoint, QPointF, QEvent
        from PyQt5.QtGui import QMouseEvent
        self.load()
        w = self.window
        w.activateWindow()
        self.app.processEvents()
        for splitter in (w.stage_splitter, w.workspace_splitter):
            w.edit_page.setFocus()
            handle = splitter.handle(1)
            before = splitter.sizes()
            point = handle.rect().center()
            offset = QPoint(-40, 0) if splitter.orientation() == Qt.Horizontal else QPoint(0, -40)
            QTest.mousePress(handle, Qt.LeftButton, pos=point)
            move = QMouseEvent(QEvent.MouseMove, QPointF(point+offset),
                              QPointF(handle.mapToGlobal(point+offset)), Qt.NoButton, Qt.LeftButton, Qt.NoModifier)
            self.app.sendEvent(handle, move)
            QTest.mouseRelease(handle, Qt.LeftButton, pos=point+offset)
            self.app.processEvents()
            self.assertNotEqual(splitter.sizes(), before)
            after = splitter.sizes()
            self.assertFalse(handle.hasFocus())
            self.assertTrue(all(sc.isEnabled() for sc in w.shortcuts))
            QTest.keyClick(self.app.focusWidget(), Qt.Key_Right)
            self.wait_for(lambda: w.current_page == 1 and not w.jobs)
            self.assertEqual(splitter.sizes(), after)
            QTest.keyClick(self.app.focusWidget(), Qt.Key_Left)
            self.wait_for(lambda: w.current_page == 0 and not w.jobs)
            # Deliberate keyboard focus still allows accessible resizing.
            handle.setFocus(Qt.TabFocusReason)
            key = Qt.Key_Left if splitter.orientation() == Qt.Horizontal else Qt.Key_Up
            QTest.keyClick(handle, key)
            self.assertNotEqual(splitter.sizes(), after)
            self.assertEqual(w.current_page, 0)

    def test_touch_controls_grow_and_shrink_with_dock(self):
        from PyQt5.QtTest import QTest
        self.load()
        w = self.window
        splitter = w.workspace_splitter
        total = sum(splitter.sizes())
        splitter.setSizes([total-112,112])
        QTest.qWait(50)
        initial_height = w.btn_next.height()
        initial_font = w.edit_page.font().pixelSize()
        initial_caption = w.lbl_suffix.font().pixelSize()
        splitter.setSizes([total-280,280])
        QTest.qWait(100)
        self.assertGreater(w.btn_next.height(), initial_height)
        self.assertGreater(w.btn_prev.height(), initial_height)
        self.assertGreater(w.edit_page.font().pixelSize(), initial_font)
        self.assertGreater(w.lbl_suffix.font().pixelSize(), initial_caption)
        self.assertEqual(w.edit_page.height(), w.btn_next.height())
        self.assertTrue(w.btn_next.geometry().right() < w.navigation_dock.width())
        self.assertTrue(w.btn_prev.property('unavailable'))
        QTest.mouseClick(w.btn_next, Qt.LeftButton)
        self.wait_for(lambda: not w.jobs)
        self.assertEqual(w.current_page, 1)
        w.setFocus()
        w.grab().save(str(Path(__file__).with_name('verification') / 'touch-controls.png'))
        splitter.setSizes([total-112,112])
        QTest.qWait(100)
        self.assertEqual(w.btn_next.height(), initial_height)
        self.assertEqual(w.edit_page.font().pixelSize(), initial_font)

    def test_startup_focus_and_simple_empty_message(self):
        w = self.window
        self.assertFalse(w.screen_button.hasFocus())
        self.assertEqual(w.current_view.text(), 'PDF 파일을 열어 주세요.')
        self.assertEqual(w.next_view.text(), 'PDF 파일을 열어 주세요.')
        w.screen_button.setFocus()
        self.app.processEvents()
        self.assertTrue(w.screen_button.hasFocus())
        w.setup_screens()
        self.assertTrue(w.screen_button.hasFocus())

    def test_qt_messages_are_not_silenced(self):
        import io
        output = io.StringIO()
        with patch.object(presenter.sys, 'stderr', output):
            presenter.qt_message_handler(None, None, 'important diagnostic')
            presenter.qt_message_handler(None, None, 'splitter-horizontal.svg')
        self.assertIn('important diagnostic', output.getvalue())
        self.assertNotIn('splitter-horizontal.svg', output.getvalue())

    def test_no_reopen_menu_and_bundled_fonts_registered(self):
        self.assertNotIn('청중 화면 다시 표시', [a.text() for a in self.window.screen_menu.actions()])
        from PyQt5.QtGui import QFontDatabase
        self.assertEqual(len(presenter._bundled_font_ids), 2)
        self.assertTrue({'Regular', 'SemiBold'}.issubset(set(QFontDatabase().styles('Pretendard'))))
        families = [family for font_id in presenter._bundled_font_ids
                    for family in QFontDatabase.applicationFontFamilies(font_id)]
        self.assertIn('Pretendard', families)

    def test_focus_animation_reverses_without_jump(self):
        edit = self.window.edit_page
        self.assertIsNone(edit.graphicsEffect())
        edit.animate_focus(1.0)
        edit.anim.setCurrentTime(70)
        level = edit.focusGlow
        self.assertGreater(level, 0)
        self.assertLess(level, 1)
        edit.animate_focus(0.0)
        self.assertAlmostEqual(edit.focusGlow, level)
        edit.anim.setCurrentTime(edit.anim.duration())
        self.assertEqual(edit.focusGlow, 0.0)
        self.assertEqual(self.window.version_label.text(), 'ver 2.5')
        with patch('presenter_ui.QDesktopServices.openUrl') as open_url:
            self.window.version_label.click()
            self.assertEqual(open_url.call_args.args[0].toString(), 'https://github.com/HwangAA/PDF-Presenter-Tools')

    def test_page_number_stays_centered_during_rapid_state_changes(self):
        edit = self.window.edit_page
        edit.clearFocus()
        for number in ['1', '8', '10', '99', '100', '999', '1']:
            for enabled in [False, True]:
                edit.setEnabled(enabled)
                edit.setText(number)
                # Render immediately, before a queued layout/paint can correct it.
                frame = edit.grab().toImage()
                points = [(x, y) for y in range(4, frame.height()-4)
                          for x in range(8, frame.width()-8)
                          if frame.pixelColor(x, y).name() == '#80cbc4']
                self.assertTrue(points)
                center_x = (min(x for x, y in points) + max(x for x, y in points)) / 2
                self.assertLessEqual(abs(center_x - (frame.width()-1)/2), 3, (number, enabled, center_x))
                self.app.processEvents()
                self.assertEqual(frame, edit.grab().toImage(), (number, enabled))

    def test_worker_start_failure_can_be_retried(self):
        from unittest.mock import MagicMock
        context = MagicMock()
        context.Process.return_value.start.side_effect = OSError('injected process start failure')
        with patch.object(presenter.mp, 'get_context', return_value=context):
            self.window.load_pdf(self.path)
        self.assertIsNone(self.window.worker)
        self.assertFalse(self.window.navigation_pending)
        self.load()

    def test_stale_resolution_error_keeps_valid_preview(self):
        self.load()
        w = self.window
        before = w.next_view.pixmap().toImage()
        w.finish_render((w.pdf_doc, w.pdf_path, 1, 'preview', (1, 1)), None, 'old resolution error')
        self.assertEqual(w.next_view.pixmap().toImage(), before)

    def test_monitor_switch_during_render_requests_new_resolution(self):
        self.load()
        w = self.window
        from PyQt5.QtGui import QImage
        image = QImage(64, 64, QImage.Format_RGB888)
        image.fill(Qt.black)
        payload = (image.bits().asstring(image.byteCount()), 64, 64, image.bytesPerLine())
        w.navigation_target = 0
        w.navigation_pending = True
        with patch.object(w, 'render_size', return_value=(640, 480)), patch.object(w, 'request_render') as request:
            w.finish_render((w.pdf_doc, w.pdf_path, 0, 'navigate', (1, 1)), payload, None)
            self.assertTrue(any(call.args[3] == 'navigate' for call in request.call_args_list))

    def test_monitor_caption_updates_for_selection_and_disconnect(self):
        from unittest.mock import MagicMock
        from PyQt5.QtCore import QRect, QSize
        w = self.window
        first, second = MagicMock(), MagicMock()
        for screen, name in ((first, 'DISPLAY1'), (second, '회의실 & 화면')):
            screen.name.return_value = name
            screen.geometry.return_value = QRect(0, 0, 1920, 1080)
            screen.size.return_value = QSize(1920, 1080)
            screen.devicePixelRatio.return_value = 1
        with patch.object(presenter.QApplication, 'screens', return_value=[first, second]), \
             patch.object(w, 'windowHandle') as handle:
            handle.return_value.screen.return_value = first
            w.choose_screen(second)
            self.assertEqual(w.screen_button.text(), '발표 모니터: 회의실 && 화면  ▾')
            self.assertEqual(w.screen_button.accessibleName(), '발표 모니터: 회의실 & 화면')
            w.choose_screen(first)
            self.assertEqual(w.screen_button.text(), '발표 모니터: DISPLAY1  ▾')
            w.choose_screen(None)
            self.assertIn('회의실', w.screen_button.text())
            w.choose_screen(second)
            with patch.object(presenter.QApplication, 'screens', return_value=[first]):
                w.refresh_screens()
                self.assertIsNone(w.selected_screen)
                self.assertEqual(w.screen_button.text(), '발표 모니터: DISPLAY1  ▾')
            self.assertFalse(w.presentation_active)
        w.refresh_screens()

    def test_stop_button_color_survives_navigation_and_resets(self):
        from PyQt5.QtCore import QEvent
        self.load()
        w = self.window
        button = w.btn_presentation
        self.assertFalse(button.property('danger'))
        w.start_presentation()
        for action in (w.next_page, w.prev_page, w.sync_ui):
            action()
            self.app.sendEvent(button, QEvent(QEvent.Leave))
            self.app.processEvents()
            self.assertTrue(button.property('danger'))
            self.assertEqual(button.text(), '발표 정지')
            self.assertEqual(button.grab().toImage().pixelColor(14, button.height()//2).name(), '#ffb4ab')
        w.stop_presentation()
        self.app.processEvents()
        self.assertFalse(button.property('danger'))
        self.assertEqual(button.text(), '발표 시작')
        self.assertEqual(button.grab().toImage().pixelColor(14, button.height()//2).name(), '#d5e7ff')

    def test_real_click_outside_page_edit_does_not_raise(self):
        from PyQt5.QtTest import QTest
        from PyQt5.QtCore import QPoint
        self.load()
        w = self.window
        w.activateWindow()
        self.app.processEvents()
        # Qt routes uncaught callback exceptions to sys.excepthook; capture
        # them here so a regression reports a test failure instead of aborting.
        with patch('sys.excepthook') as uncaught:
            for target in (w.navigation_dock, w.current_view, w.next_view,
                           w.lbl_remaining, w.centralWidget()):
                QTest.mouseClick(w.edit_page, Qt.LeftButton)
                self.app.processEvents()
                self.assertTrue(w.edit_page.hasFocus())
                w.edit_page.setText('999')
                QTest.mouseClick(target, Qt.LeftButton, pos=QPoint(1, 1))
                self.app.processEvents()
                self.assertFalse(uncaught.called,
                                 str(uncaught.call_args_list))
                self.assertFalse(w.edit_page.hasFocus())
                self.assertEqual(w.edit_page.text(), '1')
            QTest.keyClick(w, Qt.Key_Right)
            self.wait_for(lambda: w.current_page == 1)
            self.assertTrue(w.isVisible())

    def test_new_document_does_not_inherit_stalled_preview(self):
        self.load()
        w = self.window
        old_worker = w.worker
        with patch.object(w.requests, 'put'):
            w.request_render(w.pdf_doc, w.pdf_path, 1, 'preview')
        w.last_render_progress = time.monotonic() - 61
        with patch.object(w, 'show_error') as error:
            w.load_pdf(self.path)
            self.assertIsNot(w.worker, old_worker)
            self.assertEqual([job[3] for job in w.jobs.values()], ['open'])
            self.wait_for(lambda: not w.navigation_pending and not w.jobs)
            error.assert_not_called()
        self.assertEqual(w.current_page, 0)
        self.assertEqual(len(w.document_tokens), 1)

    def test_invalid_replacement_preserves_worker_and_presentation(self):
        self.load()
        w = self.window
        w.start_presentation()
        worker, doc = w.worker, w.pdf_doc
        with patch.object(w, 'show_error'):
            w.load_pdf(self.encrypted)
        self.assertIs(w.worker, worker)
        self.assertIs(w.pdf_doc, doc)
        self.assertTrue(w.presentation_active)

    def test_open_resolution_change_prioritizes_current_page(self):
        w = self.window
        candidate = fitz.open(self.path)
        payload = (bytes([0, 40, 80]) * 64 * 64, 64, 64, 64 * 3)
        with patch.object(w, 'render_size', return_value=(640, 480)), \
             patch.object(w, 'request_render') as request:
            w.finish_render((candidate, self.path, 0, 'open', (1, 1)), payload, None)
            self.assertTrue(request.called)
            self.assertEqual(request.call_args_list[0].args[2:4], (0, 'navigate'))
            self.assertFalse(any(call.args[3] == 'preview' for call in request.call_args_list))

    def test_failed_open_retry_uses_new_document_token(self):
        self.load()
        w = self.window
        old_token = w.document_tokens[id(w.pdf_doc)]
        candidate = fitz.open(self.path)
        with patch.object(w.requests, 'put') as put:
            w.request_render(candidate, self.path, 0, 'open')
            failed_token = put.call_args.args[0][-1]
        job = w.jobs.pop(w.job_serial)
        with patch.object(w, 'show_error'):
            w.finish_render(job, None, 'simulated render failure')
        self.assertNotIn(id(candidate), w.document_tokens)
        self.assertEqual(w.document_tokens[id(w.pdf_doc)], old_token)
        w.load_pdf(self.path)
        self.wait_for(lambda: not w.navigation_pending and not w.jobs)
        self.assertGreater(w.document_tokens[id(w.pdf_doc)], failed_token)
        self.assertGreater(failed_token, old_token)
        self.assertEqual(len(w.document_tokens), 1)

    def test_large_pixmap_survives_payload_release(self):
        import gc
        self.load()
        w = self.window
        width, height = 3840, 2160
        payload = (bytes([19, 79, 139]) * width * height, width, height, width * 3)
        size = w.render_size()
        w.finish_render((w.pdf_doc, w.pdf_path, 1, 'preview', size), payload, None)
        del payload
        gc.collect()
        # Reuse memory after releasing the worker response.
        scratch = bytes([230, 30, 50]) * width * height
        image = w.cached_next_pixmap.toImage()
        for x, y in [(0, 0), (width // 2, height // 2), (width - 1, height - 1)]:
            self.assertEqual(image.pixelColor(x, y).getRgb()[:3], (19, 79, 139))
        self.assertEqual(len(scratch), width * height * 3)

    def test_page_edit_blank_click_and_interactive_child_focus(self):
        from PyQt5.QtWidgets import QSlider, QLabel
        from PyQt5.QtGui import QMouseEvent
        from PyQt5.QtCore import QEvent, QPointF
        self.load()
        w = self.window
        slider = QSlider(w)
        child = QLabel(slider)
        blank = QLabel(w)
        w.activateWindow()
        w.edit_page.setFocus()
        self.app.processEvents()
        self.assertTrue(w.edit_page.hasFocus())
        event = QMouseEvent(QEvent.MouseButtonPress, QPointF(1, 1),
                            Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        with patch.object(presenter.QApplication, 'activeWindow', return_value=w):
            w.eventFilter(child, event)
            self.assertTrue(w.edit_page.hasFocus())
            w.eventFilter(blank, event)
            self.assertFalse(w.edit_page.hasFocus())
        slider.deleteLater()
        blank.deleteLater()

    def test_same_monitor_windowed_other_monitor_fullscreen(self):
        from unittest.mock import MagicMock
        from PyQt5.QtCore import QRect, QSize
        w = self.window
        first, second = MagicMock(), MagicMock()
        for screen in (first, second):
            screen.size.return_value = QSize(1920, 1080)
            screen.devicePixelRatio.return_value = 1
        first.availableGeometry.return_value = QRect(0, 0, 1920, 1080)
        second.geometry.return_value = QRect(1920, 0, 1920, 1080)
        audience = MagicMock()
        real_audience = w.audience_window
        w.audience_window = audience
        w.presentation_active = True
        try:
            with patch.object(presenter.QApplication, 'screens', return_value=[first, second]), \
                 patch.object(w, 'windowHandle') as handle:
                handle.return_value.screen.return_value = first
                w.selected_screen = second
                w.setup_screens()
                audience.showFullScreen.assert_called_once()
                audience.windowHandle.return_value.setScreen.assert_called_with(second)
                audience.reset_mock()
                w.selected_screen = first
                w.setup_screens()
                audience.showNormal.assert_called_once()
                audience.showFullScreen.assert_not_called()
                audience.resize.assert_called_once_with(640, 480)
        finally:
            w.audience_window = real_audience
            w.selected_screen = None

    def test_fractional_page_edges_have_no_white_fringe(self):
        for dimensions in [(595.28, 841.89), (841.89, 595.28), (612.37, 792.13)]:
            for rotation in [0, 90]:
                with fitz.open() as doc:
                    page = doc.new_page(width=dimensions[0], height=dimensions[1])
                    page.draw_rect(page.rect, color=None, fill=(0, 0, 0))
                    page.set_rotation(rotation)
                    for target in [(1920, 1080), (1366, 768), (3840, 2160)]:
                        pix = presenter.render_page(page, *target)
                        for x, y in [(0, 0), (pix.width-1, pix.height//2),
                                     (pix.width//2, pix.height-1), (pix.width-1, pix.height-1)]:
                            self.assertEqual(pix.pixel(x, y), (0, 0, 0), (dimensions, rotation, target, x, y))
                    # Ordinary white PDF paper must remain white.
                    white = doc.new_page(width=dimensions[0], height=dimensions[1])
                    pix = presenter.render_page(white, 1920, 1080)
                    self.assertEqual(pix.pixel(pix.width-1, pix.height//2), (255, 255, 255))


if __name__ == '__main__':
    presenter.mp.freeze_support()
    unittest.main(verbosity=2)
