import json
import re
from pathlib import Path

from app.schemas import SubtitleEntry


def format_timestamp(ms: int) -> str:
    """밀리초를 'HH:MM:SS,mmm' 형식으로 변환한다."""
    h = ms // 3_600_000
    m = (ms // 60_000) % 60
    s = (ms // 1_000) % 60
    remainder = ms % 1_000
    return f"{h:02d}:{m:02d}:{s:02d},{remainder:03d}"


def parse_json3(file_path: Path) -> list[dict]:
    """json3 포맷 자막 파일에서 세그먼트를 추출한다."""
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    segments = []
    for event in data.get("events", []):
        if "segs" not in event:
            continue
        text_parts = []
        for seg in event["segs"]:
            t = seg.get("utf8", "").strip()
            if t and t != "\n":
                text_parts.append(t)
        text = " ".join(text_parts).strip()
        if not text:
            continue
        start_ms = event.get("tStartMs", 0)
        dur_ms = event.get("dDurationMs", 0)
        segments.append({
            "start_ms": start_ms,
            "end_ms": start_ms + dur_ms,
            "text": text,
        })
    return segments


def _vtt_to_ms(ts: str) -> int:
    """VTT 타임스탬프를 밀리초로 변환한다."""
    ts = ts.strip().replace(",", ".")
    parts = ts.split(":")
    if len(parts) == 3:
        h, m, s = parts
    elif len(parts) == 2:
        h = "0"
        m, s = parts
    else:
        return 0
    return int(int(h) * 3_600_000 + int(m) * 60_000 + float(s) * 1_000)


def parse_vtt(file_path: Path) -> list[dict]:
    """VTT 포맷 자막 파일에서 세그먼트를 추출한다."""
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    segments = []
    blocks = re.split(r"\n\n+", content)
    for block in blocks:
        lines = block.strip().split("\n")
        time_line = None
        text_lines = []
        for line in lines:
            if "-->" in line:
                time_line = line
            elif time_line and line.strip():
                clean = re.sub(r"<[^>]+>", "", line).strip()
                if clean:
                    text_lines.append(clean)
        if time_line and text_lines:
            parts = time_line.split("-->")
            start_str = parts[0].strip()
            end_str = parts[1].strip().split()[0]
            segments.append({
                "start_ms": _vtt_to_ms(start_str),
                "end_ms": _vtt_to_ms(end_str),
                "text": " ".join(text_lines),
            })
    return segments


def deduplicate_segments(segments: list[dict]) -> list[dict]:
    """중복 텍스트 세그먼트를 제거한다."""
    segments.sort(key=lambda x: x["start_ms"])
    unique = []
    seen = set()
    for seg in segments:
        key = seg["text"].lower().strip()
        if key and key not in seen:
            seen.add(key)
            unique.append(seg)
    return unique


def parse_subtitle_file(file_path: Path, fmt: str) -> list[SubtitleEntry]:
    """자막 파일을 파싱하여 세그먼트 단위 SubtitleEntry 리스트를 반환한다."""
    if fmt == "json3":
        segments = parse_json3(file_path)
    elif fmt == "vtt":
        segments = parse_vtt(file_path)
    else:
        raise ValueError(f"Unsupported subtitle format: {fmt}")

    segments = deduplicate_segments(segments)

    entries = []
    for i, seg in enumerate(segments):
        text = re.sub(r"\s+", " ", seg["text"]).strip()
        if not text:
            continue
        entries.append(SubtitleEntry(
            index=i + 1,
            start_ms=seg["start_ms"],
            end_ms=seg["end_ms"],
            start_time=format_timestamp(seg["start_ms"]),
            end_time=format_timestamp(seg["end_ms"]),
            text=text,
        ))
    return entries
