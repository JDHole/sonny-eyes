# sonny-eyes MCP server

`python -m eyes mcp` starts an MCP server over stdio exposing sonny-eyes'
clip-measurement tools to any MCP client. It runs entirely on your machine:
it does not call out to the network, does not send clip data or reports
anywhere, and only touches the filesystem to read the clips you point it at
and write reports/cache under its configured output location (`EYES_OUT`,
`config.toml`, or the `./eyes-out` default - see the main README's "Uruchamianie"
section). Treat it like any other local CLI tool wrapped for an LLM client.

## Configuration

The server picks up configuration exactly like the CLI does (see
`eyes/config.py`): `EYES_CONFIG` (explicit path to a `config.toml`),
`EYES_OUT` (single output-root override for out/cache/reports), a
`config.toml` next to the repo, or built-in defaults. Set these as
environment variables on the server process - there are no `--out`/`--config`
command-line flags for the `mcp` subcommand itself.

## Claude Code

```
claude mcp add sonny-eyes --env EYES_OUT="C:/path/to/eyes-out" -- "C:/path/to/sonny-eyes/.venv/Scripts/python.exe" -m eyes mcp
```

Use the absolute path to the repo's venv Python (not a bare `python`) so the
server always runs with the locked dependencies from `requirements.lock`.
Drop `--env EYES_OUT=...` if you already have a `config.toml` next to the
repo with the paths you want.

## Claude Desktop

Add an entry under `mcpServers` in `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "sonny-eyes": {
      "command": "C:/path/to/sonny-eyes/.venv/Scripts/python.exe",
      "args": ["-m", "eyes", "mcp"],
      "env": {
        "EYES_OUT": "C:/path/to/eyes-out"
      }
    }
  }
}
```

## Cursor

Same shape, in Cursor's MCP settings (`mcp.json` or the MCP panel in
Settings):

```json
{
  "mcpServers": {
    "sonny-eyes": {
      "command": "C:/path/to/sonny-eyes/.venv/Scripts/python.exe",
      "args": ["-m", "eyes", "mcp"],
      "env": {
        "EYES_OUT": "C:/path/to/eyes-out"
      }
    }
  }
}
```

## Tools

| Tool | What it does |
|---|---|
| `probe_clip(path)` | Reads container/stream metadata (codec, resolution, frame rate, color info, duration, detected camera) via ffprobe - no decoding, under a second. |
| `measure_clip(path, project, force, lut, compact)` | Runs the full ffmpeg/numpy/OpenCV measurement and returns the report (5-60s, or instant if a report already exists and `force` is false). |
| `get_report(project, id, compact)` | Loads an already-measured report from disk by project and clip id, without re-measuring. |
| `list_reports(project)` | Lists every report in a project as a short summary row (id, file, camera, duration, motion class, flags). |
| `batch_start(project, folders, porcja, limit, force, no_gpu)` | Starts measuring every camera clip under one or more folders as a detached background process and returns immediately. |
| `batch_status(project)` | Reports whether a detached batch is running and how far it got. |
| `batch_stop(project)` | Kills a running detached batch for a project. |
| `review_page(project, compact)` | Generates the HTML review page (thumbnails, numbers, flags) for a project and returns its path. |

## Example dialog

> **User:** Is this clip usable? `C:/clips/DSCF3236.MOV`
>
> **Claude:** *(calls `measure_clip` with that path)* I measured it - it's a
> 14s Fuji clip. Blacks sit at p5=0.13 (a touch milky, flagged
> `czern_mleczna`), no highlight clipping (`clip_hi_pct` 0.02%), sharpness
> (`lapvar`) is 244. Camera motion is classified `handheld, pan` with a
> jitter of 0.53% of frame width - not flagged as shaky. No verdict is baked
> in (`werdykty` is always null) - technically it looks fine except for the
> slightly milky blacks; whether that matters is your call.
>
> **User:** How does that compare to DSCF3066?
>
> **Claude:** *(calls `measure_clip` on DSCF3066, or `get_report` if it was
> already measured)* DSCF3066 is steadier: its stable-middle jitter
> (`mediana_jitter_srodka_pct`) is 0.14% versus DSCF3236's 0.43%. Blacks are
> cleaner too - p5 is 0.05 with no `czern_mleczna` flag, versus DSCF3236's
> 0.13. Sharpness is close (`lapvar` 217 vs 244). Numbers are from each
> clip's own report, not a side-by-side guess.
