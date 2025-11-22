import logging
from fastapi import APIRouter, HTTPException

from schemas.text_analysis import (
    TextAnalysisRequest,
    TextAnalysisResponse,
)
from services.analysis_service import run_text_analysis_with_openai

router = APIRouter()

@router.post("/text-analysis", response_model=TextAnalysisResponse)
def text_analysis(req: TextAnalysisRequest):
    """
    Run fact-checking / text analysis on the given text.
    """
    try:
        return run_text_analysis_with_openai(req.text)
    except Exception as e:
        logging.error(f"Text Analysis error: {e}")
        raise HTTPException(
            status_code=500,
            detail="Text Analysis service error",
        )
