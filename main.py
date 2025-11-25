from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import yt_dlp
import logging
from typing import List
import json
from io import StringIO

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Um Actually Backend", version="1.0.0")

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Models
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

# Routes
@app.get("/")
async def root():
    return {"message": "Um Actually Backend API", "version": "1.0.0"}

@app.post("/api/transcript")
async def get_transcript(request: TranscriptRequest) -> TranscriptResponse:
    """
    Fetch YouTube video captions using yt-dlp.
    No authentication required - works for any video with subtitles.

    Args:
        request: Contains videoUrl and videoId

    Returns:
        TranscriptResponse with video ID, title, and segments with timestamps
    """
    try:
        logger.info(f"Fetching transcript for video: {request.videoId}")

        # Fetch video info and subtitles using yt-dlp
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'writesubtitles': True,
            'subtitle': ['en'],
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(request.videoUrl, download=False)
            except Exception as e:
                logger.error(f"Error fetching video: {str(e)}")
                raise HTTPException(status_code=404, detail="Video not found")

            video_title = info.get('title', 'Unknown')
            logger.info(f"Video title: {video_title}")

            # Try to get subtitles
            subtitles = None
            subtitle_format = None

            # First try regular subtitles
            if info.get('subtitles') and 'en' in info.get('subtitles', {}):
                subtitles = info['subtitles']['en']
                subtitle_format = 'regular'
                logger.info("Found regular subtitles")
            # Then try auto-generated captions
            elif info.get('automatic_captions') and 'en' in info.get('automatic_captions', {}):
                subtitles = info['automatic_captions']['en']
                subtitle_format = 'auto'
                logger.info("Found auto-generated captions")

            if not subtitles:
                logger.warning(f"No English subtitles found for video: {request.videoId}")
                raise HTTPException(
                    status_code=404,
                    detail="This video does not have English subtitles available"
                )

            # Find VTT format subtitle
            vtt_subtitle = None
            for sub in subtitles:
                if sub.get('ext') == 'vtt':
                    vtt_subtitle = sub
                    break

            # If no VTT, use first available
            if not vtt_subtitle:
                vtt_subtitle = subtitles[0]

            # Get the actual subtitle content
            subtitle_url = vtt_subtitle.get('url')
            logger.info(f"Downloading subtitle from: {subtitle_url}")

            # Download subtitle content
            import urllib.request
            try:
                with urllib.request.urlopen(subtitle_url) as response:
                    vtt_content = response.read().decode('utf-8')
            except Exception as e:
                logger.error(f"Error downloading subtitle: {str(e)}")
                raise HTTPException(status_code=500, detail="Failed to download subtitles")

            # Parse VTT to segments
            segments = parse_vtt_captions(vtt_content)

            if not segments:
                raise HTTPException(status_code=400, detail="Failed to parse subtitles")

            logger.info(f"Successfully fetched {len(segments)} subtitle segments")

            return TranscriptResponse(
                videoId=request.videoId,
                title=video_title,
                segments=segments
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching transcript: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching transcript: {str(e)}"
        )

def parse_vtt_captions(vtt_content: str) -> List[TranscriptSegment]:
    """
    Parse WebVTT caption format into transcript segments.
    Groups captions into ~5 second chunks for better UX.

    VTT format:
    WEBVTT

    00:00:00.000 --> 00:00:05.000
    This is the first caption

    00:00:05.000 --> 00:00:10.000
    This is the second caption
    """
    # First, parse individual captions
    raw_captions = []
    lines = vtt_content.strip().split("\n")

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Skip WEBVTT header and empty lines
        if not line or line.startswith("WEBVTT") or line.startswith("NOTE") or "-->" not in line:
            i += 1
            continue

        # Parse timestamp line
        if "-->" in line:
            try:
                time_parts = line.split("-->")
                start_time = parse_vtt_timestamp(time_parts[0].strip())
                end_time = parse_vtt_timestamp(time_parts[1].strip().split()[0])

                # Get caption text (next line(s) until empty line)
                caption_text = []
                i += 1
                while i < len(lines) and lines[i].strip():
                    text = lines[i].strip()
                    # Skip styling tags
                    if not text.startswith("<") and not text.endswith(">"):
                        caption_text.append(text)
                    i += 1

                if caption_text:
                    raw_captions.append({
                        "text": " ".join(caption_text),
                        "startTime": start_time,
                        "endTime": end_time
                    })
            except Exception as e:
                logger.warning(f"Error parsing caption line: {line}, error: {e}")

        i += 1

    # Now group captions into ~5 second segments
    segments = []
    segment_id = 0
    claim_id = 0

    if not raw_captions:
        return segments

    # Group captions - aim for roughly 5-second chunks
    i = 0
    while i < len(raw_captions):
        current_segment_start = raw_captions[i]["startTime"]
        current_segment_text = []
        current_segment_end = raw_captions[i]["endTime"]

        # Accumulate captions until we reach ~5 seconds
        while i < len(raw_captions):
            caption = raw_captions[i]
            current_segment_text.append(caption["text"])
            current_segment_end = caption["endTime"]

            # Check if we've accumulated enough (roughly 5 seconds worth)
            duration = current_segment_end - current_segment_start
            i += 1

            # Break if we've reached 5 seconds or more, or if this is the last caption
            if duration >= 5 or i >= len(raw_captions):
                break

        # Create segment from accumulated captions
        if current_segment_text:
            segment_text = " ".join(current_segment_text)

            # Extract first 2 words as claim for highlighting/clicking
            words = segment_text.split()[:2]
            claim_text = " ".join(words) if words else segment_text

            segments.append(TranscriptSegment(
                id=f"seg_{segment_id}",
                text=segment_text,
                startTime=current_segment_start,
                endTime=current_segment_end,
                claim=claim_text,
                claimIndex=claim_id
            ))

            claim_id += 1
            segment_id += 1

    return segments

def parse_vtt_timestamp(timestamp_str: str) -> float:
    """
    Convert VTT timestamp to seconds.
    Format: HH:MM:SS.mmm or MM:SS.mmm
    """
    parts = timestamp_str.split(":")

    if len(parts) == 3:
        hours, minutes, seconds = parts
        return float(hours) * 3600 + float(minutes) * 60 + float(seconds)
    elif len(parts) == 2:
        minutes, seconds = parts
        return float(minutes) * 60 + float(seconds)
    else:
        return float(timestamp_str)

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
