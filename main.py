import sys
import threading
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from video_info import read_video_info
from thumbnail import extract_thumbnail
from conversion_settings import ConversionSettings
from converter import convert_video, ConversionCancelled


class VideoInfoWorker(QThread):
    """后台读取视频信息和缩略图。"""

    succeeded = Signal(dict, bytes, str)
    failed = Signal(str)

    def __init__(self, video_path: Path, parent=None):
        super().__init__(parent)
        self.video_path = video_path

    def run(self):
        try:
            info = read_video_info(self.video_path)
        except Exception as exc:
            self.failed.emit(str(exc))
            return

        image_data = b""
        warning = ""

        try:
            image_data = extract_thumbnail(
                self.video_path,
                info["视频流索引"],
            )
        except Exception as exc:
            warning = str(exc)

        self.succeeded.emit(info, image_data, warning)


class ConversionWorker(QThread):
    """后台执行转换，支持进度和取消。"""

    progress = Signal(int)
    succeeded = Signal(str)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(
        self,
        source_path: Path,
        output_path: Path,
        quality: str,
        parent=None,
    ):
        super().__init__(parent)

        self.source_path = source_path
        self.output_path = output_path
        self.quality = quality

        # 主窗口和转换函数共享这个取消标记。
        self.cancel_event = threading.Event()

    def request_cancel(self):
        """主窗口调用此方法，请求停止转换。"""
        self.cancel_event.set()

    def run(self):
        try:
            saved_path = convert_video(
                self.source_path,
                self.output_path,
                self.quality,
                progress_callback=self.progress.emit,
                cancel_event=self.cancel_event,
            )
        except ConversionCancelled:
            self.cancelled.emit()
        except Exception as exc:
            self.failed.emit(str(exc))
        else:
            self.succeeded.emit(str(saved_path))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("我的视频格式转换器")
        self.resize(900, 650)

        self.video_path: Path | None = None
        self.video_info: dict | None = None
        self.worker: QThread | None = None

        title = QLabel("请选择需要转换的视频")

        self.select_button = QPushButton("选择视频")
        self.select_button.clicked.connect(self.select_video)

        self.path_label = QLabel("尚未选择文件")
        self.path_label.setWordWrap(True)
        self.path_label.setTextFormat(Qt.TextFormat.PlainText)

        self.info_label = QLabel("选择视频后，将显示视频信息")
        self.info_label.setWordWrap(True)
        self.info_label.setTextFormat(Qt.TextFormat.PlainText)

        self.thumbnail_label = QLabel("视频缩略图")
        self.thumbnail_label.setFixedSize(480, 270)
        self.thumbnail_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )
        self.thumbnail_label.setTextFormat(Qt.TextFormat.PlainText)
        self.thumbnail_label.setStyleSheet(
            "background-color: #eeeeee;"
            "border: 1px solid #cccccc;"
        )

        self.settings = ConversionSettings()

        hint = QLabel(
            "高质量通常占用更多空间；较小体积可能损失更多细节。"
        )
        hint.setWordWrap(True)

        self.start_button = QPushButton("开始转换")
        self.start_button.clicked.connect(self.start_conversion)

        self.cancel_button = QPushButton("取消转换")
        self.cancel_button.clicked.connect(self.cancel_conversion)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.cancel_button)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%p%")

        self.status_label = QLabel("请先选择一个视频")
        self.status_label.setWordWrap(True)
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        layout.addWidget(title)
        layout.addWidget(self.select_button)
        layout.addWidget(self.path_label)
        layout.addWidget(self.info_label)
        layout.addWidget(
            self.thumbnail_label,
            alignment=Qt.AlignmentFlag.AlignHCenter,
        )
        layout.addWidget(QLabel("转换设置"))
        layout.addWidget(self.settings)
        layout.addWidget(hint)
        layout.addLayout(button_layout)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.status_label)
        layout.addStretch()

        container = QWidget()
        container.setLayout(layout)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(container)
        self.setCentralWidget(scroll)

        self.update_controls()

    def update_controls(self):
        """统一管理控件状态。"""
        busy = self.worker is not None
        ready = self.video_info is not None

        self.select_button.setEnabled(not busy)
        self.settings.setEnabled(not busy and ready)
        self.start_button.setEnabled(not busy and ready)

        can_cancel = (
            isinstance(self.worker, ConversionWorker)
            and not self.worker.cancel_event.is_set()
            and self.progress_bar.value() != 100
        )
        self.cancel_button.setEnabled(can_cancel)

    def connect_worker_cleanup(self):
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.finished.connect(self.worker.deleteLater)

    def select_video(self):
        if self.worker is not None:
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择视频文件",
            "",
            "视频文件 (*.mp4 *.mkv *.mov *.avi *.webm);;所有文件 (*)",
        )

        if not file_path:
            return

        self.video_path = Path(file_path)
        self.video_info = None

        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)

        self.path_label.setText(f"已选择：{self.video_path}")
        self.info_label.setText("正在读取视频信息……")

        self.thumbnail_label.clear()
        self.thumbnail_label.setText("正在提取缩略图……")

        self.settings.output_edit.clear()
        self.status_label.setText("正在读取，请稍候……")

        self.worker = VideoInfoWorker(self.video_path, self)
        self.worker.succeeded.connect(self.show_video_info)
        self.worker.failed.connect(self.show_read_error)
        self.connect_worker_cleanup()

        self.update_controls()
        self.worker.start()

    def show_video_info(
        self,
        info: dict,
        image_data: bytes,
        warning: str,
    ):
        self.video_info = info

        width = info.get("宽度") or "未知"
        height = info.get("高度") or "未知"
        duration = info.get("时长（秒）") or "未知"
        size_mib = info["文件大小（字节）"] / (1024 * 1024)

        text = (
            f"视频编码：{info['视频编码']}\n"
            f"分辨率：{width} × {height}\n"
            f"时长：{duration} 秒\n"
            f"文件大小：{size_mib:.2f} MiB"
        )

        pixmap = QPixmap()

        if image_data and pixmap.loadFromData(image_data):
            preview = pixmap.scaled(
                self.thumbnail_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.thumbnail_label.setPixmap(preview)
        else:
            self.thumbnail_label.setText("缩略图暂不可用")
            text += f"\n缩略图提示：{warning or '无法加载图片数据'}"

        self.info_label.setText(text)
        self.settings.set_source(self.video_path)
        self.status_label.setText(
            "视频已就绪，请设置输出路径并开始转换"
        )

    def show_read_error(self, message: str):
        self.video_info = None
        self.info_label.setText(f"无法读取视频：{message}")

        self.thumbnail_label.clear()
        self.thumbnail_label.setText("无法预览此文件")

        self.status_label.setText(
            "读取失败，请重新选择有效视频"
        )

    def start_conversion(self):
        if self.worker is not None or self.video_info is None:
            return

        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)

        options = self.settings.get_options()

        if not options["output_path"]:
            self.status_label.setText("请先设置输出路径")
            return

        output_path = Path(options["output_path"])
        expected_suffix = "." + options["format"].lower()

        if output_path.suffix.lower() != expected_suffix:
            self.status_label.setText(
                "输出路径的扩展名与所选格式不一致，请重新选择"
            )
            return

        self.worker = ConversionWorker(
            source_path=self.video_path,
            output_path=output_path,
            quality=options["quality"],
            parent=self,
        )

        self.worker.progress.connect(
            self.show_conversion_progress
        )
        self.worker.succeeded.connect(
            self.show_conversion_success
        )
        self.worker.failed.connect(
            self.show_conversion_error
        )
        self.worker.cancelled.connect(
            self.show_conversion_cancelled
        )
        self.connect_worker_cleanup()

        self.status_label.setText("正在转换，请稍候……")
        self.update_controls()
        self.worker.start()

    def cancel_conversion(self):
        if not isinstance(self.worker, ConversionWorker):
            return

        self.worker.request_cancel()
        self.cancel_button.setEnabled(False)
        self.status_label.setText(
            "正在取消，请等待进程结束并清理临时文件……"
        )

    def show_conversion_progress(self, percent: int):
        if percent == -1:
            self.progress_bar.setRange(0, 0)
        else:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(percent)

            if percent == 100:
                self.cancel_button.setEnabled(False)

    def show_conversion_success(self, saved_path: str):
        self.cancel_button.setEnabled(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.status_label.setText(
            f"转换完成：{saved_path}"
        )

    def show_conversion_error(self, message: str):
        self.cancel_button.setEnabled(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.status_label.setText(
            f"转换失败：{message}"
        )

    def show_conversion_cancelled(self):
        self.cancel_button.setEnabled(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.status_label.setText(
            "已取消转换，可以重新开始。"
        )

    def on_worker_finished(self):
        self.worker = None
        self.update_controls()
        self.statusBar().clearMessage()

    def closeEvent(self, event):
        if self.worker is not None:
            if isinstance(self.worker, ConversionWorker):
                message = "请先取消转换，等待任务结束后关闭"
            else:
                message = "正在读取，请等待结束后关闭"

            self.statusBar().showMessage(message)
            event.ignore()
            return

        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())