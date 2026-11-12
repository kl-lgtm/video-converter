import math
import os
import subprocess
import sys
import tempfile
import threading
from collections import deque
from pathlib import Path
from typing import Callable

from video_info import read_video_info


PROJECT_DIR = Path(__file__).resolve().parent
FFMPEG_PATH = PROJECT_DIR / "tools" / "ffmpeg" / "bin" / "ffmpeg.exe"

QUALITY_PRESETS = {
    "高质量": "18",
    "均衡": "23",
    "较小体积": "28",
}


class ConversionCancelled(Exception):
    """用户取消了转换。"""


def convert_video(
    source_path: Path,
    output_path: Path,
    quality: str = "均衡",
    progress_callback: Callable[[int], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> Path:
    """转换视频，支持进度回调和取消请求。"""

    def check_cancelled():
        if cancel_event is not None and cancel_event.is_set():
            raise ConversionCancelled("已取消转换")

    check_cancelled()

    source_path = source_path.resolve()
    output_path = output_path.resolve()

    if not FFMPEG_PATH.is_file():
        raise ValueError("找不到 ffmpeg.exe")

    if not source_path.is_file():
        raise ValueError("源视频不存在")

    if source_path == output_path:
        raise ValueError("输出路径不能与源视频相同")

    if output_path.exists():
        raise ValueError("输出文件已存在，请换一个文件名")

    if not output_path.parent.is_dir():
        raise ValueError("输出目录不存在")

    if output_path.suffix.lower() not in (".mp4", ".mkv"):
        raise ValueError("输出格式仅支持 MP4 和 MKV")

    if quality not in QUALITY_PRESETS:
        raise ValueError("不支持的质量预设")

    info = read_video_info(source_path)
    check_cancelled()

    duration = None
    try:
        value = float(info.get("时长（秒）"))
        if math.isfinite(value) and value > 0:
            duration = value
    except (TypeError, ValueError):
        pass

    last_progress = -1

    def report_progress(percent: int):
        nonlocal last_progress

        if percent >= 0:
            percent = max(last_progress, percent)

            if percent == last_progress:
                return

            last_progress = percent

        if progress_callback is not None:
            progress_callback(percent)

    handle, temporary_name = tempfile.mkstemp(
        prefix=".video-converter-",
        suffix=output_path.suffix,
        dir=output_path.parent,
    )
    os.close(handle)

    temporary_path = Path(temporary_name)
    process = None
    monitor = None
    monitor_stop = threading.Event()

    try:
        command = [
            str(FFMPEG_PATH),
            "-hide_banner",
            "-loglevel", "error",
            "-nostdin",
            "-y",
            "-i", str(source_path),
            "-map", f"0:{info['视频流索引']}",
            "-map", "0:a:0?",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", QUALITY_PRESETS[quality],
            "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
        ]

        if output_path.suffix.lower() == ".mp4":
            command.extend(["-movflags", "+faststart"])

        command.extend([
            "-progress", "pipe:1",
            "-nostats",
            str(temporary_path),
        ])

        report_progress(0 if duration is not None else -1)
        check_cancelled()

        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

        def monitor_cancellation():
            # 独立检查取消请求。
            # 即使 FFmpeg 暂时没有输出，也可以终止它。
            while not monitor_stop.wait(0.1):
                if cancel_event.is_set():
                    if process.poll() is None:
                        try:
                            process.kill()
                        except OSError:
                            pass
                    return

        if cancel_event is not None:
            monitor = threading.Thread(
                target=monitor_cancellation,
                daemon=True,
            )
            monitor.start()

        recent_lines = deque(maxlen=40)

        for line in process.stdout:
            check_cancelled()

            line = line.strip()
            if not line:
                continue

            recent_lines.append(line)
            key, _, value = line.partition("=")

            if key == "out_time_us" and duration is not None:
                try:
                    processed_seconds = int(value) / 1_000_000
                except ValueError:
                    continue

                percent = int(processed_seconds / duration * 100)
                report_progress(max(0, min(99, percent)))

        return_code = process.wait()
        check_cancelled()

        if return_code != 0:
            reason = "\n".join(recent_lines) or "未知错误"
            raise ValueError(f"转换失败：{reason}")

        if temporary_path.stat().st_size == 0:
            raise ValueError("转换结果为空文件")

        read_video_info(temporary_path)
        check_cancelled()

        # 正式保存前仍检查取消请求。
        # Windows 下目标存在时，rename 不会覆盖它。
        os.rename(temporary_path, output_path)

        report_progress(100)
        return output_path

    finally:
        monitor_stop.set()

        if process is not None:
            if process.poll() is None:
                process.kill()
                process.wait()

            if process.stdout is not None:
                process.stdout.close()

        if monitor is not None:
            monitor.join()

        temporary_path.unlink(missing_ok=True)


def print_progress(percent: int):
    if percent == -1:
        print("正在转换，视频时长未知……", flush=True)
    else:
        print(f"转换进度：{percent}%", flush=True)


if __name__ == "__main__":
    if len(sys.argv) not in (3, 4):
        print(
            '用法：python converter.py "输入路径" "输出路径" '
            '["高质量/均衡/较小体积"]'
        )
        sys.exit(1)

    source = Path(sys.argv[1])
    output = Path(sys.argv[2])
    quality = sys.argv[3] if len(sys.argv) == 4 else "均衡"

    try:
        saved_path = convert_video(
            source,
            output,
            quality,
            progress_callback=print_progress,
        )
    except ConversionCancelled:
        print("已取消转换")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n已停止转换")
        sys.exit(130)
    except (ValueError, OSError) as exc:
        print(f"操作失败：{exc}")
        sys.exit(1)

    print(f"转换完成：{saved_path}")