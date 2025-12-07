from pydantic import BaseModel
from typing import List, Optional


class TranscriptSegment(BaseModel):
    id: str
    text: str
    startTime: float
    endTime: float
    claim: Optional[str] = None
    claimIndex: Optional[int] = None


class Source(BaseModel):
    title: str
    claimReference: Optional[str] = None
    url: str
    ratingStance: str  # "Mostly Support" | "Partially Support" | "Opposite"
    snippet: str
    datePosted: str


class SourceGroup(BaseModel):
    claim: str
    confidenceReason: str
    ratingPercent: int
    sources: List[Source]


class VideoTranscriptAnalysisRequest(BaseModel):
    videoId: str
    segments: List[TranscriptSegment]


class VideoTranscriptAnalysisResponse(BaseModel):
    videoId: str
    confidenceScores: int
    reasoning: str
    segments: List[TranscriptSegment]  # Updated with claims identified by OpenAI
    sourcesList: List[SourceGroup]
