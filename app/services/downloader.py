import json
import re
import subprocess
import tempfile
import shutil
from pathlib import Path


def extract_video_id(url: str) -> str:
    """YouTube URL에서 video_id를 추출한다."""
    patterns = [
        r"(?:v=|youtu\.be/)([a-zA-Z0-9_-]{11})",
        r"youtube\.com/shorts/([a-zA-Z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    raise ValueError(f"Cannot extract video ID from URL: {url}")


def download_subtitles(video_id: str) -> tuple[Path, str]:
    """yt-dlp CLI로 영어 자막을 다운로드한다.

    Returns:
        (자막 파일 경로, 포맷("json3" or "vtt"))을 포함하는 튜플.
        호출자가 임시 디렉토리를 정리해야 한다.
    """
    tmp_dir = Path(tempfile.mkdtemp(prefix="ytsub_"))
    url = f"https://www.youtube.com/watch?v={video_id}"

    # json3 우선 시도, 실패시 vtt 폴백
    for sub_format in ("json3", "vtt"):
        result = subprocess.run(
            [
                "yt-dlp",
                "--write-auto-sub",
                "--sub-lang", "en",
                "--sub-format", sub_format,
                "--skip-download",
                "--output", str(tmp_dir / video_id),
                url,
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )

        # 다운로드된 자막 파일 찾기
        for ext in (f".en.{sub_format}", f".{sub_format}"):
            found = list(tmp_dir.glob(f"*{ext}"))
            if found:
                return found[0], sub_format

    # 자막을 찾지 못함 - 임시 디렉토리 정리
    shutil.rmtree(tmp_dir, ignore_errors=True)
    raise FileNotFoundError(f"No English subtitles found for video: {video_id}")


def get_video_info(video_id: str) -> dict:
    """yt-dlp CLI로 영상 제목 등 메타데이터를 추출한다."""
    url = f"https://www.youtube.com/watch?v={video_id}"
    result = subprocess.run(
        ["yt-dlp", "--dump-json", "--skip-download", url],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        return {"title": "", "duration": 0}
    info = json.loads(result.stdout)
    return {"title": info.get("title", ""), "duration": info.get("duration", 0)}
