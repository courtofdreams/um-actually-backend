import json
from typing import Dict, Any, List
from datetime import datetime

from schemas.text_analysis import TextAnalysisResponse
from schemas.video_analysis import VideoTranscriptAnalysisResponse, TranscriptSegment
from services.openai_service import run_text_analysis
from services.search_service import search_for_claim, TRUSTED_FACT_CHECK_DOMAINS


def get_current_date_string() -> str:
    """Get the current date formatted for prompt injection."""
    return datetime.now().strftime("%B %d, %Y")


# Updated prompt that focuses on identifying claims, not generating URLs
TEXT_ANALYSIS_SYSTEM_PROMPT_TEMPLATE = """
You are a fact-checking and text analysis assistant.

IMPORTANT: Today's date is {current_date}. Your training data may be outdated.
When assessing claims about recent events, do NOT mark them as "future events" or "unverifiable" 
simply because they occurred after your training cutoff. Real-time search results will be used
to verify these claims, and you should generate appropriate search queries for them.

Your job is to identify factual claims in the text and assess their verifiability.
DO NOT make up URLs or sources - real sources will be found separately.

Return ONLY a single JSON object with this exact structure:

{{
  "confidenceScores": number,
  "reasoning": string,
  "htmlContent": string,
  "claims": [
    {{
      "claim": string,
      "claimText": string,
      "confidenceReason": string,
      "ratingPercent": number,
      "searchQuery": string
    }}
  ]
}}

Requirements:
- "confidenceScores" = overall confidence in the factual accuracy of the WHOLE text (0-100).
- "htmlContent" should be the full text with inline markers from claim to numbers [1], [2], [3]... wrapped in <span class="marker"> claim [1] </span>. DO NOT add markers for sentences without factual claims.
- "reasoning" should explain your overall analysis approach and findings.
- "claims" should list each identified claim with:
  - "claim": The claim being checked (e.g., "The UK left the EU in 2020")
  - "claimText": The exact text from the source that contains this claim
  - "confidenceReason": Why you rate this claim at this confidence level
  - "ratingPercent": Your confidence in this claim (0-100) based on your knowledge AND the fact that recent events will be verified via real-time search
  - "searchQuery": A good search query to find sources about this claim (for fact-checking)

For recent events (within the last 1-2 years), set a moderate confidence (40-60%) and note that 
verification depends on search results. Do NOT automatically give low confidence just because 
the event is recent or outside your training data.

Focus on identifying verifiable factual claims - dates, statistics, events, scientific facts, etc.
"""


def run_text_analysis_with_openai(text: str) -> TextAnalysisResponse:
    user_payload = {"text": text}
    
    # Format the prompt with the current date
    system_prompt = TEXT_ANALYSIS_SYSTEM_PROMPT_TEMPLATE.format(
        current_date=get_current_date_string()
    )

    raw = run_text_analysis(
        system_prompt=system_prompt,
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
            "claims": [],
        }

    # Now search for real sources for each claim
    claims = data.get("claims", [])
    sources_list = []
    
    for i, claim_data in enumerate(claims):
        claim_text = claim_data.get("claim", "")
        search_query = claim_data.get("searchQuery", claim_text)
        
        # Search for real sources using Tavily
        search_results = search_for_claim(
            search_query,
            max_results=3,
            include_domains=TRUSTED_FACT_CHECK_DOMAINS[:10]  # Top trusted domains
        )
        
        # Convert search results to our source format
        sources = []
        for result in search_results:
            # Determine stance based on search result score and content
            # This is a heuristic - higher scores generally mean more relevant/supportive
            score = result.get("score", 0)
            if score > 0.8:
                stance = "Mostly Support"
            elif score > 0.5:
                stance = "Partially Support"
            else:
                stance = "Partially Support"  # Default to partial for found sources
                
            sources.append({
                "title": result.get("title", "Unknown Source"),
                "url": result.get("url", ""),
                "snippet": result.get("snippet", ""),
                "datePosted": result.get("published_date", "Unknown"),
                "ratingStance": stance,
                "claimReference": claim_data.get("claimText", ""),
            })
        
        # If no sources found from search, note this
        if not sources:
            sources.append({
                "title": "No verified sources found",
                "url": "",
                "snippet": "Unable to find verified sources for this claim. Please verify independently.",
                "datePosted": "",
                "ratingStance": "Partially Support",
                "claimReference": claim_data.get("claimText", ""),
            })
        
        sources_list.append({
            "claim": claim_text,
            "confidenceReason": claim_data.get("confidenceReason", ""),
            "ratingPercent": claim_data.get("ratingPercent", 50),
            "sources": sources,
        })
    
    # Build final response
    return TextAnalysisResponse(
        confidenceScores=data.get("confidenceScores", 0),
        reasoning=data.get("reasoning", ""),
        htmlContent=data.get("htmlContent", text),
        sourcesList=sources_list,
    )


# Updated video transcript prompt - focuses on claim identification
VIDEO_TRANSCRIPT_ANALYSIS_SYSTEM_PROMPT_TEMPLATE = """
You are a fact-checking assistant for video transcript analysis.

IMPORTANT: Today's date is {current_date}. Your training data may be outdated.
When assessing claims about recent events, do NOT mark them as "future events" or "unverifiable" 
simply because they occurred after your training cutoff. Real-time search results will be used
to verify these claims, and you should generate appropriate search queries for them.

You will receive a list of transcript segments with timestamps. Each segment has:
- id: unique identifier
- text: the spoken text
- startTime: start time in seconds
- endTime: end time in seconds

Your job is to identify factual claims that can be verified.
DO NOT make up URLs or sources - real sources will be found separately.

Return ONLY a single JSON object with this exact structure:

{{
  "videoId": string,
  "confidenceScores": number,
  "reasoning": string,
  "segments": [
    {{
      "id": string,
      "text": string,
      "startTime": number,
      "endTime": number,
      "claim": string (optional),
      "claimIndex": number (optional)
    }}
  ],
  "claims": [
    {{
      "claim": string,
      "claimText": string,
      "confidenceReason": string,
      "ratingPercent": number,
      "searchQuery": string
    }}
  ]
}}

Requirements:
- "confidenceScores" = overall confidence in the factual accuracy (0-100).
- "reasoning" should be a brief summary (around 50 words) explaining your analysis.

CRITICAL REQUIREMENT - You MUST return ALL segments:
- "segments" array MUST contain EVERY SINGLE segment from the input, in the SAME order.
- Count the input segments and return the EXACT same number.
- For segments WITHOUT claims: include them with only {{id, text, startTime, endTime}}.
- For segments WITH claims: add "claim" and "claimIndex" fields.
- Most segments will NOT have claims - that's normal and expected.

For segments with factual claims:
  - "claim" should be the EXACT text of the claim from that segment.
  - "claimIndex" should match the index in "claims" array (starting from 0).

- "claims" array should list each unique claim identified with:
  - "claim": The claim being checked
  - "claimText": The exact text from the transcript
  - "confidenceReason": Why you rate this claim at this confidence
  - "ratingPercent": Your confidence in this claim (0-100) - for recent events, use moderate confidence (40-60%) as real-time search will verify
  - "searchQuery": A good search query to find sources about this claim

For recent events (within the last 1-2 years), set a moderate confidence (40-60%) and note that 
verification depends on search results. Do NOT automatically give low confidence just because 
the event is recent or outside your training data.

Focus on identifying verifiable factual claims - dates, statistics, events, scientific facts, etc.
"""


def run_video_transcript_analysis_with_openai(
    video_id: str,
    segments: List[TranscriptSegment]
) -> VideoTranscriptAnalysisResponse:
    """
    Analyzes video transcript segments and identifies claims with sources.
    Only analyzes the first 3 minutes to save on API costs.
    Uses real search to find verified sources for claims.
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

    # Filter to only first 3 minutes (180 seconds) for OpenAI analysis
    MAX_DURATION_SECONDS = 180
    segments_to_analyze = [
        seg for seg in all_segments_data
        if seg["startTime"] < MAX_DURATION_SECONDS
    ]

    print(f"\n>>> Total segments: {len(all_segments_data)}, analyzing first 3 minutes: {len(segments_to_analyze)} segments")
    print(f">>> First segment: {segments_to_analyze[0] if segments_to_analyze else 'None'}")
    print(f">>> Last segment to analyze: {segments_to_analyze[-1] if segments_to_analyze else 'None'}")

    user_payload = {
        "videoId": video_id,
        "segments": segments_to_analyze
    }

    # Format the prompt with the current date
    system_prompt = VIDEO_TRANSCRIPT_ANALYSIS_SYSTEM_PROMPT_TEMPLATE.format(
        current_date=get_current_date_string()
    )

    raw = run_text_analysis(
        system_prompt=system_prompt,
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
        print(f"Parsed data: videoId={data.get('videoId')}, segments={len(data.get('segments', []))}, claims={len(data.get('claims', []))}")

        # Merge analyzed segments with remaining segments (after 3 minutes)
        analyzed_segments = data.get('segments', [])
        remaining_segments = [
            seg for seg in all_segments_data
            if seg["startTime"] >= MAX_DURATION_SECONDS
        ]

        # Combine: analyzed segments (first 3 min) + remaining segments (rest of video)
        all_segments_with_claims = analyzed_segments + remaining_segments
        data['segments'] = all_segments_with_claims

        print(f"Final: {len(analyzed_segments)} analyzed + {len(remaining_segments)} remaining = {len(all_segments_with_claims)} total segments")

        # Now search for real sources for each identified claim
        claims = data.get("claims", [])
        sources_list = []
        
        for i, claim_data in enumerate(claims):
            claim_text = claim_data.get("claim", "")
            search_query = claim_data.get("searchQuery", claim_text)
            
            print(f"Searching for claim {i}: {claim_text[:50]}...")
            
            # Search for real sources using Tavily
            search_results = search_for_claim(
                search_query,
                max_results=3,
                include_domains=TRUSTED_FACT_CHECK_DOMAINS[:10]
            )
            
            # Convert search results to our source format
            sources = []
            for result in search_results:
                score = result.get("score", 0)
                if score > 0.8:
                    stance = "Mostly Support"
                elif score > 0.5:
                    stance = "Partially Support"
                else:
                    stance = "Partially Support"
                    
                sources.append({
                    "title": result.get("title", "Unknown Source"),
                    "url": result.get("url", ""),
                    "snippet": result.get("snippet", ""),
                    "datePosted": result.get("published_date", "Unknown"),
                    "ratingStance": stance,
                    "claimReference": claim_data.get("claimText", ""),
                })
            
            if not sources:
                sources.append({
                    "title": "No verified sources found",
                    "url": "",
                    "snippet": "Unable to find verified sources for this claim. Please verify independently.",
                    "datePosted": "",
                    "ratingStance": "Partially Support",
                    "claimReference": claim_data.get("claimText", ""),
                })
            
            sources_list.append({
                "claim": claim_text,
                "confidenceReason": claim_data.get("confidenceReason", ""),
                "ratingPercent": claim_data.get("ratingPercent", 50),
                "sources": sources,
            })
        
        data['sourcesList'] = sources_list

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
