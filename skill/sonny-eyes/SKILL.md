---
name: sonny-eyes
description: Measure video clips with numbers (exposure, color, sharpness, noise, camera motion, scopes) instead of guessing from frames - use when the user asks about a shot's exposure, sharpness, shake/stability, or wants to compare or pick between clips.
---

# sonny-eyes

sonny-eyes is a perception-measurement tool for camera clips. It decodes a
window of a clip with ffmpeg and runs numeric analysis (numpy/OpenCV/
scikit-image/colour-science) - brightness, color, sharpness, noise, and a
full-clip camera-motion analysis - and writes one JSON report per clip. It
does **not** judge footage. There is no AI model in the loop and no verdict:
every number is a direct measurement, and the report's `werdykty` field is
always `null` because deciding whether a shot is usable is a human call.

## When to reach for this

Use sonny-eyes whenever a question is really about the pixels, not about
memory or vibes:

- "Is this clip too dark / blown out / soft?"
- "How shaky is this handheld shot?"
- "Which of these takes is sharper / more stable / better exposed?"
- Picking or ranking shots for an edit based on technical quality.
- Anything where you would otherwise have to guess a number by looking at a
  thumbnail.

Do not use it to render, transcode, color-grade, or otherwise modify video -
it only measures and writes small PNG previews (thumbnails + scopes), never
touches the source file, and never exports.

## Two ways to call it

**MCP (preferred when available):** run `python -m eyes mcp` (stdio) and use
its tools directly - `probe_clip`, `measure_clip`, `get_report`,
`list_reports`, `batch_start`, `batch_status`, `batch_stop`, `review_page`.
See `docs/mcp.md` in this repo for client setup. This is the only way to get
structured JSON back without parsing CLI stdout.

**CLI (works anywhere a shell does):**

```
python -m eyes measure --project "Name" --files clip1.mov clip2.mp4
python -m eyes batch --project "Name" --folder "path/to/folder" --detach
python -m eyes status --project "Name" --json
python -m eyes stop --project "Name"
python -m eyes review --project "Name"
```

Common flags: `--out X` (single output folder override - use this for any
throwaway/test run so nothing lands in the user's real report folders),
`--config X` (explicit config.toml), `--lut X` / `--no-gpu` (measure/batch
only), `--force` (re-measure even if a report already exists).

`measure` on a single clip takes roughly 5-60 seconds (synchronous, one
process). `batch` on a folder can take minutes to hours depending on clip
count and length - **always use `--detach` for more than a couple of clips**,
then poll `status` every 10-20 seconds. Never block on a batch run, and never
run it without `--detach` unless it's a single test clip.

## Reading the report

A report is one JSON file per clip (`{id}.json`, id = filename stem, e.g.
`DSCF3236`). Top-level fields:

| Field | Meaning |
|---|---|
| `wersja_metryk` | Metrics schema version for this report. |
| `id` | Clip identifier (filename stem). |
| `projekt` | Project name it was measured under. |
| `zrodlo` | Source file info: filename, path, dedup hash, size, mtime, detected camera, color profile, LUT applied (or null), duration. |
| `stream` | Container/stream info from ffprobe: codec, resolution, frame rate, pixel format, color range/transfer/primaries, frame count. |
| `okno_pomiaru` | The measurement window actually used (start/end seconds, sampling rates, frame counts) - shorter clips are measured in full. |
| `tonalnosc` | Brightness: percentiles `p1`/`p5`/`p50`/`p95`/`p99` of luma (0=black, 1=white), `clip_lo_pct`/`clip_hi_pct` (% of pixels clipped to black/white), `kontrast_rms`, `p50_rozrzut` (how much the frame median varies across the window), and `profil` (per-second brightness trace - large, see compact mode below). |
| `kolor` | `sat_mean`/`sat_p95` (saturation), `cast_rg`/`cast_bg` (color cast relative to green), `cct_est_k` (estimated color temperature in Kelvin). |
| `ostrosc` | Sharpness via Laplacian variance: `lapvar` (mean), `lapvar_min`/`lapvar_max`, `siatka_3x3` (sharpness per 3x3 grid cell - useful for detecting off-center focus). Content-dependent: compare within a scene, not across wildly different subjects. |
| `szum` | `sigma`: estimated noise level (can be `null` when it can't be estimated). |
| `ruch` | Camera motion, measured across the WHOLE clip (not just the measurement window): `klasa` (list of labels - `static`/`handheld`/`shaky`/`postawiona`(tripod-like)/`pan`), `jitter_rms_pct`/`mediana_jitter_srodka_pct` (frame-to-frame shake, in % of frame width), `ruch_zamierzony_pct_s`/`mediana_ruch_srodka_pct` (intentional movement per second), `srodek`/`odcinki`/`brzegi` (the detected stable middle section and unstable edges), `pary_niepewne` (frame pairs the tracker couldn't trust), `profil` (per-second trace - large, see compact mode). |
| `plynnosc` | Frame timing: `vfr` (variable frame rate detected), `duplikaty` (near-duplicate frame count), `tdiff` (mean frame-to-frame difference). |
| `montaz` | `dlugosc_s` (clip length); `segmenty` is always empty in v0 - cut detection is not implemented yet. |
| `klatki` | Paths to extracted preview frames (first frame, sharpest frame). |
| `skopy` | Paths to scope images (waveform, vectorscope, and a rendered motion/brightness trace chart). |
| `flagi_prowizoryczne` | Active warning flags for this clip only (e.g. `czern_mleczna` = milky blacks, `trzesie` = shaky, `nieostre` = soft, `czern_zabita` = crushed blacks, `clip_hi>1%` = highlight clipping). An empty list means none triggered - not "not checked". |
| `progi_prowizoryczne` | The actual threshold values used to decide the flags and motion class above, echoed into every report. |
| `werdykty` | Always `null`. Judging whether a clip is usable is a human decision - never invent or infer a verdict from the numbers yourself. |
| `niepewnosc` | Caveats on this specific measurement: `pomiar_bez_lut` (no LUT was available/applied), `kamera_nieznana` (camera not recognized from filename), `gpu_fallback_cpu` (GPU decode failed, fell back to CPU), `okno_krotsze_niz_zadane` (clip shorter than the requested window). |
| `pomiar` | Run metadata: timestamp, decode/total time, whether GPU was used, ffmpeg/OpenCV versions. |

`null` anywhere in a report means "not measured" (or "couldn't be
estimated"), not zero and not "fine". Treat it as missing data.

## Rules

- **Never state a number from looking at a frame or thumbnail.** If you
  haven't measured it (`measure_clip` / `python -m eyes measure`), you don't
  have a number for it - say so, or measure it.
- **Always cite the actual value from the report** when answering ("p5 is
  0.13, clip_hi_pct is 0.02%"), not a paraphrase or a rounded guess.
- `flagi_prowizoryczne`, `progi_prowizoryczne`, and the motion `klasa`
  thresholds are explicitly **provisional** - hand-calibrated on a small
  number of reference clips, not settled science. Present them as "the
  current provisional threshold says X", not as an authoritative verdict.
- Do not render, re-encode, color-grade, or export video. This tool only
  measures and writes small PNG previews/reports.
- For `batch`, always detach and poll `status` - never run it in the
  foreground and block, and never poll faster than every ~10 seconds.
