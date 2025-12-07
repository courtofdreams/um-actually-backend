import json
from typing import Dict, Any, List

from schemas.text_analysis import TextAnalysisResponse
from schemas.video_analysis import VideoTranscriptAnalysisResponse, TranscriptSegment
from services.openai_service import run_text_analysis


TEXT_ANALYSIS_SYSTEM_PROMPT = """
You are a fact-checking and text analysis assistant.

Return ONLY a single JSON object with this exact structure and field names:

{
  "confidenceScores": number,
  "reasoning": string,
  "htmlContent": string,
  "sourcesList": [
    {
      "claim": string,
      "confidenceReason": string,
      "ratingPercent": number,
      "sources": [
        {
          "title": string,
          "claimReference": string?,
          "url": string,
          "ratingStance": "Mostly Support" | "Partially Support" | "Opposite",
          "snippet": string,
          "datePosted": string
        }
      ]
    }
  ]
}

Requirements:
- "confidenceScores" = overall confidence in your fact-checking for the WHOLE text (0-100).
- "htmlContent" should be the full text with inline markers from claim to numbers [1], [2], [3]... wrapped in <span class="marker"> claim [1] </span>. DO NOT add markers for sentences without claims.
- "reasoning" should explain your overall analysis approach and findings.
- "sourcesList" should align those [n] markers with external sources.
For each source in "sources":
- "snippet" is a short excerpt from the source supporting your analysis.
- "ratingStance" is your evaluation of the source's position relative to the claim.
- "ratingPercent" is your confidence in that specific claim (0-100).
- "url" is the direct link to the source.
- "title" is the title of the source article or page.
- "datePosted" is the publication date of the source.
- "claimReference" is optional; include it if the source explicitly references the claim for example, the claim "The UK left the EU in 2019" might have a claimReference "left the EU in 2019".
If you are uncertain or have limited information, lower ratingPercent and explain why in confidenceReason.
"""


def run_text_analysis_with_openai(text: str) -> TextAnalysisResponse:
    user_payload = {"text": text}

    raw = run_text_analysis(
        system_prompt=TEXT_ANALYSIS_SYSTEM_PROMPT,
        user_payload=user_payload,
        model="gpt-4.1",
        temperature=0.1,
    )

    try:
        data: Dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError:
        data = {
            "confidenceScores": 0,
            "reasoning": "Model returned invalid JSON.",
            "htmlContent": text,
            "sourcesList": [],
        }

    return TextAnalysisResponse(**data)


VIDEO_TRANSCRIPT_ANALYSIS_SYSTEM_PROMPT = """
You are a fact-checking assistant for video transcript analysis.

You will receive a list of transcript segments with timestamps. Each segment has:
- id: unique identifier
- text: the spoken text
- startTime: start time in seconds
- endTime: end time in seconds

Return ONLY a single JSON object with this exact structure:

{
  "videoId": string,
  "confidenceScores": number,
  "reasoning": string,
  "segments": [
    {
      "id": string,
      "text": string,
      "startTime": number,
      "endTime": number,
      "claim": string (optional),
      "claimIndex": number (optional)
    }
  ],
  "sourcesList": [
    {
      "claim": string,
      "confidenceReason": string,
      "ratingPercent": number,
      "sources": [
        {
          "title": string,
          "claimReference": string?,
          "url": string,
          "ratingStance": "Mostly Support" | "Partially Support" | "Opposite",
          "snippet": string,
          "datePosted": string
        }
      ]
    }
  ]
}

Requirements:
- "confidenceScores" = overall confidence in your fact-checking (0-100).
- "reasoning" should explain your overall analysis approach and key findings.

CRITICAL REQUIREMENT - You MUST return ALL segments:
- "segments" array MUST contain EVERY SINGLE segment from the input, in the SAME order.
- Count the input segments and return the EXACT same number.
- For segments WITHOUT claims: include them with only {id, text, startTime, endTime}.
- For segments WITH claims: add "claim" and "claimIndex" fields.
- Most segments will NOT have claims - that's normal and expected.

For segments with factual claims:
  - "claim" should be the EXACT text of the claim from that segment (can be a phrase or full sentence).
  - "claimIndex" should match the index in "sourcesList" (starting from 0).

- "sourcesList" should provide sources for each unique claim identified.
- For each source:
  - "snippet" is a short excerpt from the source supporting your analysis.
  - "ratingStance" is your evaluation of the source's position relative to the claim.
  - "ratingPercent" is your confidence in that specific claim (0-100).
  - "url" is the direct link to the source.
  - "title" is the title of the source article or page.
  - "datePosted" is the publication date of the source.
  - "claimReference" is optional; include it if the source explicitly references the claim.

If you are uncertain or have limited information, lower ratingPercent and explain why in confidenceReason.
"""


def run_video_transcript_analysis_with_openai(
    video_id: str,
    segments: List[TranscriptSegment]
) -> VideoTranscriptAnalysisResponse:
    """
    Analyzes video transcript segments and identifies claims with sources.
    Only analyzes the first 2 minutes to save on API costs.
    """
    # Convert segments to dict for JSON serialization
    all_segments_data = [
        {
            "id": seg.id,
            "text": seg.text,
            "startTime": seg.startTime,
            "endTime": seg.endTime
        }
        for seg in segments
    ]

    # Filter to only first 2 minutes (120 seconds) for OpenAI analysis
    MAX_DURATION_SECONDS = 120
    segments_to_analyze = [
        seg for seg in all_segments_data
        if seg["startTime"] < MAX_DURATION_SECONDS
    ]

    print(f"\n>>> Total segments: {len(all_segments_data)}, analyzing first 2 minutes: {len(segments_to_analyze)} segments")
    print(f">>> First segment: {segments_to_analyze[0] if segments_to_analyze else 'None'}")
    print(f">>> Last segment to analyze: {segments_to_analyze[-1] if segments_to_analyze else 'None'}")

    user_payload = {
        "videoId": video_id,
        "segments": segments_to_analyze
    }

    raw = run_text_analysis(
        system_prompt=VIDEO_TRANSCRIPT_ANALYSIS_SYSTEM_PROMPT,
        user_payload=user_payload,
        model="gpt-4.1",
        temperature=0.1,
    )

    # Log the raw OpenAI response for debugging
    print("\n" + "="*80)
    print("RAW OPENAI RESPONSE FOR VIDEO ANALYSIS:")
    print("="*80)
    print(raw)
    print("="*80 + "\n")

    try:
        data: Dict[str, Any] = json.loads(raw)
        print(f"Parsed data: videoId={data.get('videoId')}, segments={len(data.get('segments', []))}, sourcesList={len(data.get('sourcesList', []))}")

        # Merge analyzed segments with remaining segments (after 2 minutes)
        analyzed_segments = data.get('segments', [])
        remaining_segments = [
            seg for seg in all_segments_data
            if seg["startTime"] >= MAX_DURATION_SECONDS
        ]

        # Combine: analyzed segments (first 2 min) + remaining segments (rest of video)
        all_segments_with_claims = analyzed_segments + remaining_segments
        data['segments'] = all_segments_with_claims

        print(f"Final: {len(analyzed_segments)} analyzed + {len(remaining_segments)} remaining = {len(all_segments_with_claims)} total segments")

    except json.JSONDecodeError as e:
        # Fallback if OpenAI returns invalid JSON
        print(f"ERROR: Failed to parse OpenAI JSON response: {e}")
        data = {
            "videoId": video_id,
            "confidenceScores": 0,
            "reasoning": "Model returned invalid JSON.",
            "segments": all_segments_data,
            "sourcesList": [],
        }

    return VideoTranscriptAnalysisResponse(**data)
