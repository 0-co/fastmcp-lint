# fastmcp-lint

Static analysis for [FastMCP](https://github.com/prefecthq/fastmcp) servers. Catches schema quality issues before they ship.

No server execution needed — pure Python AST analysis.

## Why

FastMCP generates MCP tool descriptions from Python docstrings. If the docstring is missing, agents see an empty description and can't use the tool reliably.

We graded 207 MCP servers. **4/4 FastMCP-built servers grade F** — not because FastMCP is bad, but because empty docstrings produce empty descriptions. Same database, different documentation hygiene: community DuckDB (raw SDK, full docstrings) A 96/100. MotherDuck (FastMCP, no docstrings) F 50/100.

## Install

```bash
pip install fastmcp-lint
```

## Usage

```bash
fastmcp-lint server.py
```

```
server.py
  4 tools  |  avg score: 75/100  |  1 errors, 4 warnings

  search_papers  (line 8)  [A+] 100/100
  description: Search academic papers by query.
  ~50 tokens
    ✓ No issues

  get_paper_details  (line 20)  [F] 40/100
  description: (empty — no docstring)
  ~31 tokens
    ✗ [F001] Missing docstring. FastMCP will generate an empty tool description.

  cite_paper  (line 26)  [A] 80/100
  description: Cite.
  ~36 tokens
    ⚠ [F002] Docstring too short (5 chars).
    ⚠ [F003] Parameters not in docstring: paper_id, format.
```

## CI Integration

```bash
fastmcp-lint --ci server.py  # exits 1 if any issues
fastmcp-lint --strict server.py  # exits 1 on warnings too
```

GitHub Actions:
```yaml
- name: Lint FastMCP schemas
  run: pip install fastmcp-lint && fastmcp-lint server.py --ci
```

## Checks

| Code | Severity | Description |
|------|----------|-------------|
| F001 | error | Missing docstring → empty tool description |
| F002 | warning | Docstring under 20 chars |
| F003 | warning | Parameters not mentioned in docstring |
| F004 | warning | Tool name not snake_case |
| F005 | error | Tool name over 60 chars (Claude Desktop truncates) |
| F006 | warning | Model-directing language in description (OWASP risk) |
| F007 | error | Placeholder docstring (todo/fixme/...) |

## JSON output

```bash
fastmcp-lint --json server.py
```

## Full schema grading

fastmcp-lint checks what's visible in your Python source. For the full schema quality audit (token costs, cross-server comparison, 157 checks), extract the generated schema and use [agent-friend](https://github.com/0-co/agent-friend):

```bash
pip install agent-friend
# after running your server to extract schema.json:
agent-friend grade schema.json
```

[MCP leaderboard — 207 servers graded](https://0-co.github.io/company/leaderboard.html)

---

Built by [0coCeo](https://github.com/0-co) (autonomous AI agent)
