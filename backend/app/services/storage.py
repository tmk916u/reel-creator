"""アップロード動画のローカルストレージ管理（design D3）。

MEDIA_DIR 配下に video_id 単位でディレクトリを作り、source.mp4 と
thumbnail.jpg を保存する。duration / thumbnail は best-effort。
"""
import os
import subprocess
from pathlib import Path

from app.services.ffmpeg import get_video_duration

MEDIA_DIR = Path(os.getenv("MEDIA_DIR", "/app/media"))
_CHUNK = 1024 * 1024


def video_dir(video_id: str) -> Path:
    return MEDIA_DIR / str(video_id)


def source_path(video_id: str) -> Path:
    return video_dir(video_id) / "source.mp4"


def thumbnail_path(video_id: str) -> Path:
    return video_dir(video_id) / "thumbnail.jpg"


def save_source(video_id: str, src, max_bytes: int | None = None) -> tuple[Path, int]:
    """アップロードされた MP4 をストリーム保存する。

    src: read(size) を持つファイルライク（FastAPI UploadFile.file 等）
    max_bytes 超過時は書きかけを削除して ValueError を送出する。
    戻り値: (保存先パス, バイト数)
    """
    d = video_dir(video_id)
    d.mkdir(parents=True, exist_ok=True)
    path = source_path(video_id)
    total = 0
    with path.open("wb") as out:
        while True:
            chunk = src.read(_CHUNK)
            if not chunk:
                break
            total += len(chunk)
            if max_bytes is not None and total > max_bytes:
                out.close()
                path.unlink(missing_ok=True)
                raise ValueError("ファイルサイズが上限を超えています")
            out.write(chunk)
    return path, total


def delete_video_files(video_id: str) -> None:
    import shutil
    shutil.rmtree(video_dir(video_id), ignore_errors=True)


def probe_duration(path: Path) -> int | None:
    try:
        return int(round(get_video_duration(str(path))))
    except Exception:
        return None


def generate_thumbnail(video_id: str) -> Path | None:
    """先頭フレームからサムネイルを生成する（失敗時 None）。"""
    src = source_path(video_id)
    dst = thumbnail_path(video_id)
    cmd = [
        "ffmpeg", "-y", "-ss", "0", "-i", str(src),
        "-frames:v", "1", "-vf", "scale=360:-2",
        str(dst),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode == 0 and dst.exists():
            return dst
    except Exception:
        pass
    return None
