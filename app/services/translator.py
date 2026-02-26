import json
import os
import re
import time

from google import genai
from google.genai import types

from app.schemas import SubtitleEntry, TranslatedEntry

BATCH_SIZE_GEMINI = 20
BATCH_SIZE_OPENAI_COMPAT = 10
GEMINI_MODEL = "gemini-2.5-flash"

PROVIDER_CONFIG = {
    "groq": {
        "host": "api.groq.com",
        "path": "/openai/v1/chat/completions",
        "model": "llama-3.3-70b-versatile",
    },
    "openrouter": {
        "host": "openrouter.ai",
        "path": "/api/v1/chat/completions",
        "model": "google/gemini-2.5-flash",
    },
    "grok": {
        "host": "api.x.ai",
        "path": "/v1/chat/completions",
        "model": "grok-3-mini-fast",
    },
    "deepseek": {
        "host": "api.deepseek.com",
        "path": "/chat/completions",
        "model": "deepseek-chat",
    },
}

SYSTEM_PROMPT = """영어 자막에 한글 발음(pronunciation)과 한글 번역(korean)을 추가하는 전문가입니다.

## 한글 번역
자연스러운 한국어. 의역 가능."""

TRANSLATE_PROMPT = """각 자막에 pronunciation(한글 발음)과 korean(한글 번역)을 추가하세요.
반드시 입력과 같은 개수, 같은 순서로 반환하세요.

## pronunciation 작성법: 원어민 연음 발음 표기

절대로 단어를 하나씩 끊어 읽지 마세요. 원어민이 빠르게 말할 때의 소리 흐름을 그대로 한글로 적습니다.
단어 사이 경계가 사라지고 소리가 이어지는 것이 핵심입니다.

### ❌ 나쁜 예 (단어 단위 — 이렇게 하지 마세요)
- "I want to get out of here" → "아이 원트 투 겟 아웃 오브 히어"
- "Check it out" → "체크 잇 아웃"
- "Not at all" → "낫 앳 올"
- "I'm going to take a look at it" → "아임 고잉 투 테이크 어 룩 앳 잇"
- "Would you like to come with us?" → "우드 유 라이크 투 컴 위드 어스?"
- "That's what I'm talking about" → "댓츠 왓 아임 토킹 어바웃"

### ✅ 좋은 예 (연음/축약 반영 — 이렇게 하세요)
- "I want to get out of here" → "아이워너 게라러브히어"
- "Check it out" → "체키라웃"
- "Not at all" → "나래럴"
- "I'm going to take a look at it" → "암고나 테이커루캐릿"
- "Would you like to come with us?" → "우쥬라이커 컴위더스?"
- "That's what I'm talking about" → "댓스와람 토킹어바웃"
- "I don't know what to do" → "아이도노 왓투두"
- "Can I get a cup of coffee?" → "캐나이게러 커퍼커피?"
- "He's kind of weird, isn't he?" → "히즈카인더 위어드, 이즌니?"
- "We need to figure it out" → "위니러 피겨리라웃"
- "Let me take a look at it" → "레미 테이커루캐릿"
- "I should have told you about it" → "아이슈러브 톨쥬어바우릿"

### 규칙 요약
1. 자음+모음이 만나면 무조건 연음: get it → 게릿, put on → 푸론, check it → 체킷
2. 모음 사이 t/d는 ㄹ로: water → 워러, got a → 가러, let it → 레릿
3. 축약 필수: want to→워너, going to→고나, have to→해프터, got to→가러, did you→디쥬, would you→우쥬
4. 기능어는 약하게 붙임: of→어/르, to→터/러, a→어, the→더, and→은/앤
5. 소리 덩어리 안은 붙여 쓰고, 덩어리 사이만 띄어 씁니다

반드시 아래 JSON 형식으로만 응답하세요. 다른 텍스트 없이 JSON 배열만 출력하세요.
[{{"index": 번호, "pronunciation": "한글발음", "korean": "한글번역"}}, ...]

입력:
{entries_json}"""

_response_schema = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "index": {"type": "INTEGER"},
            "pronunciation": {"type": "STRING"},
            "korean": {"type": "STRING"},
        },
        "required": ["index", "pronunciation", "korean"],
    },
}


# ─── Gemini ───

def _get_gemini_client(api_key: str) -> genai.Client:
    if not api_key:
        raise RuntimeError("Gemini API key is required")
    return genai.Client(api_key=api_key)


def _translate_batch_gemini(
    client: genai.Client,
    entries: list[dict],
) -> list[dict]:
    entries_json = json.dumps(entries, ensure_ascii=False, indent=2)
    prompt = TRANSLATE_PROMPT.format(entries_json=entries_json)

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=_response_schema,
            temperature=0.3,
        ),
    )
    return json.loads(response.text)


# ─── Groq (OpenAI-compatible) ───

def _extract_json_array(text: str) -> list[dict]:
    """응답에서 JSON 배열을 추출한다. 객체 래퍼나 마크다운 코드블록도 처리."""
    text = text.strip()
    # 마크다운 코드블록 제거
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```\s*$", "", text)
    text = text.strip()

    parsed = json.loads(text)

    # 바로 배열이면 그대로
    if isinstance(parsed, list):
        return parsed

    # 객체라면 첫 번째 배열 값을 찾기
    if isinstance(parsed, dict):
        for val in parsed.values():
            if isinstance(val, list) and len(val) > 0:
                return val

    raise ValueError(f"Could not extract array from response: {text[:200]}")


GROQ_TRANSLATE_PROMPT = """각 자막에 pronunciation(한글 발음)과 korean(한글 번역)을 추가하세요.

⚠️ 중요 규칙:
- 반드시 입력된 자막 개수({count}개)와 동일한 개수를 반환하세요.
- 각 항목에 원본 text를 그대로 포함하세요.
- 순서를 절대 바꾸지 마세요. 첫 번째 입력 → 첫 번째 출력.

## pronunciation 작성법: 원어민 연음 발음 표기

절대로 단어를 하나씩 끊어 읽지 마세요. 원어민이 빠르게 말할 때의 소리 흐름을 그대로 한글로 적습니다.

### ❌ 나쁜 예 (단어 단위)
- "Check it out" → "체크 잇 아웃"
- "Not at all" → "낫 앳 올"

### ✅ 좋은 예 (연음/축약 반영)
- "Check it out" → "체키라웃"
- "Not at all" → "나래럴"
- "I want to get out of here" → "아이워너 게라러브히어"
- "Would you like to come with us?" → "우쥬라이커 컴위더스?"

### 규칙 요약
1. 자음+모음이 만나면 연음: get it → 게릿
2. 모음 사이 t/d는 ㄹ: water → 워러
3. 축약: want to→워너, going to→고나, did you→디쥬
4. 기능어 약하게 붙임: of→어, to→터, a→어
5. 소리 덩어리 안은 붙여 쓰기

JSON 형식: [{{"index": 번호, "text": "원본텍스트", "pronunciation": "한글발음", "korean": "한글번역"}}, ...]

입력 ({count}개):
{entries_json}"""


def _translate_batch_openai_compat(
    api_key: str,
    entries: list[dict],
    provider: str,
) -> list[dict]:
    """Groq, OpenRouter 등 OpenAI 호환 API로 번역한다."""
    import http.client

    cfg = PROVIDER_CONFIG[provider]
    entries_json = json.dumps(entries, ensure_ascii=False, indent=2)
    prompt = GROQ_TRANSLATE_PROMPT.format(entries_json=entries_json, count=len(entries))

    body = json.dumps({
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT + "\n\nJSON 배열로만 응답하세요. 입력과 정확히 같은 개수, 같은 순서로 반환하세요. 각 항목에 원본 text를 포함하세요."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 4096,
        "response_format": {"type": "json_object"},
    }).encode("utf-8")

    conn = http.client.HTTPSConnection(cfg["host"], timeout=120)
    conn.request(
        "POST",
        cfg["path"],
        body=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    resp = conn.getresponse()
    resp_body = resp.read().decode("utf-8")
    conn.close()

    if resp.status != 200:
        raise RuntimeError(f"{provider} API error {resp.status}: {resp_body[:300]}")

    result = json.loads(resp_body)
    content = result["choices"][0]["message"]["content"]
    return _extract_json_array(content)


# ─── Unified stream ───

def translate_subtitles_stream(
    subtitles: list[SubtitleEntry],
    api_key: str,
    provider: str = "gemini",
):
    """배치별로 번역 결과를 yield하는 제너레이터."""
    if not api_key:
        raise RuntimeError(f"{provider} API key is required")

    if provider == "gemini":
        client = _get_gemini_client(api_key)
    elif provider not in PROVIDER_CONFIG:
        raise RuntimeError(f"Unknown provider: {provider}")

    is_openai_compat = provider in PROVIDER_CONFIG
    batch_size = BATCH_SIZE_GEMINI if provider == "gemini" else BATCH_SIZE_OPENAI_COMPAT

    batches = []
    for i in range(0, len(subtitles), batch_size):
        batches.append(subtitles[i : i + batch_size])

    total = len(batches)

    for batch_idx, batch in enumerate(batches):
        entries_for_api = [
            {"index": s.index, "text": s.text} for s in batch
        ]

        translated = None
        last_error = None
        for attempt in range(3):
            try:
                if provider == "gemini":
                    translated = _translate_batch_gemini(client, entries_for_api)
                else:
                    translated = _translate_batch_openai_compat(api_key, entries_for_api, provider)
                # OpenAI 호환 API: 개수 불일치 시 재시도
                if is_openai_compat and translated and len(translated) != len(batch):
                    last_error = f"Count mismatch: expected {len(batch)}, got {len(translated)}"
                    translated = None
                    if attempt < 2:
                        time.sleep(3)
                    continue
                last_error = None
                break
            except Exception as e:
                last_error = str(e)
                if attempt < 2:
                    time.sleep(5)

        failed = False
        if not translated:
            failed = True
            translated = [
                {"index": e["index"], "pronunciation": "", "korean": ""}
                for e in entries_for_api
            ]

        # 매핑 전략 결정
        entries = []
        if is_openai_compat:
            # Groq: text 기반 매핑 → 순서 기반 fallback
            text_map = {}
            for t in translated:
                txt = t.get("text", "").strip()
                if txt:
                    text_map[txt.lower()] = t

            matched_by_text = sum(1 for sub in batch if sub.text.strip().lower() in text_map)

            for i, sub in enumerate(batch):
                t = text_map.get(sub.text.strip().lower())
                if not t and i < len(translated):
                    t = translated[i]  # 순서 기반 fallback
                if not t:
                    t = {}
                entries.append(TranslatedEntry(
                    index=sub.index,
                    start_ms=sub.start_ms,
                    end_ms=sub.end_ms,
                    start_time=sub.start_time,
                    end_time=sub.end_time,
                    text=sub.text,
                    pronunciation=t.get("pronunciation", ""),
                    korean=t.get("korean", ""),
                ))
        else:
            # Gemini: index 기반 매핑
            trans_map = {t.get("index"): t for t in translated if "index" in t}
            for sub in batch:
                t = trans_map.get(sub.index, {})
                entries.append(TranslatedEntry(
                    index=sub.index,
                    start_ms=sub.start_ms,
                    end_ms=sub.end_ms,
                    start_time=sub.start_time,
                    end_time=sub.end_time,
                    text=sub.text,
                    pronunciation=t.get("pronunciation", ""),
                    korean=t.get("korean", ""),
                ))

        yield batch_idx + 1, total, entries, failed, last_error

        if batch_idx < total - 1:
            time.sleep(2)
