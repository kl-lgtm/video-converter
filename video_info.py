import json
import subprocess
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
FFPROBE_PATH = PROJECT_DIR / "tools" / "ffmpeg" / "bin" / "ffprobe.exe"


def read_video_info(video_path: Path) -> dict:
    """读取视频信息，成功返回字典，失败抛出异常。"""

    if not FFPROBE_PATH.is_file():
        raise ValueError("找不到 ffprobe.exe，请检查工具目录")

    if not video_path.is_file():
        raise ValueError("视频文件不存在")

    command = [
        str(FFPROBE_PATH),
        "-v", "error",
        "-show_format",
        "-show_streams",
        "-of", "json",
        str(video_path),
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except subprocess.TimeoutExpired as exc:
        raise ValueError("读取视频信息超时") from exc
    except OSError as exc:
        raise ValueError(f"无法启动 ffprobe：{exc}") from exc

    if result.returncode != 0:
        reason = result.stderr.strip() or "未知错误"
        raise ValueError(f"读取失败：{reason}")

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("无法解析 ffprobe 返回的信息") from exc

    # 找到第一个真正的视频流，跳过音频和附带封面。
    video_stream = next(
        (
            stream
            for stream in data.get("streams", [])
            if stream.get("codec_type") == "video"
            and not stream.get("disposition", {}).get("attached_pic", 0)
        ),
        None,
    )

    if video_stream is None:
        raise ValueError("文件中没有找到视频画面流")

    format_info = data.get("format", {})

    return {
        "文件名": video_path.name,
        "视频流索引": video_stream["index"],
        "视频编码": video_stream.get("codec_name", "未知"),
        "宽度": video_stream.get("width"),
        "高度": video_stream.get("height"),
        "时长（秒）": format_info.get("duration"),
        "文件大小（字节）": video_path.stat().st_size,
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print('用法：python video_info.py "视频完整路径"')
        sys.exit(1)

    try:
        info = read_video_info(Path(sys.argv[1]))
    except (ValueError, OSError) as exc:
        print(f"读取失败：{exc}")
        sys.exit(1)

    print(json.dumps(info, ensure_ascii=False, indent=2))