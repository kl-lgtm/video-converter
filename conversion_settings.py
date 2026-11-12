import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QWidget,
)


class ConversionSettings(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.source_path: Path | None = None

        self.format_combo = QComboBox()
        self.format_combo.addItems(["MP4", "MKV"])

        self.quality_combo = QComboBox()
        self.quality_combo.addItems(["高质量", "均衡", "较小体积"])
        self.quality_combo.setCurrentText("均衡")

        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("请选择输出文件路径")

        self.browse_button = QPushButton("另存为…")
        self.browse_button.clicked.connect(self.choose_output)

        self.format_combo.currentTextChanged.connect(
            self.on_format_changed
        )

        output_row = QHBoxLayout()
        output_row.addWidget(self.output_edit)
        output_row.addWidget(self.browse_button)

        layout = QFormLayout()
        layout.addRow("输出格式", self.format_combo)
        layout.addRow("质量预设", self.quality_combo)
        layout.addRow("保存到", output_row)

        self.setLayout(layout)

    def set_source(self, source_path: Path):
        """主窗口选好视频后，调用此方法生成默认输出路径。"""
        self.source_path = source_path

        extension = self.format_combo.currentText().lower()
        filename = f"{source_path.stem}_converted.{extension}"
        output_path = source_path.parent / filename

        self.output_edit.setText(str(output_path))

    def on_format_changed(self, format_name: str):
        """切换格式时，同步修改输出文件扩展名。"""
        text = self.output_edit.text().strip()

        if not text:
            return

        output_path = Path(text).with_suffix(
            f".{format_name.lower()}"
        )
        self.output_edit.setText(str(output_path))

    def choose_output(self):
        extension = self.format_combo.currentText().lower()

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "选择输出文件",
            self.output_edit.text(),
            f"{extension.upper()} 视频 (*.{extension})",
        )

        if not file_path:
            return

        output_path = Path(file_path)

        if output_path.suffix.lower() != f".{extension}":
            output_path = output_path.with_suffix(f".{extension}")

        self.output_edit.setText(str(output_path))

    def get_options(self) -> dict:
        """供主窗口读取用户选择。"""
        return {
            "format": self.format_combo.currentText(),
            "quality": self.quality_combo.currentText(),
            "output_path": self.output_edit.text().strip(),
        }


if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = ConversionSettings()
    window.setWindowTitle("转换设置测试")
    window.resize(700, 180)
    window.show()

    sys.exit(app.exec())