"""使用真正的 FFmpeg 和 Qt 事件循环验证用户流程，无需私人视频。"""
import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from main import MainWindow
from media import FFMPEG_PATH, FFPROBE_PATH, NO_WINDOW


class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.folder = tempfile.TemporaryDirectory(prefix='video-converter-')
        cls.root = Path(cls.folder.name) / '中文 video samples'
        cls.root.mkdir()
        cls.source = cls.root / '测试 输入.mp4'
        cls.silent = cls.root / '没有音轨.mkv'
        cls.run_ffmpeg(['-f', 'lavfi', '-i', 'testsrc2=size=640x360:rate=24',
            '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=44100',
            '-t', '3', '-c:v', 'libx264', '-preset', 'ultrafast', '-c:a', 'aac', str(cls.source)])
        cls.run_ffmpeg(['-f', 'lavfi', '-i', 'testsrc2=size=320x180:rate=24',
            '-t', '2', '-c:v', 'libx264', '-preset', 'ultrafast', '-an', str(cls.silent)])

    @classmethod
    def run_ffmpeg(cls, args):
        result = subprocess.run([str(FFMPEG_PATH), '-v', 'error', '-nostdin', '-y'] + args,
            capture_output=True, timeout=60, creationflags=NO_WINDOW)
        if result.returncode:
            raise AssertionError(result.stderr.decode('utf-8', errors='replace'))

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def setUp(self):
        self.window = MainWindow()
        self.window.show()

    def tearDown(self):
        if self.window.phase == 'converting':
            self.window.cancel_conversion()
        self.wait_idle()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def wait_idle(self):
        deadline = time.monotonic() + 60
        while self.window.phase != 'idle' and time.monotonic() < deadline:
            QTest.qWait(20)
        self.assertEqual(self.window.phase, 'idle', self.window.details.toPlainText())

    def load(self, source=None):
        self.window.load_video(source or self.source)
        self.wait_idle()
        self.assertIsNotNone(self.window.info, self.window.details.toPlainText())

    def convert(self, name, extension='MP4'):
        self.window.format_box.setCurrentText(extension)
        target = self.root / name
        self.window.output_edit.setText(str(target))
        self.window.start_conversion()
        self.wait_idle()
        self.assertEqual(self.window.last_output, target, self.window.details.toPlainText())
        self.assertTrue(target.is_file())
        self.assertEqual(self.window.progress.value(), 100)
        self.assertTrue(self.window.open_button.isEnabled())
        self.run_ffmpeg(['-i', str(target), '-f', 'null', '-'])
        return target

    def test_mp4_thumbnail_real_decode_and_event_loop(self):
        self.load()
        self.assertFalse(self.window.thumbnail.pixmap().isNull())
        ticks = []
        timer = QTimer()
        timer.setInterval(10)
        timer.timeout.connect(lambda: ticks.append(True))
        timer.start()
        self.convert('正常 输出.mp4')
        timer.stop()
        self.assertTrue(ticks, '转换期间事件循环应继续运行')

    def test_silent_mkv_conversion(self):
        self.load(self.silent)
        target = self.convert('静音 输出.mkv', 'MKV')
        result = subprocess.run([str(FFPROBE_PATH), '-v', 'error', '-show_streams', '-of', 'json', str(target)],
            capture_output=True, check=True, creationflags=NO_WINDOW)
        streams = json.loads(result.stdout)['streams']
        self.assertFalse(any(stream['codec_type'] == 'audio' for stream in streams))

    def test_invalid_file_then_recover(self):
        self.window.load_video(Path(__file__))
        self.wait_idle()
        self.assertIsNone(self.window.info)
        self.assertFalse(self.window.start_button.isEnabled())
        self.assertTrue(self.window.select_button.isEnabled())
        self.load()
        self.assertTrue(self.window.start_button.isEnabled())

    def test_cancel_cleanup_and_retry(self):
        self.load()
        target = self.root / '取消后重试.mp4'
        self.window.output_edit.setText(str(target))
        self.window.start_conversion()
        self.assertEqual(self.window.phase, 'converting')
        self.window.process.waitForStarted(3000)
        temporary = self.window.temporary
        self.window.close()
        self.assertTrue(self.window.isVisible(), '运行中关闭应被阻止')
        self.window.cancel_conversion()
        self.wait_idle()
        self.assertFalse(target.exists())
        self.assertFalse(temporary.exists())
        self.assertTrue(self.window.start_button.isEnabled())
        self.convert(target.name)

    def test_existing_source_and_racing_target_are_preserved(self):
        self.load()
        original = self.source.read_bytes()
        self.window.output_edit.setText(str(self.source))
        self.window.start_conversion()
        self.assertEqual(self.source.read_bytes(), original)
        self.assertIsNone(self.window.process)
        target = self.root / '竞争目标.mp4'
        self.window.output_edit.setText(str(target))
        self.window.start_conversion()
        target.write_bytes(b'other user file')
        self.wait_idle()
        self.assertEqual(target.read_bytes(), b'other user file')
        self.assertIsNone(self.window.last_output)
        self.assertFalse(list(self.root.glob('.video-converter-*')))

    def test_missing_ffmpeg_and_missing_probe_report_errors(self):
        self.load()
        with patch('main.FFMPEG_PATH', self.root / 'missing.exe'):
            self.window.start_conversion()
        self.assertIn('ffmpeg', self.window.details.toPlainText())
        self.assertEqual(self.window.phase, 'idle')
        with patch('video_info.FFPROBE_PATH', self.root / 'missing.exe'):
            self.window.load_video(self.source)
            self.wait_idle()
        self.assertIsNone(self.window.info)
        self.assertIn('ffprobe', self.window.details.toPlainText())

    def test_thumbnail_failure_does_not_block_conversion(self):
        with patch('main.thumbnail_bytes', side_effect=ValueError('测试缩略图失败')):
            self.load()
        self.assertTrue(self.window.start_button.isEnabled())
        self.assertIn('缩略图', self.window.details.toPlainText())
        self.convert('无缩略图仍转换.mp4')

    def test_invalid_output_paths_are_rejected(self):
        self.load()
        for text in ('', str(self.root / '不存在的目录' / 'out.mp4'), str(self.root / 'out.mkv')):
            self.window.output_edit.setText(text)
            self.window.start_conversion()
            self.assertEqual(self.window.phase, 'idle')
            self.assertIsNone(self.window.process)
            self.assertTrue(self.window.details.toPlainText())

    def test_failed_process_start_then_retry(self):
        self.load()
        target = self.root / '进程失败后重试.mp4'
        self.window.output_edit.setText(str(target))
        with patch('main.FFMPEG_PATH', Path(__file__)):
            self.window.start_conversion()
            self.wait_idle()
        self.assertFalse(target.exists())
        self.assertIn('无法启动', self.window.details.toPlainText())
        self.assertFalse(list(self.root.glob('.video-converter-*')))
        self.convert(target.name)


if __name__ == '__main__':
    unittest.main()
