from pydantic import BaseModel, field_validator
import re


class SubtitleRequest(BaseModel):
    url: str

    @field_validator("url")
    @classmethod
    def validate_youtube_url(cls, v: str) -> str:
        pattern = r"(youtube\.com/watch\?|youtu\.be/|youtube\.com/shorts/)"
        if not re.search(pattern, v):
            raise ValueError("Invalid YouTube URL")
        return v


class SubtitleEntry(BaseModel):
    index: int
    start_ms: int
    end_ms: int
    start_time: str
    end_time: str
    text: str


class SubtitleResponse(BaseModel):
    video_id: str
    title: str
    subtitle_count: int
    subtitles: list[SubtitleEntry]


class TranslateRequest(BaseModel):
    video_id: str
    title: str
    api_key: str
    provider: str = "gemini"  # "gemini" or "groq"
    subtitles: list[SubtitleEntry]


class TranslatedEntry(BaseModel):
    index: int
    start_ms: int
    end_ms: int
    start_time: str
    end_time: str
    text: str
    pronunciation: str
    korean: str


class TranslateResponse(BaseModel):
    video_id: str
    title: str
    subtitle_count: int
    subtitles: list[TranslatedEntry]
