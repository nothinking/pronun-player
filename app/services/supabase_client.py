"""Supabase REST API client using http.client (proxy-safe)."""
import http.client
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union

SUPABASE_URL = "gkfydaggnpvffynooyop.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImdrZnlkYWdnbnB2ZmZ5bm9veW9wIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzA4MjA3NTMsImV4cCI6MjA4NjM5Njc1M30.gZaIvHNwsCOFBiK8JTNE8iva8locKWjIvr3kbesdcTY"

_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}


def _request(method: str, path: str, body: Optional[Union[Dict, List]] = None, extra_headers: Optional[Dict[str, str]] = None) -> Tuple[int, str]:
    conn = http.client.HTTPSConnection(SUPABASE_URL, timeout=30)
    headers = {**_HEADERS}
    if extra_headers:
        headers.update(extra_headers)
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    conn.request(method, path, body=payload, headers=headers)
    resp = conn.getresponse()
    resp_body = resp.read().decode("utf-8")
    conn.close()
    return resp.status, resp_body


def save_translation(video_id: str, title: str, provider: str, subtitles: list[dict]) -> dict:
    """번역 결과를 Supabase에 저장한다. 같은 video_id+provider면 upsert."""
    row = {
        "video_id": video_id,
        "title": title,
        "provider": provider,
        "subtitles": subtitles,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    # upsert: on conflict (video_id, provider) → update
    status, body = _request(
        "POST",
        "/rest/v1/translations",
        body=row,
        extra_headers={
            "Prefer": "return=representation,resolution=merge-duplicates",
        },
    )
    if status not in (200, 201):
        raise RuntimeError(f"Supabase save error {status}: {body[:300]}")
    return json.loads(body)[0] if body.startswith("[") else json.loads(body)


def get_translations(video_id: str) -> list[dict]:
    """특정 video_id의 번역 목록을 가져온다."""
    path = f"/rest/v1/translations?video_id=eq.{video_id}&order=updated_at.desc"
    status, body = _request("GET", path)
    if status != 200:
        raise RuntimeError(f"Supabase get error {status}: {body[:300]}")
    return json.loads(body)


def get_history(limit: int = 20) -> list[dict]:
    """최근 번역 히스토리를 가져온다 (subtitles 제외)."""
    path = f"/rest/v1/translations?select=id,video_id,title,provider,updated_at&order=updated_at.desc&limit={limit}"
    status, body = _request("GET", path)
    if status != 200:
        raise RuntimeError(f"Supabase history error {status}: {body[:300]}")
    return json.loads(body)


def delete_translation(translation_id: str) -> bool:
    """번역 레코드를 삭제한다."""
    path = f"/rest/v1/translations?id=eq.{translation_id}"
    status, body = _request("DELETE", path)
    return status in (200, 204)
