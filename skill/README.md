# sonny-eyes skill

To install the Claude Code skill, copy the `sonny-eyes/` folder into
`.claude/skills/sonny-eyes/` in a project (or into `~/.claude/skills/` to make
it available everywhere), so `SKILL.md` ends up at that path. For an
environment that speaks MCP instead of Claude Code skills (Claude Desktop,
Cursor, etc.), run `python -m eyes mcp` and connect to it as an MCP server
instead - see `docs/mcp.md` in this repo for client configuration; it exposes
the same tools with the same report format.
