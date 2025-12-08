# services/search_service.py
"""
Search service for finding real, verified sources for fact-checking claims.
Uses Tavily API which is designed for AI/LLM search and provides reliable sources.
"""
import logging
from typing import List, Optional, Dict, Any
from tavily import TavilyClient
import httpx

from config import settings

logger = logging.getLogger(__name__)


def get_tavily_client() -> Optional[TavilyClient]:
    """Get Tavily client if API key is configured."""
    if not settings.TAVILY_API_KEY or settings.TAVILY_API_KEY == "your-tavily-api-key-here":
        logger.warning("Tavily API key not configured - search features disabled")
        return None
    return TavilyClient(api_key=settings.TAVILY_API_KEY)


def search_for_claim(
    claim: str,
    max_results: int = 3,
    include_domains: Optional[List[str]] = None,
    search_depth: str = "basic"
) -> List[Dict[str, Any]]:
    """
    Search for sources related to a specific claim using Tavily.
    
    Args:
        claim: The factual claim to search for
        max_results: Maximum number of results to return (default 3)
        include_domains: Optional list of trusted domains to prioritize
        search_depth: "basic" or "advanced" - advanced gets more detailed results
        
    Returns:
        List of source dictionaries with url, title, content, score, published_date
    """
    client = get_tavily_client()
    if not client:
        return []
    
    try:
        # Craft a fact-checking focused query
        search_query = f"fact check: {claim}"
        
        search_params = {
            "query": search_query,
            "max_results": max_results,
            "search_depth": search_depth,
            "include_answer": False,
        }
        
        if include_domains:
            search_params["include_domains"] = include_domains
            
        response = client.search(**search_params)
        
        results = []
        for result in response.get("results", []):
            results.append({
                "url": result.get("url", ""),
                "title": result.get("title", ""),
                "snippet": result.get("content", "")[:500],  # Limit snippet length
                "score": result.get("score", 0),
                "published_date": result.get("published_date", ""),
            })
            
        logger.info(f"Found {len(results)} sources for claim: {claim[:50]}...")
        return results
        
    except Exception as e:
        logger.error(f"Error searching for claim: {e}")
        return []


def search_for_claims_batch(
    claims: List[str],
    max_results_per_claim: int = 2
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Search for sources for multiple claims.
    
    Args:
        claims: List of claims to search for
        max_results_per_claim: Max results per claim
        
    Returns:
        Dictionary mapping each claim to its found sources
    """
    results = {}
    for claim in claims:
        results[claim] = search_for_claim(
            claim,
            max_results=max_results_per_claim
        )
    return results


async def verify_url_exists(url: str, timeout: float = 5.0) -> bool:
    """
    Verify that a URL actually exists by making a HEAD request.
    
    Args:
        url: URL to verify
        timeout: Request timeout in seconds
        
    Returns:
        True if URL exists and returns 2xx/3xx status
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.head(
                url,
                timeout=timeout,
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (compatible; UmActually/1.0)"}
            )
            return 200 <= response.status_code < 400
    except Exception as e:
        logger.debug(f"URL verification failed for {url}: {e}")
        return False


def verify_url_exists_sync(url: str, timeout: float = 5.0) -> bool:
    """
    Synchronous version of URL verification.
    """
    try:
        with httpx.Client() as client:
            response = client.head(
                url,
                timeout=timeout,
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (compatible; UmActually/1.0)"}
            )
            return 200 <= response.status_code < 400
    except Exception as e:
        logger.debug(f"URL verification failed for {url}: {e}")
        return False


# Trusted news/fact-checking domains for prioritization
TRUSTED_FACT_CHECK_DOMAINS = [
    "reuters.com",
    "apnews.com",
    "factcheck.org",
    "snopes.com",
    "politifact.com",
    "bbc.com",
    "bbc.co.uk",
    "nytimes.com",
    "washingtonpost.com",
    "npr.org",
    "pbs.org",
    "theguardian.com",
    "nature.com",
    "sciencedirect.com",
    "pubmed.ncbi.nlm.nih.gov",
    "scholar.google.com",
]

