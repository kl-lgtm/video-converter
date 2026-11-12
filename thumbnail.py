import subprocess
import sys
from pathlib import Path

from video_info import read_video_info


PROJECT_DIR = Path(__file__).resolve().parent
FFMPEG_PATH = PROJECT_DIR / "tools" / "ffmpeg" / "bin" / "ffmpeg.exe"


def extract_thumbnail(video_path: Path, stream_index: int) -> bytes:
    """提取视频第一帧，返回 PNG 图片数据。"""

    if not FFMPEG_PATH.is_file():
        raise ValueError("找不到 ffmpeg.exe，请检查工具目录")

    if not video_path.is_file():
        raise ValueError("视频文件不存在")

    command = [
        str(FFMPEG_PATH),
        "-hide_banner",
        "-loglevel", "error",
        "-nostdin",
        "-i", str(video_path),
        "-map", f"0:{stream_index}",
        "-frames:v", "1",
        "-vf", "scale=480:-2",
        "-f", "image2pipe",
        "-c:v", "png",
        "pipe:1",
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except subprocess.TimeoutExpired as exc:
        raise ValueError("提取缩略图超时") from exc
    except OSError as exc:
        raise ValueError(f"无法启动 FFmpeg：{exc}") from exc

    if result.returncode != 0:
        reason = result.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(f"提取缩略图失败：{reason or '未知错误'}")

    if not result.stdout.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("FFmpeg 没有返回有效的 PNG 图片数据")

    return result.stdout


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print('用法：python thumbnail.py "视频完整路径"')
        sys.exit(1)

    video_path = Path(sys.argv[1])

    try:
        info = read_video_info(video_path)
        image_data = extract_thumbnail(
            video_path,
            info["视频流索引"],
        )

        output_path = PROJECT_DIR / "thumbnail_test.png"
        output_path.write_bytes(image_data)
    except (ValueError, OSError) as exc:
        print(f"操作失败：{exc}")
        sys.exit(1)

    print(f"缩略图已保存：{output_path}")