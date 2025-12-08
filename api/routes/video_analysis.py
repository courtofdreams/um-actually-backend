import logging
from fastapi import APIRouter, HTTPException

from schemas.video_analysis import (
    VideoTranscriptAnalysisRequest,
    VideoTranscriptAnalysisResponse,
)
from services.analysis_service import run_video_transcript_analysis_with_openai

router = APIRouter()

@router.post("/video-analysis", response_model=VideoTranscriptAnalysisResponse)
def video_transcript_analysis(req: VideoTranscriptAnalysisRequest):
    """
    Run fact-checking / analysis on video transcript segments.
    Identifies claims and provides sources with timestamps.
    """
    try:
        return run_video_transcript_analysis_with_openai(
            video_id=req.videoId,
            segments=req.segments
        )
    except Exception as e:
        logging.error(f"Video Transcript Analysis error: {e}")
        raise HTTPException(
            status_code=500,
            detail="Video Transcript Analysis service error",
        )
