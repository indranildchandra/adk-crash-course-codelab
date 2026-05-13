"""
DuckDuckGo Search Tool for ADK agents.

A plain Python function that ADK exposes as a callable tool.
No API key required — free web search via DuckDuckGo.

This demonstrates how any Python package can be plugged into an ADK agent
as a custom tool with zero boilerplate beyond a typed function + docstring.
"""

from ddgs import DDGS


def ddg_search(query: str) -> str:
    """Search the web using DuckDuckGo and return a formatted summary of results.

    Use this tool whenever you need current information, specific facts,
    venue details, event listings, opening hours, or anything that benefits
    from a live web search.

    Args:
        query: The search query string (e.g. "best sushi in Sunnyvale CA").

    Returns:
        Formatted string with title, URL, and snippet for each result.
        Returns an error message if the search fails.
    """
    try:
        results = DDGS().text(query, max_results=10)
        if not results:
            return f"No results found for: {query}"

        lines = [f"Search results for: {query}\n"]
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. {r.get('title', 'No title')}")
            lines.append(f"   URL: {r.get('href', '')}")
            lines.append(f"   {r.get('body', '')[:300]}")
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        return f"Search failed: {e}"
