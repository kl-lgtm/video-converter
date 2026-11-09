"""FFmpeg 参数、缩略图与输出文件安全处理（不依赖界面）。"""
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_DIR = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
FFMPEG_PATH = PROJECT_DIR / 'tools/ffmpeg/bin/ffmpeg.exe'
FFPROBE_PATH = PROJECT_DIR / 'tools/ffmpeg/bin/ffprobe.exe'
QUALITY = {'高质量': '18', '均衡': '23', '较小体积': '28'}
NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0


def duration_seconds(value):
    try:
        number = float(value)
        return number if math.isfinite(number) and number > 0 else None
    except (ValueError, TypeError):
        return None


def progress_percent(microseconds, duration):
    duration = duration_seconds(duration)
    if duration is None:
        return None
    try:
        seconds = float(microseconds) / 1_000_000
        return max(0, min(99, int(seconds / duration * 100)))
    except (ValueError, TypeError, OverflowError):
        return None


def validate_destination(source: Path, target: Path):
    if source.resolve() == target.resolve():
        raise ValueError('输出路径不能与源视频相同')
    if target.exists():
        raise ValueError('输出文件已存在，请换一个文件名；本工具不会覆盖已有文件')
    if not target.parent.is_dir():
        raise ValueError('输出目录不存在')
    if target.suffix.lower() not in ('.mp4', '.mkv'):
        raise ValueError('输出格式仅支持 MP4 或 MKV')


def new_temporary_output(target: Path) -> Path:
    handle, name = tempfile.mkstemp(prefix='.video-converter-', suffix=target.suffix, dir=target.parent)
    os.close(handle)
    return Path(name)


def publish_output(temporary: Path, target: Path):
    # Windows 的 rename 在目标存在时失败，不覆盖。临时文件与目标在同一目录。
    if os.name == 'nt':
        os.rename(temporary, target)
    else:
        os.link(temporary, target)
        temporary.unlink()


def conversion_arguments(source: Path, temporary: Path, quality: str, stream_index: int):
    args = [
        '-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
        '-i', str(source), '-map', f'0:{stream_index}', '-map', '0:a:0?',
        '-map_metadata', '-1', '-map_chapters', '-1',
        '-c:v', 'libx264', '-preset', 'fast', '-crf', QUALITY[quality],
        '-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2', '-pix_fmt', 'yuv420p',
        '-c:a', 'aac', '-b:a', '192k',
    ]
    if temporary.suffix.lower() == '.mp4':
        args += ['-movflags', '+faststart']
    return args + ['-progress', 'pipe:1', '-nostats', str(temporary)]


def thumbnail_bytes(source: Path, stream_index: int) -> bytes:
    if not FFMPEG_PATH.is_file():
        raise ValueError('找不到 ffmpeg.exe')
    result = subprocess.run(
        [str(FFMPEG_PATH), '-hide_banner', '-loglevel', 'error', '-nostdin',
         '-i', str(source), '-map', f'0:{stream_index}', '-frames:v', '1',
         '-vf', 'scale=480:270:force_original_aspect_ratio=decrease',
         '-f', 'image2pipe', '-c:v', 'png', 'pipe:1'],
        capture_output=True, timeout=30, creationflags=NO_WINDOW,
    )
    if result.returncode or not result.stdout:
        raise ValueError('无法提取缩略图，仍可尝试转换')
    return result.stdout
