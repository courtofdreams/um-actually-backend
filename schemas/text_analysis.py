from pydantic import BaseModel
from typing import List, Optional


class Source(BaseModel):
    title: str
    url: str  # Allow empty string when no source found
    ratingStance: str
    snippet: str
    datePosted: str
    claimReference: Optional[str] = None  


class SourceGroup(BaseModel):
    claim: str
    confidenceReason: str
    ratingPercent: int
    sources: List[Source]


class TextAnalysisResponse(BaseModel):
    confidenceScores: int
    reasoning: str
    htmlContent: str
    sourcesList: List[SourceGroup]


class TextAnalysisRequest(BaseModel):
    # you can expand later (language, url, platform, etc.)
    text: str
