"""桌面入口：后台预览、异步转码、输出验证。"""
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QProcess, QThread, QTimer, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFormLayout, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QMainWindow, QPlainTextEdit, QProgressBar, QPushButton,
    QVBoxLayout, QWidget,
)
from media import (
    FFMPEG_PATH, QUALITY, conversion_arguments, duration_seconds,
    new_temporary_output, progress_percent, publish_output, thumbnail_bytes,
    validate_destination,
)
from video_info import read_video_info


def load_preview(path):
    info = read_video_info(path)
    image, warning = b'', ''
    try:
        image = thumbnail_bytes(path, info['视频流索引'])
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        warning = f'缩略图暂不可用：{exc}'
    return {'info': info, 'image': image, 'warning': warning}


class TaskWorker(QThread):
    """后台任务只产出数据，不操作控件。"""
    def __init__(self, action, parent):
        super().__init__(parent)
        self.action = action
        self.result = None
        self.error = ''

    def run(self):
        try:
            self.result = self.action()
        except Exception as exc:
            self.error = str(exc) or type(exc).__name__


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('视频格式转换器')
        self.resize(1000, 800)
        self.setMinimumSize(780, 680)
        self.video_path = self.info = self.worker = self.process = None
        self.temporary = self.destination = self.last_output = None
        self.phase = 'idle'
        self.cancel_requested = False
        self.stdout_buffer = self.stderr_buffer = ''

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)
        title = QLabel('视频格式转换器')
        title.setObjectName('title')
        layout.addWidget(title)
        layout.addWidget(QLabel('导入视频，选择预设，保存为 MP4 或 MKV。文件始终在本机处理。'))

        top = QHBoxLayout()
        self.select_button = QPushButton('＋ 选择视频')
        self.select_button.clicked.connect(self.select_video)
        top.addWidget(self.select_button)
        top.addWidget(QLabel('也可以将一个本地视频拖入窗口'), 1)
        layout.addLayout(top)
        self.path_label = self.plain_label('尚未选择视频')
        self.path_label.setWordWrap(True)
        layout.addWidget(self.path_label)

        preview = QHBoxLayout()
        self.thumbnail = QLabel('视频缩略图')
        self.thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumbnail.setMinimumSize(320, 180)
        self.thumbnail.setObjectName('thumbnail')
        preview.addWidget(self.thumbnail, 1)
        self.info_label = self.plain_label('选择视频后显示编码、分辨率、时长和文件大小。')
        self.info_label.setWordWrap(True)
        preview.addWidget(self.info_label, 1)
        layout.addLayout(preview)

        settings = QFrame()
        settings.setObjectName('settings')
        form = QFormLayout(settings)
        form.setContentsMargins(18, 16, 18, 16)
        form.setSpacing(12)
        self.format_box = QComboBox()
        self.format_box.addItems(['MP4', 'MKV'])
        self.format_box.currentTextChanged.connect(self._format_changed)
        form.addRow('输出格式', self.format_box)
        self.quality_box = QComboBox()
        self.quality_box.addItems(list(QUALITY))
        self.quality_box.setCurrentText('均衡')
        form.addRow('质量预设', self.quality_box)
        row = QHBoxLayout()
        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText('选择视频后自动生成输出路径，也可修改')
        self.browse_button = QPushButton('另存为…')
        self.browse_button.clicked.connect(self.choose_output)
        row.addWidget(self.output_edit, 1)
        row.addWidget(self.browse_button)
        form.addRow('保存到', row)
        layout.addWidget(settings)
        hint = QLabel('H.264 视频 + AAC 音频（如有）。高质量通常占用更多空间；不会覆盖已有文件。')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.progress = QProgressBar()
        self.progress.setValue(0)
        layout.addWidget(self.progress)
        self.status_label = self.plain_label('准备就绪，请选择一个视频。')
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        actions = QHBoxLayout()
        self.start_button = QPushButton('开始转换')
        self.start_button.setObjectName('primary')
        self.start_button.clicked.connect(self.start_conversion)
        self.cancel_button = QPushButton('取消转换')
        self.cancel_button.clicked.connect(self.cancel_conversion)
        self.open_button = QPushButton('打开输出目录')
        self.open_button.clicked.connect(self.open_output)
        for button in (self.start_button, self.cancel_button, self.open_button):
            actions.addWidget(button)
        layout.addLayout(actions)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setPlaceholderText('出错时会在此显示详细原因，便于排查。')
        self.details.setMaximumHeight(90)
        layout.addWidget(self.details)
        self.setCentralWidget(root)
        self.setAcceptDrops(True)
        self.setStyleSheet('''
            QWidget { font-family: "Microsoft YaHei UI"; font-size: 14px; color: #172b4d; }
            QMainWindow { background: #f4f7fb; }
            QLabel#title { font-size: 28px; font-weight: bold; }
            QFrame#settings { background: white; border: 1px solid #dce3ef; border-radius: 10px; }
            QLabel#thumbnail { background: #e8eef7; border-radius: 10px; color: #536781; }
            QPushButton { padding: 10px 18px; background: white; border: 1px solid #cad5e5; border-radius: 6px; }
            QPushButton:hover { background: #eaf1fd; }
            QPushButton#primary { background: #2463dc; color: white; border: none; }
            QPushButton:disabled { background: #e5eaf2; color: #8996aa; }
            QLineEdit, QComboBox, QPlainTextEdit { padding: 7px; background: white; border: 1px solid #cad5e5; border-radius: 5px; }
            QProgressBar { border: 1px solid #dce3ef; border-radius: 5px; text-align: center; min-height: 20px; }
            QProgressBar::chunk { background: #4984ee; border-radius: 4px; }
        ''')
        self._update_controls()

    @staticmethod
    def plain_label(text):
        label = QLabel(text)
        label.setTextFormat(Qt.TextFormat.PlainText)
        return label

    def _update_controls(self):
        idle = self.phase == 'idle'
        self.select_button.setEnabled(idle)
        for widget in (self.format_box, self.quality_box, self.output_edit, self.browse_button):
            widget.setEnabled(idle)
        self.start_button.setEnabled(idle and self.info is not None)
        self.cancel_button.setEnabled(self.phase == 'converting' and not self.cancel_requested)
        self.open_button.setEnabled(idle and self.last_output is not None)

    def select_video(self):
        path, _ = QFileDialog.getOpenFileName(self, '选择视频文件', '',
            '视频文件 (*.mp4 *.mkv *.mov *.avi *.webm *.m4v);;所有文件 (*)')
        if path:
            self.load_video(Path(path))

    def load_video(self, path):
        if self.phase != 'idle':
            return
        self.video_path = Path(path)
        self.info = self.last_output = None
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.path_label.setText(str(path))
        self.info_label.setText('正在读取视频信息……')
        self.thumbnail.clear()
        self.thumbnail.setText('正在生成缩略图……')
        self.details.clear()
        self._set_default_output()
        self._start_task('loading', lambda: load_preview(Path(path)))

    def _set_default_output(self):
        if self.video_path:
            extension = '.' + self.format_box.currentText().lower()
            base = self.video_path.parent / (self.video_path.stem + '_converted' + extension)
            candidate, number = base, 2
            while candidate.exists():
                candidate = base.with_name(base.stem + f'_{number}' + base.suffix)
                number += 1
            self.output_edit.setText(str(candidate))

    def _format_changed(self):
        text = self.output_edit.text().strip()
        if text:
            self.output_edit.setText(str(Path(text).with_suffix('.' + self.format_box.currentText().lower())))

    def choose_output(self):
        extension = self.format_box.currentText().lower()
        path, _ = QFileDialog.getSaveFileName(self, '选择输出文件（已有文件不会覆盖）',
            self.output_edit.text(), f'{extension.upper()} 视频 (*.{extension})')
        if path:
            destination = Path(path)
            if destination.suffix.lower() != '.' + extension:
                destination = destination.with_suffix('.' + extension)
            self.output_edit.setText(str(destination))

    def _start_task(self, phase, action):
        self.phase = phase
        self.status_label.setText('正在读取视频与缩略图……' if phase == 'loading' else '转码结束，正在验证输出文件……')
        self._update_controls()
        self.worker = TaskWorker(action, self)
        self.worker.finished.connect(self._task_finished)
        self.worker.start()

    def _task_finished(self):
        worker, phase = self.worker, self.phase
        self.worker = None
        result, error = worker.result, worker.error
        worker.deleteLater()
        if error:
            if phase == 'loading':
                self.info_label.setText('无法读取此文件，请选择有效的视频。')
                self.thumbnail.setText('无预览')
            self._fail(error)
            return
        if phase == 'loading':
            self.info = result['info']
            info = self.info
            seconds = duration_seconds(info.get('时长（秒）'))
            duration = f'{seconds:.2f} 秒' if seconds else '未知'
            self.info_label.setText(
                f"视频编码：{info['视频编码']}\n"
                f"分辨率：{info.get('宽度') or '未知'} × {info.get('高度') or '未知'}\n"
                f"时长：{duration}\n文件大小：{info['文件大小（字节）'] / 1048576:.2f} MiB")
            pixmap = QPixmap()
            if result['image'] and pixmap.loadFromData(result['image']):
                self.thumbnail.setPixmap(pixmap.scaled(
                    440, 248, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            else:
                self.thumbnail.setText('缩略图不可用，仍可转换')
            self.status_label.setText('视频已就绪，可以开始转换。')
            if result['warning']:
                self.details.setPlainText(result['warning'])
        elif phase == 'verifying':
            try:
                if not self.temporary or self.temporary.stat().st_size == 0:
                    raise ValueError('输出文件为空')
                publish_output(self.temporary, self.destination)
            except (ValueError, OSError) as exc:
                self._fail(f'保存输出失败：{exc}')
                return
            self.temporary = None
            self.last_output = self.destination
            self.progress.setRange(0, 100)
            self.progress.setValue(100)
            self.status_label.setText(f'转换完成：{self.destination.name}')
            self.details.setPlainText(str(self.destination))
        self.phase = 'idle'
        self._update_controls()

    def start_conversion(self):
        if self.phase != 'idle' or self.info is None:
            return
        try:
            if not FFMPEG_PATH.is_file():
                raise ValueError('找不到 ffmpeg.exe，请检查 tools/ffmpeg/bin')
            text = self.output_edit.text().strip()
            if not text:
                raise ValueError('请选择输出路径')
            target = Path(text).absolute()
            if target.suffix.lower() != '.' + self.format_box.currentText().lower():
                raise ValueError('输出文件扩展名与所选格式不一致')
            validate_destination(self.video_path, target)
            self.destination = target
            self.temporary = new_temporary_output(target)
            args = conversion_arguments(self.video_path, self.temporary,
                self.quality_box.currentText(), self.info['视频流索引'])
        except (ValueError, OSError) as exc:
            self._fail(str(exc))
            return
        self.phase = 'converting'
        self.cancel_requested = False
        self.last_output = None
        self.stdout_buffer = self.stderr_buffer = ''
        self.details.clear()
        self.progress.setRange(0, 100 if duration_seconds(self.info.get('时长（秒）')) else 0)
        self.progress.setValue(0)
        self.status_label.setText('正在转换，请稍候……')
        self._update_controls()
        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self._read_progress)
        self.process.readyReadStandardError.connect(self._read_errors)
        self.process.errorOccurred.connect(self._process_error)
        self.process.finished.connect(self._process_finished)
        self.process.start(str(FFMPEG_PATH), args)

    def _read_progress(self):
        if self.process is None:
            return
        self.stdout_buffer += bytes(self.process.readAllStandardOutput()).decode('utf-8', errors='replace')
        while '\n' in self.stdout_buffer:
            line, self.stdout_buffer = self.stdout_buffer.split('\n', 1)
            key, _, value = line.strip().partition('=')
            if key == 'out_time_us':
                percent = progress_percent(value, self.info.get('时长（秒）'))
                if percent is not None:
                    self.progress.setValue(percent)

    def _read_errors(self):
        if self.process is not None:
            self.stderr_buffer = (self.stderr_buffer + bytes(
                self.process.readAllStandardError()).decode('utf-8', errors='replace'))[-12000:]

    def _release_process(self):
        process, self.process = self.process, None
        if process is not None:
            process.deleteLater()

    def _process_error(self, error):
        if self.process is not None and error == QProcess.ProcessError.FailedToStart:
            message = self.process.errorString()
            self._release_process()
            self._fail(f'无法启动 FFmpeg：{message}')

    def _process_finished(self, code, exit_status):
        if self.process is None:
            return
        self._read_progress()
        self._read_errors()
        self._release_process()
        if self.cancel_requested:
            self._cleanup_temporary()
            self.phase = 'idle'
            self.progress.setRange(0, 100)
            self.progress.setValue(0)
            self.status_label.setText('已取消转换，源视频未修改。')
            self._update_controls()
        elif code != 0 or exit_status != QProcess.ExitStatus.NormalExit:
            self._fail(self.stderr_buffer or f'FFmpeg 异常退出，退出码 {code}')
        else:
            self._start_task('verifying', lambda: read_video_info(self.temporary))

    def cancel_conversion(self):
        if self.phase != 'converting' or self.process is None:
            return
        self.cancel_requested = True
        self.status_label.setText('正在取消转换……')
        self._update_controls()
        process = self.process
        process.terminate()

        def force_stop():
            if self.process is process and process.state() != QProcess.ProcessState.NotRunning:
                process.kill()
        QTimer.singleShot(1500, force_stop)

    def _cleanup_temporary(self):
        if self.temporary:
            try:
                self.temporary.unlink(missing_ok=True)
            except OSError as exc:
                self.details.appendPlainText(f'临时文件清理失败：{self.temporary}\n{exc}')
            self.temporary = None

    def _fail(self, message):
        self.details.setPlainText(message)
        self._cleanup_temporary()
        self.phase = 'idle'
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.status_label.setText('操作未完成，请查看下方原因，调整后可重试。')
        self._update_controls()

    def open_output(self):
        if self.last_output:
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.last_output.parent))):
                self.details.setPlainText(f'无法打开目录，请手动访问：{self.last_output.parent}')

    def dragEnterEvent(self, event):
        urls = event.mimeData().urls()
        if self.phase == 'idle' and len(urls) == 1 and urls[0].isLocalFile():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if self.phase == 'idle' and len(urls) == 1 and urls[0].isLocalFile():
            self.load_video(Path(urls[0].toLocalFile()))
            event.acceptProposedAction()

    def closeEvent(self, event):
        if self.phase != 'idle':
            self.status_label.setText('任务尚未结束；转换时请先点击“取消转换”，待结束后关闭。')
            event.ignore()
        else:
            event.accept()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
