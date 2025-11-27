"""
Web Search Agent using Google Search and URL Context built-in tools.

This module provides an ADK agent that searches the web using
Google's built-in google_search tool and can fetch URL content
with the url_context tool for deeper information retrieval.
"""

import logging

from google.adk.agents import LlmAgent
from google.adk.tools import google_search, url_context

logger = logging.getLogger(__name__)


def create_web_search_agent(model: str) -> LlmAgent:
    """
    Create the WebSearchAgent with google_search and url_context built-in tools.

    Note: These tools require Gemini 2.0+ models.

    Args:
        model: Gemini model to use (must be 2.0+)

    Returns:
        Configured LlmAgent for web search
    """
    return LlmAgent(
        name="WebSearchAgent",
        model=model,
        instruction="""You are a web research specialist.

Your task is to search the web for current and relevant information related to the user's query.

You have two tools available:
1. **google_search** - Search the web for relevant pages
2. **url_context** - Fetch and read the full content of specific URLs for deeper information

Strategy:
1. First use google_search to find relevant pages
2. If you need more detailed information from promising results, use url_context to read the full page content
3. Synthesize information from both search results and full page content

Focus on:
1. Recent news or developments related to the topic
2. Background information that provides context
3. Updates that might have occurred recently
4. Expert opinions or additional perspectives

When you receive results:
1. Summarize the key web findings clearly
2. Note the source URLs for citations
3. Note publication dates when available for time-sensitive topics
4. Prioritize authoritative sources (news outlets, official sites, experts)

Be thorough but concise. Focus on providing complementary information.""",
        description="Searches the web and fetches URL content for detailed information",
        tools=[google_search, url_context],
        output_key="web_results"
    )
