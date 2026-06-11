"""
Two thin HTTP wrappers over the OCI Real Estate Intel REST API.

The upstream agent does intent routing, retrieval, and synthesis internally
— so the MCP surface stays small: one query tool that takes natural language
and returns a grounded answer + citations + trace id, and one feedback tool
that lets the calling agent attach a thumbs-up/down score to a trace.

All responses are normalized through Pydantic models so the calling LLM sees
a stable shape even if the upstream adds fields. Errors carry an `ok=False`
flag with `error_kind` + `error` so the caller can branch without parsing
free-text.
"""

from __future__ import annotations

import logging

import httpx
from pydantic import BaseModel, Field

from server.config import settings

log = logging.getLogger(__name__)


class Citation(BaseModel):
    """One APN cited by the agent's answer."""

    apn: str
    address: str | None = None


class QueryResult(BaseModel):
    """Stable response shape for query_parcels.

    On success: ok=True with answer/intent/citations/trace_id populated.
    On failure: ok=False with error_kind + error so the caller can decide
    whether to retry, switch tools, or surface the error.
    """

    ok: bool = True
    answer: str = ""
    intent: str = ""
    citations: list[Citation] = Field(default_factory=list)
    trace_id: str | None = None
    error_kind: str | None = None  # "config" | "network" | "http" | None on success
    error: str | None = None


class FeedbackResult(BaseModel):
    ok: bool = True
    trace_id: str = ""
    score: float = 0.0
    error_kind: str | None = None
    error: str | None = None


def _headers() -> dict[str, str]:
    """Build outbound headers, including the optional bearer token."""
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if settings.oci_api_key:
        headers["Authorization"] = f"Bearer {settings.oci_api_key}"
    return headers


def _config_error(field: str) -> QueryResult:
    """Convert a missing-config error to a structured response the calling
    LLM can act on (typically by telling the user how to fix the .env)."""
    return QueryResult(
        ok=False,
        error_kind="config",
        error=(
            f"{field} is empty. Set it in oci-mcp's .env "
            "(see .env.example) and restart the MCP server."
        ),
    )


async def query_parcels(
    query: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> QueryResult:
    """POST natural-language query to the OCI agent.

    The upstream's LangGraph supervisor handles intent routing (lookup,
    summarize, compare, title_chain, portfolio) — the MCP caller doesn't
    need to specify the route. Returns the agent's answer + the APNs it
    actually cited (citations are extracted from the answer text, not
    everything retrieved) + a Langfuse trace_id for follow-up scoring.
    """
    if not settings.oci_api_url:
        return _config_error("OCI_API_URL")
    if not query or not query.strip():
        return QueryResult(
            ok=False, error_kind="config",
            error="query is empty — pass a natural-language question",
        )

    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=settings.oci_timeout_s)
    try:
        try:
            r = await client.post(
                f"{settings.base}/api/v1/query",
                json={"query": query},
                headers=_headers(),
            )
        except httpx.RequestError as e:
            return QueryResult(
                ok=False, error_kind="network",
                error=f"network error talking to {settings.base}: {e}",
            )
        if r.status_code >= 400:
            return QueryResult(
                ok=False, error_kind="http",
                error=f"{r.status_code} from /api/v1/query: {r.text[:300]}",
            )
        try:
            data = r.json()
        except ValueError as e:
            return QueryResult(
                ok=False, error_kind="http",
                error=f"non-JSON response from agent: {e}",
            )

        citations = [
            Citation(**c) for c in (data.get("citations") or [])
            if isinstance(c, dict) and c.get("apn")
        ]
        return QueryResult(
            ok=True,
            answer=str(data.get("answer") or ""),
            intent=str(data.get("intent") or ""),
            citations=citations,
            trace_id=data.get("trace_id"),
        )
    finally:
        if own_client:
            await client.aclose()


async def submit_feedback(
    trace_id: str,
    score: float,
    comment: str | None = None,
    *,
    client: httpx.AsyncClient | None = None,
) -> FeedbackResult:
    """Attach a thumbs-up (+1) or thumbs-down (-1) score to a trace.

    The upstream wires this through to Langfuse as a `user_feedback` score.
    Lets the calling LLM (or a downstream eval pipeline) signal answer
    quality back to the agent that produced it — exactly the multi-agent
    handoff loop MCP is supposed to unlock.
    """
    if not settings.oci_api_url:
        return FeedbackResult(
            ok=False, trace_id=trace_id,
            error_kind="config",
            error="OCI_API_URL is empty — set it in oci-mcp's .env",
        )
    if not trace_id:
        return FeedbackResult(
            ok=False, trace_id="",
            error_kind="config",
            error="trace_id is empty",
        )
    if score not in (-1.0, 1.0):
        return FeedbackResult(
            ok=False, trace_id=trace_id, score=score,
            error_kind="config",
            error="score must be +1.0 (thumbs up) or -1.0 (thumbs down)",
        )

    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=settings.oci_timeout_s)
    try:
        try:
            r = await client.post(
                f"{settings.base}/api/v1/feedback",
                json={"trace_id": trace_id, "score": score, "comment": comment},
                headers=_headers(),
            )
        except httpx.RequestError as e:
            return FeedbackResult(
                ok=False, trace_id=trace_id, score=score,
                error_kind="network",
                error=f"network error: {e}",
            )
        if r.status_code >= 400:
            return FeedbackResult(
                ok=False, trace_id=trace_id, score=score,
                error_kind="http",
                error=f"{r.status_code} from /api/v1/feedback: {r.text[:300]}",
            )
        return FeedbackResult(ok=True, trace_id=trace_id, score=score)
    finally:
        if own_client:
            await client.aclose()
