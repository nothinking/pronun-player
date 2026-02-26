import json
import shutil
from asyncio import get_event_loop

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.schemas import SubtitleRequest, SubtitleResponse, TranslateRequest, TranslateResponse
from app.services.downloader import extract_video_id, download_subtitles, get_video_info
from app.services.parser import parse_subtitle_file
from app.services.translator import translate_subtitles_stream
from app.services.supabase_client import save_translation, get_translations, get_history, delete_translation

router = APIRouter(prefix="/api", tags=["subtitles"])


@router.post("/subtitles", response_model=SubtitleResponse)
async def get_subtitles(req: SubtitleRequest):
    """YouTube URL로부터 영어 자막을 추출하여 JSON으로 반환한다."""
    try:
        video_id = extract_video_id(req.url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    loop = get_event_loop()

    # 영상 정보 추출
    try:
        info = await loop.run_in_executor(None, get_video_info, video_id)
    except Exception:
        info = {"title": "", "duration": 0}

    # 자막 다운로드
    try:
        sub_file, fmt = await loop.run_in_executor(None, download_subtitles, video_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="No English subtitles found for this video")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to download subtitles: {e}")

    # 자막 파싱
    try:
        subtitles = parse_subtitle_file(sub_file, fmt)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse subtitles: {e}")
    finally:
        # 임시 디렉토리 정리
        shutil.rmtree(sub_file.parent, ignore_errors=True)

    return SubtitleResponse(
        video_id=video_id,
        title=info["title"],
        subtitle_count=len(subtitles),
        subtitles=subtitles,
    )


@router.post("/translate")
async def translate(req: TranslateRequest):
    """자막에 한글 발음과 번역을 SSE 스트림으로 반환한다."""

    def generate():
        try:
            for batch_num, total_batches, entries, failed, error_msg in translate_subtitles_stream(
                req.subtitles, req.api_key, req.provider
            ):
                payload = {
                    "batch": batch_num,
                    "total": total_batches,
                    "entries": [e.model_dump() for e in entries],
                    "failed": failed,
                    "error_msg": error_msg,
                }
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except RuntimeError as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': f'Translation failed: {e}'})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# ─── Supabase 저장/조회 ───

class SaveRequest(BaseModel):
    video_id: str
    title: str
    provider: str
    subtitles: list[dict]


@router.post("/save")
async def save(req: SaveRequest):
    """번역 결과를 Supabase에 저장한다."""
    loop = get_event_loop()
    try:
        result = await loop.run_in_executor(
            None, save_translation, req.video_id, req.title, req.provider, req.subtitles
        )
        return {"ok": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/translations/{video_id}")
async def get_video_translations(video_id: str):
    """특정 영상의 저장된 번역 목록을 가져온다."""
    loop = get_event_loop()
    try:
        data = await loop.run_in_executor(None, get_translations, video_id)
        return {"ok": True, "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
async def history():
    """최근 번역 히스토리를 가져온다."""
    loop = get_event_loop()
    try:
        data = await loop.run_in_executor(None, get_history, 30)
        return {"ok": True, "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/translations/{translation_id}")
async def remove_translation(translation_id: str):
    """저장된 번역을 삭제한다."""
    loop = get_event_loop()
    ok = await loop.run_in_executor(None, delete_translation, translation_id)
    if not ok:
        raise HTTPException(status_code=500, detail="삭제 실패")
    return {"ok": True}
