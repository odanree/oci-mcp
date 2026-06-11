# oci-mcp

**MCP server that exposes the [OC Real Estate Intel agent](https://github.com/odanree/oc-realestate-intel) as a tool** to Claude Desktop, Claude Code, and any other MCP client. Lets you ask natural-language questions about Orange County parcels — addresses, APNs, owners, title chains, LLC portfolios — and get back grounded answers with APN citations and a Langfuse trace ID.

`MCP` · `FastMCP` · `Claude Desktop` · `Claude Code` · `Anthropic` · `LangGraph (upstream)` · `Pydantic v2` · `httpx` · `respx` · `pytest-asyncio`

| Tool | What it does |
|---|---|
| `oc_parcel_query` | Natural-language query → answer + intent + citations + trace_id. The upstream agent does intent routing internally (lookup / summarize / compare / title_chain / portfolio); the MCP caller doesn't pick a mode. |
| `oc_submit_feedback` | Attach +1 (thumbs-up) or -1 (thumbs-down) to a trace. Lands in Langfuse as a `user_feedback` score on the trace, so the agent's operator can filter "show me every query users marked bad." |

The upstream agent is documented at [oc-realestate-intel](https://github.com/odanree/oc-realestate-intel) and runs live at [oci.danhle.net](https://oci.danhle.net).

---

## Use it from Claude Code

```bash
git clone https://github.com/odanree/oci-mcp
cd oci-mcp
python -m venv .venv && .venv/Scripts/activate
pip install -e ".[dev]"
cp .env.example .env
# Edit .env: set OCI_API_URL=https://your-deployment-url
```

Register the server (user scope = available in every Claude Code project):

```powershell
claude mcp add oci -s user -- "C:\Users\Danh\Documents\Projects\oci-mcp\.venv\Scripts\python.exe" -m server.main
```

Verify:

```powershell
claude mcp list
```

You should see `oci: ... - ✓ Connected`. Restart Claude Code, then in any chat:

> "oci: who owns 461-211-62?"
>
> "oci: what does FLORES FAMILY TR own?"
>
> "oci: trace the title chain on 73 Bridgeport Rd Irvine"

Claude calls `oc_parcel_query`, the agent runs end-to-end (router → retrieval → summarize), and you see the answer cited by APN.

## Use it from Claude Desktop

Same config, different file. Drop this into `%APPDATA%\Claude\claude_desktop_config.json` (Windows) or `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "oci": {
      "command": "C:\\Users\\Danh\\Documents\\Projects\\oci-mcp\\.venv\\Scripts\\python.exe",
      "args": ["-m", "server.main"],
      "env": {
        "OCI_API_URL": "https://your-deployment-url"
      }
    }
  }
}
```

Quit Claude Desktop fully, reopen, and the 🔧 icon should list the two tools.

---

## Why this exists

Three reasons one of my MCP servers wraps my own agent system:

1. **It turns a destination into a capability.** Without this server, oc-realestate-intel is "a thing users go to." With it, the agent becomes a tool other agents can call. Different architecture, different composability.

2. **It closes a real loop.** I built an agent → deployed it to my infra → wrote an MCP that exposes it → other agents (or me, in Claude Code) call it. Every layer is mine, every layer is public, every layer is traced.

3. **It's exactly what interviewers ask about.** "How do you compose agentic systems?" gets a concrete answer: this server. Plus the upstream-vs-MCP separation maps directly to the read-vs-write split that infra-mcp uses, so the design story is consistent across the portfolio.

---

## Tests

```bash
pytest
# 11 tests covering success path, all four error_kind cases (config / network /
# http / validation), citation normalization, bearer-token wiring, and feedback
# score validation. All HTTP mocked with respx — no network.
```

---

## Project layout

```
server/
  main.py        FastMCP entrypoint, registers oc_parcel_query + oc_submit_feedback
  config.py      pydantic-settings, .env loaded via absolute path
  tools.py       Both API wrappers + Pydantic response models
tests/
  test_tools.py  respx-mocked tests for both tools
```

---

## License

MIT
