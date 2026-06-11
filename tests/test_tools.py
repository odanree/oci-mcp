"""Tests for the OCI MCP tools — respx-mocked HTTP, no network."""

from __future__ import annotations

import httpx
import pytest
import respx

import server.config as cfg
from server.tools import (
    Citation,
    FeedbackResult,
    QueryResult,
    query_parcels,
    submit_feedback,
)


@pytest.fixture(autouse=True)
def _set_oci_url(monkeypatch):
    """Tests run against a placeholder URL — never touches the real deployment."""
    monkeypatch.setattr(cfg.settings, "oci_api_url", "https://oci.test")
    monkeypatch.setattr(cfg.settings, "oci_api_key", "")
    monkeypatch.setattr(cfg.settings, "oci_timeout_s", 5.0)


# ---------------------------------------------------------------------------
# query_parcels
# ---------------------------------------------------------------------------


@respx.mock
@pytest.mark.asyncio
async def test_query_parcels_returns_normalized_response():
    respx.post("https://oci.test/api/v1/query").mock(
        return_value=httpx.Response(200, json={
            "answer": "FLORES FAMILY TRUST owns 461-211-62 at 73 Bridgeport Rd, Irvine.",
            "intent": "lookup",
            "citations": [
                {"apn": "461-211-62", "address": "73 BRIDGEPORT RD IRVINE"},
            ],
            "trace_id": "trc_abc123",
        }),
    )
    result = await query_parcels("Who owns 461-211-62?")
    assert isinstance(result, QueryResult)
    assert result.ok is True
    assert result.intent == "lookup"
    assert len(result.citations) == 1
    assert result.citations[0].apn == "461-211-62"
    assert result.trace_id == "trc_abc123"
    assert result.error_kind is None


@respx.mock
@pytest.mark.asyncio
async def test_query_parcels_passes_bearer_when_key_set(monkeypatch):
    monkeypatch.setattr(cfg.settings, "oci_api_key", "test-secret-key")
    route = respx.post("https://oci.test/api/v1/query").mock(
        return_value=httpx.Response(200, json={
            "answer": "ok", "intent": "lookup", "citations": [], "trace_id": None,
        }),
    )
    await query_parcels("anything")
    auth = route.calls[0].request.headers.get("Authorization")
    assert auth == "Bearer test-secret-key"


@pytest.mark.asyncio
async def test_query_parcels_requires_api_url(monkeypatch):
    monkeypatch.setattr(cfg.settings, "oci_api_url", "")
    result = await query_parcels("anything")
    assert result.ok is False
    assert result.error_kind == "config"
    assert "OCI_API_URL" in (result.error or "")


@pytest.mark.asyncio
async def test_query_parcels_rejects_empty_query():
    result = await query_parcels("   ")
    assert result.ok is False
    assert result.error_kind == "config"
    assert "query is empty" in (result.error or "")


@respx.mock
@pytest.mark.asyncio
async def test_query_parcels_maps_5xx_to_http_error():
    respx.post("https://oci.test/api/v1/query").mock(
        return_value=httpx.Response(502, text="upstream agent down"),
    )
    result = await query_parcels("any")
    assert result.ok is False
    assert result.error_kind == "http"
    assert "502" in (result.error or "")


@respx.mock
@pytest.mark.asyncio
async def test_query_parcels_drops_malformed_citation_rows():
    """Upstream sometimes returns citations missing apn. Drop those, keep the rest."""
    respx.post("https://oci.test/api/v1/query").mock(
        return_value=httpx.Response(200, json={
            "answer": "x", "intent": "lookup",
            "citations": [
                {"apn": "461-211-62"},
                {"address": "no apn here"},
                {"apn": "", "address": "empty apn"},
                {"apn": "390-284-13", "address": "470 S Alpine"},
            ],
            "trace_id": None,
        }),
    )
    result = await query_parcels("anything")
    apns = [c.apn for c in result.citations]
    assert apns == ["461-211-62", "390-284-13"]


@respx.mock
@pytest.mark.asyncio
async def test_query_parcels_handles_non_json_body():
    respx.post("https://oci.test/api/v1/query").mock(
        return_value=httpx.Response(200, text="<html>nope</html>"),
    )
    result = await query_parcels("any")
    assert result.ok is False
    assert result.error_kind == "http"
    assert "non-JSON" in (result.error or "")


# ---------------------------------------------------------------------------
# submit_feedback
# ---------------------------------------------------------------------------


@respx.mock
@pytest.mark.asyncio
async def test_submit_feedback_posts_score():
    route = respx.post("https://oci.test/api/v1/feedback").mock(
        return_value=httpx.Response(200, json={"ok": True}),
    )
    result = await submit_feedback("trc_x", 1.0, comment="good")
    assert isinstance(result, FeedbackResult)
    assert result.ok is True
    body = route.calls[0].request.content.decode()
    assert "trc_x" in body
    assert "good" in body


@pytest.mark.asyncio
async def test_submit_feedback_rejects_invalid_score():
    result = await submit_feedback("trc_x", 0.5)
    assert result.ok is False
    assert result.error_kind == "config"
    assert "+1.0" in (result.error or "")


@pytest.mark.asyncio
async def test_submit_feedback_rejects_empty_trace_id():
    result = await submit_feedback("", 1.0)
    assert result.ok is False
    assert result.error_kind == "config"
    assert "trace_id" in (result.error or "")


@respx.mock
@pytest.mark.asyncio
async def test_submit_feedback_maps_400_to_http_error():
    respx.post("https://oci.test/api/v1/feedback").mock(
        return_value=httpx.Response(400, text="bad trace"),
    )
    result = await submit_feedback("trc_x", -1.0)
    assert result.ok is False
    assert result.error_kind == "http"
