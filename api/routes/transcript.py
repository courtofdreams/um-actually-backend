import os
import base64
import tempfile
import re
from fastapi import APIRouter, HTTPException
from typing import List, Optional
from schemas.transcript import TranscriptRequest, TranscriptResponse, TranscriptSegment
import logging
import yt_dlp
from config import settings

router = APIRouter()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_cookie_file_path: Optional[str] = None


def get_cookie_file_path() -> Optional[str]:
    global _cookie_file_path

    if _cookie_file_path and os.path.exists(_cookie_file_path):
        return _cookie_file_path

    cookies_b64 = settings.YOUTUBE_COOKIES_BASE64
    if not cookies_b64 or cookies_b64 == "":
        logger.info("No YouTube cookies configured - running without authentication")
        return None

    try:
        cookies_content = base64.b64decode(cookies_b64).decode('utf-8')
        fd, path = tempfile.mkstemp(suffix='.txt', prefix='yt_cookies_')
        with os.fdopen(fd, 'w') as f:
            f.write(cookies_content)
        _cookie_file_path = path
        logger.info("YouTube cookies loaded successfully")
        return path
    except Exception as e:
        logger.error(f"Failed to decode YouTube cookies: {e}")
        return None


@router.post("/transcript")
async def get_transcript(request: TranscriptRequest) -> TranscriptResponse:
    try:
        logger.info(f"Fetching transcript for video: {request.videoId}")

        with tempfile.TemporaryDirectory() as tmpdir:
            output_template = os.path.join(tmpdir, '%(id)s.%(ext)s')

            ydl_opts = {
                'writesubtitles': True,       # Write manually uploaded subtitles
                'writeautomaticsub': True,    # Write auto-generated subtitles
                'subtitleslangs': ['en', 'en-orig', 'en-US'],
                'skip_download': True,        # Skip video — subtitles still get written
                'outtmpl': output_template,
                'subtitlesformat': 'vtt',
                'quiet': True,
                'no_warnings': False,
                'extractor_args': {
                    'youtube': {
                        # Try multiple clients for best compatibility
                        'player_client': ['web', 'android', 'mweb'],
                    }
                },
            }

            cookie_file = get_cookie_file_path()
            if cookie_file:
                ydl_opts['cookiefile'] = cookie_file
                logger.info("Using YouTube cookies for authentication")

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    # extract_info with download=False only fetches metadata
                    # but won't write subtitle files. We use download=True so
                    # yt-dlp processes post-processors (subtitle writing),
                    # while skip_download=True prevents the video from downloading.
                    info = ydl.extract_info(request.videoUrl, download=True)
                except yt_dlp.utils.DownloadError as e:
                    logger.error(f"yt-dlp error: {str(e)}")
                    raise HTTPException(status_code=404, detail="Video not found or unavailable")

                video_title = info.get('title', 'Unknown')
                logger.info(f"Video title: {video_title}")

                # Find the downloaded VTT subtitle file
                vtt_content = None
                for fname in os.listdir(tmpdir):
                    if fname.endswith('.vtt'):
                        vtt_path = os.path.join(tmpdir, fname)
                        with open(vtt_path, 'r', encoding='utf-8') as f:
                            vtt_content = f.read()
                        logger.info(f"Found subtitle file: {fname}")
                        break

                if not vtt_content:
                    logger.warning(f"No English subtitles found for video: {request.videoId}")
                    raise HTTPException(
                        status_code=404,
                        detail="This video does not have English subtitles available"
                    )

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
    Parse WebVTT caption format into transcript segments (~5 second chunks).
    Handles inline timing tags and deduplicates overlapping auto-generated cues.
    """
    raw_captions = []
    lines = vtt_content.strip().split("\n")

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        if not line or line.startswith("WEBVTT") or line.startswith("NOTE"):
            i += 1
            continue

        if "-->" in line:
            try:
                time_parts = line.split("-->")
                start_time = parse_vtt_timestamp(time_parts[0].strip())
                end_time = parse_vtt_timestamp(time_parts[1].strip().split()[0])

                caption_text = []
                i += 1
                while i < len(lines) and lines[i].strip():
                    text = lines[i].strip()
                    # Strip inline VTT timing tags e.g. <00:00:01.234> and <c> tags
                    text = re.sub(r'<[^>]+>', '', text).strip()
                    if text:
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

    # Deduplicate consecutive identical lines (very common in auto-generated VTTs)
    deduped = []
    for cap in raw_captions:
        if not deduped or deduped[-1]["text"] != cap["text"]:
            deduped.append(cap)
    raw_captions = deduped

    # Group into ~5 second segments
    segments = []
    segment_id = 0
    claim_id = 0

    if not raw_captions:
        return segments

    i = 0
    while i < len(raw_captions):
        current_segment_start = raw_captions[i]["startTime"]
        current_segment_text = []
        current_segment_end = raw_captions[i]["endTime"]

        while i < len(raw_captions):
            caption = raw_captions[i]
            current_segment_text.append(caption["text"])
            current_segment_end = caption["endTime"]
            duration = current_segment_end - current_segment_start
            i += 1
            if duration >= 5 or i >= len(raw_captions):
                break

        if current_segment_text:
            segment_text = " ".join(current_segment_text)
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
    parts = timestamp_str.split(":")
    if len(parts) == 3:
        hours, minutes, seconds = parts
        return float(hours) * 3600 + float(minutes) * 60 + float(seconds)
    elif len(parts) == 2:
        minutes, seconds = parts
        return float(minutes) * 60 + float(seconds)
    else:
        return float(timestamp_str)