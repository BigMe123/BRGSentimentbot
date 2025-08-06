"""Multimodal ingestion utilities."""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Dict

import logging
import requests


logger = logging.getLogger(__name__)


def ocr_image_from_url(url: str) -> str:
    """Download an image and return OCR text."""

    import cv2
    import numpy as np
    import pytesseract

    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    img = np.frombuffer(resp.content, dtype=np.uint8)
    img = cv2.imdecode(img, cv2.IMREAD_COLOR)
    return pytesseract.image_to_string(img)


def transcribe_video_from_url(url: str) -> str:
    """Download a video, extract audio and return Whisper transcript."""

    import ffmpeg
    import whisper

    with tempfile.TemporaryDirectory() as tmpdir:
        video_path = Path(tmpdir) / "video.mp4"
        audio_path = Path(tmpdir) / "audio.wav"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        video_path.write_bytes(resp.content)
        (
            ffmpeg.input(str(video_path))
            .output(str(audio_path), ac=1, ar=16000)
            .run(quiet=True)
        )
        model = whisper.load_model("tiny")
        result = model.transcribe(str(audio_path))
        return result["text"]


def aggregate_article_text(article: Dict[str, str]) -> str:
    """Combine text, image OCR and video transcripts for an article."""

    parts = [article.get("text", "")]
    if img := article.get("image_url"):
        try:
            parts.append(ocr_image_from_url(img))
        except Exception as exc:  # pragma: no cover - network/ocr errors
            logger.exception("Image OCR failed for %s", img)
            raise exc
    if vid := article.get("video_url"):
        try:
            parts.append(transcribe_video_from_url(vid))
        except Exception:  # pragma: no cover - network/ffmpeg errors
            pass
    return "\n".join(p for p in parts if p)
