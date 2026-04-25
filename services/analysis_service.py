"""
Um, Actually — Backend Analysis Service
4-agent pipeline: Orchestrator → [Claim Extractor ‖ Search Agent] → Verifier + Explainer

All public functions return plain dicts (JSON-serialisable).
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from schemas.text_analysis import TextAnalysisResponse
from schemas.video_analysis import VideoTranscriptAnalysisResponse, TranscriptSegment
from services.openai_service import run_text_analysis
from services.search_service import search_for_claim, TRUSTED_FACT_CHECK_DOMAINS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _today() -> str:
    return datetime.now().strftime("%B %d, %Y")


def _safe_json(raw: str, fallback: dict) -> dict:
    """Parse JSON, stripping markdown fences if the model wrapped the output."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        # Strip ```json ... ``` or ``` ... ```
        lines = cleaned.splitlines()
        cleaned = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return fallback


# ---------------------------------------------------------------------------
# Claim type classification helpers
# ---------------------------------------------------------------------------

CLAIM_TYPE_VERIFIABLE = "verifiable"
CLAIM_TYPE_ANONYMOUS  = "anonymous_source"
CLAIM_TYPE_INFERENCE  = "subjective_inference"

# Confidence ceiling per claim type — used by the Verifier agent to cap scores
# and to generate honest explanations for the UI.
CONFIDENCE_CEILING: dict[str, int] = {
    CLAIM_TYPE_VERIFIABLE: 95,
    CLAIM_TYPE_ANONYMOUS:  60,
    CLAIM_TYPE_INFERENCE:  55,
}

CLAIM_TYPE_EXPLANATION: dict[str, str] = {
    CLAIM_TYPE_VERIFIABLE: (
        "This is a verifiable factual claim. Confidence is based on available "
        "public sources and may be updated by real-time search results."
    ),
    CLAIM_TYPE_ANONYMOUS: (
        "This claim originates from an unnamed or anonymous source. AI cannot "
        "cross-reference anonymous insider claims against public records. "
        "A confidence score above 60% is structurally impossible regardless of "
        "how many sources are found — treat this as unverified unless corroborated "
        "by a named, accountable source."
    ),
    CLAIM_TYPE_INFERENCE: (
        "This is a subjective interpretation or inference rather than a concrete "
        "factual claim. Confidence reflects how widely the interpretation is shared, "
        "not verifiable truth."
    ),
}


# ---------------------------------------------------------------------------
# Agent 2 — Claim Extractor prompt
# ---------------------------------------------------------------------------

_CLAIM_EXTRACTOR_PROMPT = """
You are Agent 2 (Claim Extractor) in a multi-agent fact-checking system.

Today's date: {today}

YOUR ONLY JOB is to identify and classify factual claims in the text.
Do NOT invent sources or URLs.

Classify every claim as ONE of:
  - "verifiable"          — a concrete, publicly checkable fact (date, statistic, named event)
  - "anonymous_source"    — originates from an unnamed/insider/unnamed-insider source
  - "subjective_inference"— an opinion, characterisation, or interpretation framed as fact

Return ONLY valid JSON — no markdown fences, no prose before or after.

{{
  "claims": [
    {{
      "claimIndex": 0,
      "claim": "Short label for the claim",
      "claimText": "Exact verbatim text from the source",
      "claimType": "verifiable | anonymous_source | subjective_inference",
      "initialConfidence": <integer 0-100>,
      "confidenceReason": "Why this confidence, and what limits it",
      "searchQuery": "Best web search query to verify this claim"
    }}
  ]
}}

Rules:
- Only extract claims with meaningful factual content (skip filler, opinions clearly marked as such).
- For recent events (< 2 years old) use initialConfidence 40-60 — search results will refine it.
- For anonymous_source claims, cap initialConfidence at 60.
- For subjective_inference claims, cap initialConfidence at 55.
- claimIndex must start at 0 and be sequential.
"""

_HTML_MARKER_PROMPT = """
You are a text formatter. You will receive:
1. The original text
2. A list of claims with their claimIndex and claimText

Return ONLY valid JSON — no markdown fences.

{{
  "htmlContent": "<p>Text with <span class=\\"marker\\">claim text [1]</span> inline markers...</p>",
  "overallConfidence": <integer 0-100>,
  "overallReasoning": "2-3 sentence summary of the text's factual reliability"
}}

Rules:
- Wrap ONLY the exact claimText in <span class="marker">...</span> and append [N] where N = claimIndex + 1.
- Do not add markers where there is no claim.
- overallConfidence is your assessment of the whole text's factual reliability (0-100).
"""


# ---------------------------------------------------------------------------
# Agent 3 — Search Agent
# ---------------------------------------------------------------------------

def _search_for_claims(claims: list[dict]) -> list[dict]:
    """
    Agent 3: For each claim, search for real sources.
    Returns an enriched list with a 'sources' key added to each claim.
    """
    enriched = []
    top_domains = TRUSTED_FACT_CHECK_DOMAINS[:10]

    for claim_data in claims:
        query = claim_data.get("searchQuery") or claim_data.get("claim", "")
        results = search_for_claim(query, max_results=3, include_domains=top_domains)

        sources = []
        for r in results:
            score = r.get("score", 0)
            if score > 0.8:
                stance = "Mostly Support"
            elif score > 0.5:
                stance = "Partially Support"
            elif score > 0.2:
                stance = "Weakly Support"
            else:
                stance = "Insufficient Evidence"

            sources.append({
                "title":          r.get("title", "Unknown Source"),
                "url":            r.get("url", ""),
                "snippet":        r.get("snippet", ""),
                "datePosted":     r.get("published_date", ""),
                "ratingStance":   stance,
                "claimReference": claim_data.get("claimText", ""),
            })

        if not sources:
            sources.append({
                "title":          "No verified sources found",
                "url":            "",
                "snippet":        (
                    "Unable to find verified public sources. "
                    "Verify this claim independently before treating it as fact."
                ),
                "datePosted":     "",
                "ratingStance":   "Insufficient Evidence",
                "claimReference": claim_data.get("claimText", ""),
            })

        enriched.append({**claim_data, "sources": sources})

    return enriched


# ---------------------------------------------------------------------------
# Agent 4 — Verifier + Explainer
# ---------------------------------------------------------------------------

def _apply_trust_layer(claims_with_sources: list[dict]) -> list[dict]:
    """
    Agent 4: Cap confidence scores by claim type, attach structured AI-limitation
    explanations, and produce the final sourcesList entries consumed by the UI.
    """
    sources_list = []

    for c in claims_with_sources:
        claim_type     = c.get("claimType", CLAIM_TYPE_VERIFIABLE)
        raw_confidence = c.get("initialConfidence", 50)
        ceiling        = CONFIDENCE_CEILING.get(claim_type, 95)

        # Hard cap: anonymous/inference claims cannot exceed their ceiling
        final_confidence = min(raw_confidence, ceiling)

        # Build the human-readable confidence reason, always including the
        # structural ceiling explanation for non-verifiable claim types
        base_reason = c.get("confidenceReason", "")
        type_explanation = CLAIM_TYPE_EXPLANATION.get(claim_type, "")

        if claim_type != CLAIM_TYPE_VERIFIABLE:
            confidence_reason = f"{base_reason}\n\n⚠ AI limitation: {type_explanation}"
        else:
            confidence_reason = base_reason

        sources_list.append({
            "claim":            c.get("claim", ""),
            "claimType":        claim_type,
            "confidenceReason": confidence_reason,
            "ratingPercent":    final_confidence,
            "confidenceCeiling": ceiling,
            "aiLimitation":     type_explanation,
            "sources":          c.get("sources", []),
        })

    return sources_list


# ---------------------------------------------------------------------------
# Agent 1 — Orchestrator (text)
# ---------------------------------------------------------------------------

def run_text_analysis_with_openai(text: str) -> dict:
    """
    Orchestrates the 4-agent pipeline for plain text input.

    Returns a plain dict (always JSON-serialisable):
    {
        "confidenceScores": int,
        "reasoning":        str,
        "htmlContent":      str,
        "sourcesList": [
            {
                "claim":             str,
                "claimType":         "verifiable|anonymous_source|subjective_inference",
                "confidenceReason":  str,
                "ratingPercent":     int,   # already capped by claim type
                "confidenceCeiling": int,
                "aiLimitation":      str,
                "sources": [
                    {
                        "title":          str,
                        "url":            str,
                        "snippet":        str,
                        "datePosted":     str,
                        "ratingStance":   str,
                        "claimReference": str,
                    }
                ]
            }
        ]
    }
    """
    today = _today()

    # ── Agent 2a: extract and classify claims ────────────────────────────────
    extractor_raw = run_text_analysis(
        system_prompt=_CLAIM_EXTRACTOR_PROMPT.format(today=today),
        user_payload={"text": text},
        model="gpt-4.1",
        temperature=0.1,
    )
    extractor_data = _safe_json(extractor_raw, {"claims": []})
    claims: list[dict] = extractor_data.get("claims", [])

    # ── Agent 2b: generate annotated HTML + overall score ────────────────────
    marker_raw = run_text_analysis(
        system_prompt=_HTML_MARKER_PROMPT,
        user_payload={
            "originalText": text,
            "claims": [
                {"claimIndex": c["claimIndex"], "claimText": c.get("claimText", "")}
                for c in claims
            ],
        },
        model="gpt-4.1",
        temperature=0.0,
    )
    marker_data = _safe_json(marker_raw, {
        "htmlContent":       text,
        "overallConfidence": 0,
        "overallReasoning":  "Could not generate annotated text.",
    })

    # ── Agent 3: search for sources (parallel in spirit; sequential here) ────
    claims_with_sources = _search_for_claims(claims)

    # ── Agent 4: apply trust layer + confidence ceilings ─────────────────────
    sources_list = _apply_trust_layer(claims_with_sources)

    return {
        "confidenceScores": marker_data.get("overallConfidence", 0),
        "reasoning":        marker_data.get("overallReasoning", ""),
        "htmlContent":      marker_data.get("htmlContent", text),
        "sourcesList":      sources_list,
    }


# ---------------------------------------------------------------------------
# Agent 1 — Orchestrator (video transcript)
# ---------------------------------------------------------------------------

_VIDEO_CLAIM_EXTRACTOR_PROMPT = """
You are Agent 2 (Claim Extractor) specialised in video transcript analysis.

Today's date: {today}

You receive a list of transcript segments. Your job:
1. Return ALL segments unchanged — most have no claims.
2. For segments containing a factual claim, add "claim", "claimType", and "claimIndex".
3. Separately list each unique claim in the "claims" array.

Classify every claim as ONE of:
  - "verifiable"           — publicly checkable fact
  - "anonymous_source"     — unnamed/insider source
  - "subjective_inference" — opinion presented as fact

Return ONLY valid JSON — no markdown fences, no prose.

{{
  "videoId": "{video_id}",
  "overallConfidence": <integer 0-100>,
  "overallReasoning": "brief summary",
  "segments": [
    {{
      "id": "...",
      "text": "...",
      "startTime": 0,
      "endTime": 5
    }},
    {{
      "id": "...",
      "text": "...",
      "startTime": 5,
      "endTime": 10,
      "claim": "short label",
      "claimType": "verifiable",
      "claimIndex": 0
    }}
  ],
  "claims": [
    {{
      "claimIndex": 0,
      "claim": "short label",
      "claimText": "exact verbatim text",
      "claimType": "verifiable | anonymous_source | subjective_inference",
      "initialConfidence": 55,
      "confidenceReason": "explanation",
      "searchQuery": "search query"
    }}
  ]
}}

Rules:
- Return EVERY segment from input, in order, even those without claims.
- Cap initialConfidence at 60 for anonymous_source, 55 for subjective_inference.
- For recent events use initialConfidence 40-60.
"""

MAX_TRANSCRIPT_SECONDS = 180  # analyse only first 3 min to control cost


def run_video_transcript_analysis_with_openai(
    video_id: str,
    segments: list[TranscriptSegment],
) -> dict:
    """
    Orchestrates the 4-agent pipeline for video transcript input.

    Returns a plain dict (always JSON-serialisable):
    {
        "videoId":          str,
        "confidenceScores": int,
        "reasoning":        str,
        "segments":         list[dict],   # all segments, some annotated with claim info
        "sourcesList":      list[dict],   # same shape as text analysis
    }
    """
    today = _today()

    all_segments_data = [
        {"id": s.id, "text": s.text, "startTime": s.startTime, "endTime": s.endTime}
        for s in segments
    ]

    to_analyse   = [s for s in all_segments_data if s["startTime"] < MAX_TRANSCRIPT_SECONDS]
    after_cutoff = [s for s in all_segments_data if s["startTime"] >= MAX_TRANSCRIPT_SECONDS]

    # ── Agent 2: extract claims from first 3 min ─────────────────────────────
    extractor_raw = run_text_analysis(
        system_prompt=_VIDEO_CLAIM_EXTRACTOR_PROMPT.format(today=today, video_id=video_id),
        user_payload={"videoId": video_id, "segments": to_analyse},
        model="gpt-4.1",
        temperature=0.1,
    )
    data = _safe_json(extractor_raw, {
        "videoId":          video_id,
        "overallConfidence": 0,
        "overallReasoning": "Model returned invalid JSON.",
        "segments":         to_analyse,
        "claims":           [],
    })

    # Merge analysed segments with the remainder of the video
    analysed_segments  = data.get("segments", to_analyse)
    full_segments      = analysed_segments + after_cutoff
    claims: list[dict] = data.get("claims", [])

    # ── Agent 3: search ───────────────────────────────────────────────────────
    claims_with_sources = _search_for_claims(claims)

    # ── Agent 4: apply trust layer ────────────────────────────────────────────
    sources_list = _apply_trust_layer(claims_with_sources)

    return {
        "videoId":          video_id,
        "confidenceScores": data.get("overallConfidence", 0),
        "reasoning":        data.get("overallReasoning", ""),
        "segments":         full_segments,
        "sourcesList":      sources_list,
    }