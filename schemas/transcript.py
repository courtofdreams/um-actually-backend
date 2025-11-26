# Models
from pydantic import BaseModel
from typing import List


class TranscriptRequest(BaseModel):
    videoUrl: str
    videoId: str

class TranscriptSegment(BaseModel):
    id: str
    text: str
    startTime: float
    endTime: float
    claim: str = ""
    claimIndex: int = 0

class TranscriptResponse(BaseModel):
    videoId: str
    title: str
    segments: List[TranscriptSegment]