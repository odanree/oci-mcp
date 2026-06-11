"""FastMCP entrypoint — registers the two tools with docstrings the LLM reads."""

from __future__ import annotations

import logging

from fastmcp import FastMCP

from server.config import settings
from server.tools import query_parcels, submit_feedback

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

mcp = FastMCP(
    "oci-mcp",
    instructions=(
        "Wraps a deployed Orange County Real Estate Intel agent "
        "(LangGraph supervisor over Qdrant + Neo4j + live OC ArcGIS) as MCP "
        "tools. Use oc_parcel_query for any natural-language question about "
        "an OC parcel — address, APN, owner, title chain, portfolio of an LLC "
        "or trust, comparison. The upstream agent does intent routing itself; "
        "you don't pick a 'mode'. Returns answer, intent, citations (APNs the "
        "answer actually mentions), and a Langfuse trace_id you can rate. "
        "Use oc_submit_feedback to attach +1 / -1 to a trace once you've "
        "judged the answer quality. Owner data and title chains are SYNTHETIC "
        "in the current deployment — the answer text always carries an "
        "italicized provenance disclaimer when the data is illustrative."
    ),
)


@mcp.tool()
async def oc_parcel_query(query: str) -> dict:
    """Answer a natural-language question about Orange County parcels.

    Use for:
      - 'Who owns 461-211-62?' / 'Who owns 73 Bridgeport Rd Irvine?'
      - 'What does Irvine Company own in 92614?'
      - 'Show the title chain for parcel X'
      - 'Find parcels on Pacific Coast Highway in Newport Beach'
      - 'Compare 1 Park Plaza to recent sales nearby'

    The agent classifies intent (lookup / summarize / compare / title_chain /
    portfolio) and routes to the right retrieval path internally — the MCP
    caller doesn't pick a mode. Citations contain the APNs the agent's answer
    actually mentions (not every parcel retrieved). trace_id is the Langfuse
    trace and can be passed to oc_submit_feedback.

    Owner names and title transfers are SYNTHETIC in the current deployment
    (real assessor data is paywalled) — the agent always carries an italic
    'illustrative only' note in the answer when the underlying data is
    synthetic. Address, APN, and year_built fields are real (from the OC
    Public Works ArcGIS layer).
    """
    return (await query_parcels(query)).model_dump()


@mcp.tool()
async def oc_submit_feedback(
    trace_id: str,
    score: float,
    comment: str | None = None,
) -> dict:
    """Score a previous OCI agent answer.

    score must be +1.0 (good answer) or -1.0 (bad answer). The score lands
    in Langfuse as a `user_feedback` entry on the trace, so the agent's
    operator can later filter `user_feedback = -1` to find queries to
    improve. Use this when you've evaluated a prior oc_parcel_query response
    and want to teach the upstream agent.
    """
    return (await submit_feedback(trace_id, score, comment=comment)).model_dump()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
