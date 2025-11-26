import json
from typing import Dict, Any

from schemas.text_analysis import TextAnalysisResponse
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
