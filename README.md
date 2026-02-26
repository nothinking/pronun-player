# pronun-player

YouTube 영상의 영어 자막을 추출하고, AI를 활용해 한글 발음(연음/축약 반영)과 번역을 제공하는 영어 발음 학습 도구입니다.

## 주요 기능

- **자막 추출** — YouTube URL에서 영어 자막 자동 추출
- **AI 번역** — 한글 발음 + 한글 번역 동시 생성 (SSE 실시간 스트리밍)
- **원어민 발음 표기** — 단어 단위가 아닌 연음/축약 기반 발음 (예: "Check it out" → "체키라웃")
- **멀티 AI 지원** — Gemini, Groq, OpenRouter, Grok, DeepSeek
- **DB 저장** — Supabase에 번역 결과 저장/불러오기
- **번역 제어** — 진행률 표시, 중지, provider 변경 후 재번역

## 기술 스택

- **Backend**: FastAPI, Python
- **Frontend**: Vanilla JS (단일 HTML)
- **AI**: Google Gemini, OpenAI-compatible API (Groq, OpenRouter, Grok, DeepSeek)
- **DB**: Supabase (PostgreSQL)
- **자막**: yt-dlp

## 실행 방법

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

http://localhost:8000 접속 후 YouTube URL 입력 → 자막 추출 → API 키 입력 → 번역

## Supabase 설정

Supabase SQL Editor에서 테이블 생성:

```sql
CREATE TABLE translations (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  video_id TEXT NOT NULL,
  title TEXT NOT NULL DEFAULT '',
  provider TEXT NOT NULL DEFAULT 'gemini',
  subtitles JSONB NOT NULL DEFAULT '[]',
  updated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(video_id, provider)
);

ALTER TABLE translations ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow all for anon" ON translations
  FOR ALL USING (true) WITH CHECK (true);
```

## 배포

Render (Docker):

```bash
# render.yaml 포함되어 있음
# Render 대시보드에서 GitHub repo 연결 후 자동 배포
```

## 라이선스

MIT
