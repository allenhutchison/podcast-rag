"""
Synthesizer Agent for combining podcast and web search results.

This module provides an ADK agent that synthesizes results from
multiple search sources with equal weighting.
"""

import logging

from google.adk.agents import LlmAgent

logger = logging.getLogger(__name__)


def create_synthesizer_agent(model: str) -> LlmAgent:
    """
    Create the SynthesizerAgent for combining search results.

    This agent receives results from both PodcastSearchAgent and
    WebSearchAgent and creates a unified response with equal weighting.

    Args:
        model: Gemini model to use

    Returns:
        Configured LlmAgent for synthesis
    """
    return LlmAgent(
        name="SynthesizerAgent",
        model=model,
        instruction="""You are a research synthesis specialist.

You will receive information from two sources:
1. **Podcast Results** (in {podcast_results}): Findings from podcast transcript search
2. **Web Results** (in {web_results}): Findings from web search

Your task is to create a UNIFIED, COHERENT response that treats both sources with EQUAL WEIGHT.

## Synthesis Rules:
1. Weigh both sources equally based on relevance to the original query
2. If sources agree, present the consensus view
3. If sources disagree or provide different perspectives, note both viewpoints
4. Use the most relevant and accurate information from each source

## Response Structure:
Create a well-organized response that:
1. Answers the user's question directly
2. Weaves together information from both sources naturally
3. Notes any important agreements or conflicts between sources
4. When referencing information, mention whether it comes from "podcast episodes" or "web sources" naturally in the text

## Output Format:
Format your response using HTML tags (NOT markdown):
- Use <p> for paragraphs
- Use <strong> for bold/emphasis
- Use <em> for italics
- Use <ul>/<ol> and <li> for lists
- Use <h3> for section headings if needed
- Do NOT use markdown syntax like **, ##, -, or *
- Do NOT include citation brackets like [P1] or [W1] - sources will be shown separately

## Handling Missing Data:
- If {podcast_results} is empty/errored: Use web results only, note limitation
- If {web_results} is empty/errored: Use podcast results only, note limitation
- If both are empty: Explain that no relevant information was found

Be comprehensive yet concise. Prioritize accuracy and clarity.""",
        description="Synthesizes podcast and web search results into unified response",
        output_key="final_response"
    )
