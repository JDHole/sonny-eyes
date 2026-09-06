[🇵🇱 Polski](README.md) | 🇬🇧 English

# sonny-eyes

Perceptual measurement for video shots: it takes a camera clip and turns it
into numbers (tonality, color, sharpness, noise, camera motion, brightness over
time), writes one JSON report per clip plus an HTML review page, and exposes
the same data to AI agents over an MCP server. For video creators working with
AI models, and for agents that are supposed to "watch" footage but physically
cannot.

![Review page: bricks, numbers, flags](docs/img/przeglad.png) <!-- TODO screenshot -->
![Clip profile chart](docs/img/przebieg.png) <!-- TODO screenshot -->
![JSON report for one clip](docs/img/raport-json.png) <!-- TODO screenshot -->

## The problem: how AI watches video

A model does not see pixels. It sees a grid of squares. The image is cut into
patches (28x28 px for Claude), each patch is flattened into a vector of
numbers, and the original pixels are gone - there is no way back, no way to
"zoom in". A 4K frame never arrives in 4K: it is scaled down to 2576 px on the
long side, which is a grid of 92 x 52 = 4784 patches. That is the ceiling; 8K
input will not change it. On top of that: no metadata at all. No EXIF, no ICC,
no hint that this is F-Log or 10-bit.

The vision encoder is trained to match images to TEXT (contrastive image-caption
training), not to preserve photometric fidelity. Nobody ever trained that
network to hold on to luminance values. The result is predictable: the model
will honestly say "warm", "flat", "blown out", but it will not say "black at
6 IRE" or "300 K too warm". Sonny, the agent this tool was built for, put it
this way (translated from Polish): *"I see the content and the mood of a frame,
I do not see values, and I do not see video at all, because what I get is a
handful of stills."*

Video is worse, because nobody actually watches video. The Claude API has no
"video" block - supported inputs are JPEG, PNG, GIF (no animation) and WebP, so
the only route is cutting frames with ffmpeg and sending them as a sequence of
images. Gemini accepts a video file, but the documentation describes it plainly
as a "sequence of frames" sampled at a fixed rate, 1 frame per second by
default, with no dedicated optical flow channel. Open-weight models do the same
thing, just more explicitly.

A concrete number from real footage: the camera records 50 frames per second,
so an 8 second window is 400 frames. At 1 fps sampling the model receives 8 of
them. The 392 frames where all the shake lives simply do not exist. They are
not "hard to see" - they are absent. And stability, judder, duplicate frames
and editing rhythm are exactly the properties that live BETWEEN frames, not in
a single frame.

Benchmarks say the same thing in numbers. **ColorBench**: naming the exact
color of a point is the hardest perceptual task in the whole suite, best score
57.3%; recognizing the dominant color goes far better (best 82.9% against 92.0%
for humans) - category yes, value no. **ShotBench** (3.5k expert questions from
over 200 films, 24 models): the best model stays below 60% average, and camera
movement is the hardest dimension - GPT-4o 48.3%, Qwen2.5-VL-72B 48.9%,
Gemini-2.5-flash 43.5%. **CameraBench** tests a shakiness scale directly
(static, no shaking, minimal shaking, unsteady, very unsteady) and most
open-source VLMs land at or below chance. **MotionBench**: the best video LLMs
stay below 0.60, and on repetition counting "all models scored near random".

This is not an academic problem, it is a time bill. On the Canarian Tweety
series a DCTL file named WARMTH was a no-op for an entire episode (EP02) and
nobody caught it - not the agent, not the author. One delta measurement before
and after would have caught it in a second; looking at the picture did not
catch it across a whole episode. Earlier, on EP01, the AI produced 36 TIFF
renders and 3 contact sheets to compare A/B/C looks whose deltas were
practically invisible: 30 minutes down the drain. The author's verdicts across
those iterations were (translated from Polish): *"I don't see any difference at
all, too weak, dude"*, then *"I don't see that warmth anywhere"*, and after it
was pushed harder, *"too yellow"*. Every one of those rounds was a human
scrubbing through a viewer, because there was no measurement.

![What the model sees without measurement vs with it](docs/img/bez-pomiaru-vs-z-pomiarem.png) <!-- TODO screenshot -->

## The solution: measure, do not look

One rule: **tools measure, the model interprets**. This tool only does the
first half.

The full perception stack has three layers, and they are not interchangeable -
each answers a different question and lies when used for someone else's:

1. **Physics (numbers).** Luminance percentiles, saturation, cast, Laplacian
   variance, displacement vectors between frames. Cheap, repeatable, objective.
   They answer "how much", never "is it good". This is the layer `sonny-eyes`
   covers.
2. **Visual control (scopes).** Waveform, vectorscope, profile chart and single
   frames as PNG. Here a human or a model actually looks, but at a chart, not
   at the image. A chart reads more reliably than a table of numbers and costs
   fewer tokens than a full frame. `sonny-eyes` generates these images.
3. **Semantics (model).** Shot size, camera movement, content, editorial role,
   "is this interesting". The only layer that can say "interesting", and the
   only one that can be confidently wrong. That is why it goes last, and always
   on frames selected by layer 1. `sonny-eyes` does NOT do this.

The foundation is the shot report: one JSON per clip, plus paths to frames and
scopes. The report contract:

- **`null` instead of guessing.** A metric that could not be computed (a second
  with too little texture to track, a color temperature estimate that came out
  non-finite) is written as `null`, not as a fictional zero.
- **Explicit uncertainty.** The `niepewnosc` field states what went wrong in
  this particular measurement: whether a Fuji clip was measured without a LUT,
  whether the camera is unrecognized, whether GPU decoding fell back to CPU,
  whether the measurement window was shorter than requested.
- **`werdykty` is always `null`.** Judgement is written by a human, never by
  the script. The automation is a classifier, not an operator: it flags and
  sorts, the human decides.
- **Thresholds travel with the data.** The `progi_prowizoryczne` field records,
  in EVERY report, the full set of thresholds used for flags and motion
  classification, so an old measurement can be told apart from a new one and
  reinterpreted after a threshold change. `wersja_metryk` serves the same
  purpose.

### What it measures

- **Tonality.** Brightness percentiles p1 / p5 / p50 / p95 / p99 (BT.709 luma,
  0-1 scale), percentage of pixels crushed at the bottom and clipped at the
  top, RMS contrast, spread of the per-frame median, plus a per-second
  brightness profile (p5 / p50 / p99) across the whole clip.
- **Color.** Mean and p95 saturation, R-G and B-G cast, correlated color
  temperature estimate (McCamy 1992, via `colour-science`).
- **Sharpness.** Laplacian variance: mean, min and max across the window's
  frames, plus a 3x3 grid on the sharpest frame (to tell whether the subject is
  sharp or the whole field is).
- **Noise.** Sigma estimate on the sharpest frame
  (`skimage.restoration.estimate_sigma`).
- **Camera motion.** Features (`goodFeaturesToTrack`) + optical flow
  (`calcOpticalFlowPyrLK`) + RANSAC affine fit (`estimateAffinePartial2D`)
  between consecutive samples. RANSAC rejects points on moving objects (leaves,
  passers-by) as outliers, leaving the motion of the camera itself. Output: a
  per-second profile (intended motion, jitter, measurement confidence), stable
  and moving segments, the longest stable segment, separate information about
  the first and last 2 seconds, and a shot class (`postawiona` = camera put
  down / `static` / `handheld` / `shaky`, plus `pan` added independently).
- **Cadence.** VFR flag (`r_frame_rate` vs `avg_frame_rate` mismatch), duplicate
  frame count, mean difference between consecutive frames.
- **Editing.** Clip duration. Cut detection is not implemented yet
  (`montaz.segmenty` is always empty).
- **Images.** First frame, sharpest frame, waveform, vectorscope and a clip
  profile chart (three panels: brightness after LUT, jitter, intended motion) -
  all PNG.

Tonality, color, sharpness and noise are computed on a short window (5-25 s by
default; a clip shorter than 30 s is measured in full from 0), sampled at
2 frames per second at 480 px wide, after the LUT. Motion and the brightness
profile use a separate sample: the whole clip from 0 s, 10 frames per second up
to 60 s of duration and 5 frames per second above that, with a hard limit of
180 seconds of material.

### What it does NOT do

- **Zero AI in the measurement itself.** It is ffmpeg, numpy, OpenCV,
  scikit-image and colour-science. No model is loaded, nothing goes to any API.
- **Zero verdicts.** The tool will not tell you whether a shot is good. The
  `werdykty` field in the report is always `null`.
- **Zero renders or exports.** It does not produce versions of your footage and
  does not touch DaVinci Resolve or any other NLE.
- **It modifies nothing.** Source files are read and never written. The tool
  writes only into its own output directory. Reports are regenerable: delete
  the JSON, measure again, and it is rebuilt from scratch. Nothing here is a
  source of truth except the camera clips themselves.
- **No cut detection** (for now) and **no semantic layer**.

## Quick start

### Requirements

- Python 3.12 or newer (developed and tested on 3.12.10).
- `ffmpeg` and `ffprobe` in PATH. Developed against build 8.0.1; some
  workarounds in the code exist specifically because of this version's
  behaviour (see "Limitations and gotchas").
- Optional NVIDIA GPU. Every ffmpeg call tries `-hwaccel cuda` first and
  automatically retries on CPU if it fails. The fallback is built in and
  recorded in the report (`niepewnosc.gpu_fallback_cpu`), so the tool works
  without a GPU. You can also force CPU with `--no-gpu`.
- **Tested only on Windows 11 with an RTX 4080 Laptop. macOS and Linux have not
  been verified.** The code has no explicit Windows dependency beyond the paths
  in the examples and the ffmpeg workarounds, but nobody has run it on another
  OS - if you try, a report of what happened is welcome.

### Install

```bash
git clone https://github.com/JDHole/sonny-eyes.git
cd sonny-eyes
python -m venv .venv
.venv\Scripts\activate         # Windows
# source .venv/bin/activate    # macOS / Linux
pip install -r requirements.txt
```

`requirements.txt` is the minimal set of nine packages needed for measurement
and the MCP server (install takes about 1-2 minutes, about 0.6 GB). The
author's full development environment lives in `requirements.lock` and is not
needed to run the tool. Check the install with `python -m eyes --version`.

### First measurement

```bash
python -m eyes measure --project demo --files clip.mp4
```

The output lands under `./eyes-out`, relative to the current directory:

```
eyes-out/demo/reports/clip.json          <- the report
eyes-out/demo/clip/frames/*.png          <- first and sharpest frame
eyes-out/demo/clip/scopes/*.png          <- waveform, vectorscope, profile
eyes-out/demo/_log.jsonl                 <- log: one line per clip per run
```

For several files: `--files a.MOV b.MP4` (or with the flag repeated:
`--files a.MOV --files b.MP4`); `--folder` in `batch` works the same way. By default a clip that already has a report is
skipped - `--force` re-measures it. The measurement window is set by
`--window-start` and `--window-len`.

### Batch a folder

```bash
python -m eyes batch --project demo --folder "D:/camera/day-1"
```

Scans the folder recursively and measures everything that matches. **Note: in
this version the filename filter is hardwired to the author's two cameras** -
`DSCF*.MOV` (Fuji) plus `GX*.MP4`, `GH*.MP4`, `GOPR*.MP4` (GoPro). Everything
else in the folder is skipped. Single files with any name can still be measured
with `measure --files`.

Interrupting at any point is safe: on the next run clips that already have a
report are skipped. Progress with a counter and ETA goes to
`eyes-out/demo/_postep.json` (written atomically after every file, so a reader
never sees half a JSON).

Batching in the background, without holding a terminal:

```bash
python -m eyes batch --project demo --folder "D:/camera/day-1" --detach
python -m eyes status --project demo          # or --json
python -m eyes stop --project demo            # kills the whole process tree, ffmpeg included
```

Other useful `batch` flags: `--limit N` (only the first N files, to test a
batch), `--porcja "Day 1"` (a label recorded in `_postep.json`).

### Review page

```bash
python -m eyes review --project demo
```

Builds `eyes-out/demo/_przeglad.html`: a single page with bricks (the sharpest
frame of each clip), numbers, flags, sorting and filtering. Images are embedded
as data URIs, so the file works without access to the output directory and can
be shared as one file. `--out-file path.html` writes an extra copy at the given
path, `--compact` swaps full PNGs for small JPEGs (to fit artifact size
limits), and `--status "text"` puts a banner at the top of the page.

### Duplicates

```bash
python -m eyes dupes --project demo
python -m eyes dupes --project demo --verify
```

During measurement, files whose `hash_4mb` (sha1 of the first 4 MB) matches an
earlier file in the list are recognized as content duplicates and measured only
once. `dupes` lists those pairs from the log as a decision list, and `--verify`
hashes the FULL files on both sides and marks each pair as identical or
different (different = only the first 4 MB matched, so that file is not a
deletion candidate). **It never deletes anything** - that is a human decision.

### Clip profile

```bash
python -m eyes profile --project demo
python -m eyes profile --project demo --ids DSCF0934 DSCF0935
```

Draws the profile chart from an EXISTING report, without decoding anything
again. Three panels on a shared time axis: brightness after the LUT (p5 / p50 /
p99), jitter (as a percentage of frame width) and intended motion (percent of
frame width per second), with thresholds and stable segments marked. A report
without the `tonalnosc.profil` field (from before this feature existed) is
skipped with a message.

### Smoke test

```bash
python tests/test_smoke.py
```

The gate does not use pytest: files in `tests/` are run as plain scripts.

## For AI agents

The MCP server starts with one command:

```bash
python -m eyes mcp
```

Claude Code:

```bash
claude mcp add sonny-eyes -- /path/to/.venv/bin/python -m eyes mcp
```

Claude Desktop (`claude_desktop_config.json`):

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

The server exposes eight tools:

| Tool | What it does |
|---|---|
| `probe_clip` | Returns stream parameters from ffprobe (codec, resolution, fps, pix_fmt, range, duration) without measuring anything. |
| `measure_clip` | Measures one clip and writes a shot report. |
| `get_report` | Returns the finished JSON report for a given clip. |
| `list_reports` | Lists the reports that exist in a project. |
| `batch_start` | Starts a folder batch as a background process. |
| `batch_status` | Returns batch progress (done, errors, ETA). |
| `batch_stop` | Stops a running background batch. |
| `review_page` | Builds the HTML review page for a project. |

There is also a skill: copy the `skill/sonny-eyes/` directory into your
project's `.claude/skills/` (or into `~/.claude/skills/`). The skill teaches
the agent when to reach for a measurement instead of looking, and how to read
the report fields.

Configuration details, permissions and example calls: [docs/mcp.md](docs/mcp.md).

## Output

### Folder layout

Every path below is configurable (see "Configuration"); this is the default,
i.e. everything under `./eyes-out` relative to the current directory.

```
eyes-out/
  _luts/                             copies of the LUTs used for measurement
  <project>/
    reports/<id>.json                shot report, one per clip
    <id>/frames/<id>_pierwsza.png    first frame
    <id>/frames/<id>_najostrzejsza.png   sharpest frame
    <id>/scopes/<id>_waveform.png
    <id>/scopes/<id>_vectorscope.png
    <id>/scopes/<id>_przebieg.png    profile chart
    _log.jsonl                       one JSON line per clip per run
    _postep.json                     batch progress (batch only)
    _runner.json                     pid and command of the background process (--detach only)
    _batch.log                       stdout and stderr of the background process
    _przeglad.html                   review page (review only)
```

`id` is the filename without its extension (`DSCF3236`). A name collision
within one run produces `name@parent_folder`. The report file is always
`{id}.json`.

`_log.jsonl` has one line per clip per run: id, filename, status (`ok` /
`pominieto` = skipped / `duplikat` / `blad` = error), duration, metrics version,
and the error text when something failed. `_postep.json` is overwritten
atomically after every file and holds: project, batch label, folder list,
status (`w toku` = running / `zakonczony` = finished / `zakonczony z bledami` =
finished with errors / `przerwany` = interrupted), counters (files, done, ok,
skipped, duplicates, errors), average time, ETA and the last processed file.

### Report shape

An excerpt from a real report (Fuji 4K50 clip, 12 s, handheld moving shot; the
`profil`, `odcinki` and `siatka_3x3` arrays are truncated):

```json
{
  "wersja_metryk": "0.2",
  "id": "DSCF0934",
  "projekt": "Canarian Tweety EP03",
  "zrodlo": {
    "plik": "DSCF0934.MOV", "kamera": "Fuji", "profil": "F-Log",
    "lut_pomiarowy": "FLog_to_Rec709_65pt.cube",
    "hash_4mb": "e69685b4caec2a965ef4a861f5c71da49bd3e853",
    "rozmiar_b": 307694592, "czas_s": 12.0
  },
  "stream": {
    "codec": "hevc", "w": 3840, "h": 2160, "fps": 50.0, "fps_avg": 50.0,
    "pix_fmt": "yuv420p10le", "range": "pc", "transfer": "smpte170m",
    "primaries": "bt709", "nb_frames": 600
  },
  "okno_pomiaru": {
    "start_s": 0.0, "koniec_s": 12.0, "fps_probki_a": 2, "fps_probki_b": 10.0,
    "szerokosc_px": 480, "liczba_klatek_a": 24, "liczba_klatek_b": 120
  },
  "tonalnosc": {
    "p1": 0.001, "p5": 0.001, "p50": 0.008, "p95": 0.066, "p99": 0.144,
    "clip_lo_pct": 61.168, "clip_hi_pct": 0.029,
    "kontrast_rms": 0.042, "p50_rozrzut": 0.005,
    "profil": [{"t_s": 0, "p5": 0.0, "p50": 0.004, "p99": 0.072}]
  },
  "kolor": {"sat_mean": 0.499, "sat_p95": 1.0, "cast_rg": 0.003, "cast_bg": 0.007, "cct_est_k": 7743.439},
  "ostrosc": {"lapvar": 52.285, "lapvar_min": 21.624, "lapvar_max": 124.618,
              "siatka_3x3": [47.258, 209.048, 185.412], "skala_pomiaru_px": 480},
  "szum": {"sigma": 0.002},
  "ruch": {
    "ruch_zamierzony_pct_s": 30.144, "jitter_rms_pct": 1.733,
    "mediana_jitter_pct": 1.016, "p90_jitter_pct": 2.416,
    "profil": [{"t_s": 0, "ruch_pct": 36.611, "jitter_pct": 1.236, "conf": 0.857}],
    "odcinki": [{"od_s": 0, "do_s": 11, "typ": "ruch"}],
    "srodek": null, "brzegi": {"poczatek_ruch": false, "koniec_ruch": false},
    "pary_niepewne": 31, "klasa": ["shaky", "pan"],
    "zrodlo": "lk_ransac_affine", "obcieto_s": null
  },
  "plynnosc": {"vfr": false, "duplikaty": 0, "tdiff": 0.01},
  "montaz": {"dlugosc_s": 12.0, "segmenty": []},
  "flagi_prowizoryczne": ["czern_zabita", "trzesie"],
  "werdykty": null,
  "niepewnosc": {"pomiar_bez_lut": false, "kamera_nieznana": false,
                 "gpu_fallback_cpu": false, "okno_krotsze_niz_zadane": true},
  "pomiar": {"czas_dekodowania_s": 5.841, "czas_calkowity_s": 7.734, "gpu": true,
             "ffmpeg": "8.0.1-full_build-www.gyan.dev", "opencv": "5.0.0"}
}
```

Field names are in Polish, and that is a deliberate decision: the report is a
data contract already consumed by the author's other tools, so it is not
renamed for cosmetics. A full English dictionary of every field - type,
meaning, gotchas - lives in [docs/report-fields.md](docs/report-fields.md).

### Review page

`review` assembles every report in a project into one HTML page: a card per
clip with the sharpest frame (switchable to waveform and profile chart), the
six most important numbers, flags, motion class, sorting (by id, black level,
clipping, sharpness, jitter) and filters by flag and camera. At the top there
is a "how to read the numbers" section that explains each metric in words
rather than in math.

![Waveform and vectorscope for one clip](docs/img/skopy.png) <!-- TODO screenshot -->

## Configuration

With no configuration at all the tool runs immediately and writes everything
under `./eyes-out` relative to the current directory. To change that, copy
`config.example.toml` to `config.toml` next to the repo and uncomment what you
need. `config.toml` is in `.gitignore` - it holds local paths and does not go
into the repo.

```toml
# Root output folder used when nothing else is configured.
out_root = "./eyes-out"

# Per-clip cache: frames, scopes, _log.jsonl, _postep.json, _luts/.
# Defaults to the same value as out_root.
cache_root = "./eyes-out"

# Where finished JSON reports are written. MUST contain the literal
# "{project}" placeholder, filled in from --project.
# Default: "{cache_root}/{project}/reports".
reports_root = "./eyes-out/{project}/reports"

# Per-camera LUT table. Key = camera name as it appears in the report's
# zrodlo.kamera field, lowercased ("fuji", "gopro"); value = path to a .cube
# file applied before measuring that camera's clips.
[lut]
fuji = "C:/path/to/FLog_to_Rec709.cube"
```

A camera missing from the `[lut]` table (or an absent table) is measured
without a LUT, which the report records in `niepewnosc.pomiar_bez_lut`. The
`--lut path.cube` flag overrides the whole table and forces one LUT on every
clip regardless of camera.

Environment variables:

- `EYES_OUT` - root output folder, same as `out_root`.
- `EYES_CONFIG` - explicit path to a `config.toml`.

**Override order (first wins):** CLI flags (`--out`, `--config`, `--lut`) >
environment variables (`EYES_OUT`, `EYES_CONFIG`) > `config.toml` > built-in
defaults. `--out X` is stronger than it looks: it sets `out_root`, `cache_root`
and `reports_root` at once, overriding even an explicit `reports_root` from the
config file - otherwise `--out` pointing at a temp directory would still write
reports to the configured location.

## Limitations and gotchas

**The thresholds are provisional.** The flag and motion-classification
thresholds (`jitter_stabilny_max` 0.4, `ruch_stabilny_max` 3.0,
`jitter_shaky_min` 0.6 and the rest) were hand-calibrated on THREE clips with a
human verdict attached (a camera resting on a wall, a handheld hero shot, a
tripod shot), not on a diverse sample. They started from a rough figure from
the literature and were raised, because on real footage they fragmented one
long stable segment into a dozen short ones. Treat them as a starting point for
calibration on your own material, not as a standard. That is why they ride
along in every report as `progi_prowizoryczne` - the classification can be
recomputed after a threshold change without re-measuring.

**What the v0.2 motion metric does not catch:**

1. Rotation and scale are computed from the affine matrix but unused. Camera
   roll and zoom during a shot have no effect on the class today.
2. "Pan" is computed from the mean magnitude of the smoothed displacement, not
   from an averaged VECTOR, so very strong chaotic jitter can, in an extreme
   case, also add "pan".
3. Low-texture scenes (clear sky, a blown-out wall) yield too few features to
   track - pairs, or whole seconds, end up as `null` rather than a fictional
   zero.
4. `ruch.brzegi` looks rigidly at the first and last 2 seconds. Putting the
   camera down over a noticeably longer stretch can partly leak outside that
   window.
5. Tracking breakdown (a hand covering the lens when starting or stopping the
   recording) can produce a single second with a physically nonsensical
   `ruch_pct` at low `conf`. The aggregates and the edge gate are protected
   against this (median plus a minimum confidence), but the raw `ruch.profil`
   still shows such values.
6. A large object moving coherently in frame (a silhouette leaning into the
   wind) can partly leak into `ruch_pct`, even though RANSAC rejects most of
   its points.
7. There is no cut detection at all - `montaz.segmenty` is always empty.

**Measurement time on long clips.** Motion is computed from the whole clip (up
to 180 s), not from a short window, and that dominates the cost. Decoding 4K
10-bit HEVC runs in practice around 200-300 frames per second of effective
throughput REGARDLESS of the target sampling fps, because the `fps` filter
drops frames AFTER decoding, not before - the entire time range is fully
decoded either way. The GPU gain is moderate (roughly 20-50% on decoding),
because the most expensive step can be the CPU-side `lut3d`, not the decode.
Every measurement records its own timing in the report
(`pomiar.czas_calkowity_s`, `pomiar.czas_dekodowania_s`), so it is easy to
measure this on your own machine.

**Windows: LUTs and the drive colon.** Passing a Windows path as the `file=`
value of the `lut3d` filter breaks the filtergraph parser in this ffmpeg build,
and it breaks regardless of whether the colon is escaped or the value is
quoted - the parser trips on the drive letter either way. The workaround is
built in: the LUT is copied once into `{cache_root}/_luts/`, ffmpeg is launched
with `cwd` set to that directory, and the LUT is referenced by bare filename,
with no colon involved at all.

**Windows: console encoding.** The Windows console will not print non-ASCII
characters in some modes (cp1252) and dies with `UnicodeEncodeError`. Every CLI
entry point calls `sys.stdout.reconfigure(encoding="utf-8")` (and the same for
stderr) on startup, and all files are written and read as UTF-8. Paths
containing `#` and spaces work without escaping, because all ffmpeg and ffprobe
calls go through `subprocess.run` with an argument list, without a shell.

## Where this came from

This is a slice of JDHole OS, one video creator's life and production system,
where twelve AI agents each own a domain. Sonny owns color and post. Across
four episodes of the Canarian Tweety series (roughly 1111 clips, 1 TB of Fuji
and GoPro footage) every "does this look right" went through the author's eyes,
because the agent physically could not see the material - and every time it
pretended it could, it cost hours (a revert of 516 grade instances, 36
worthless renders, WARMTH as a no-op for a whole episode). `sonny-eyes` is the
answer to that: not another model, but the measurement layer underneath one. It
goes open source because the research behind the project found a real gap -
measuring (rather than fixing) camera shake has practically no repositories,
and the best image-quality scorers ship non-commercial licences, so they cannot
be used in monetized production. If it saves someone else those same hours, the
work paid for itself twice.

## License

MIT. See [LICENSE](LICENSE).

## Contributing

Issues are welcome - especially results from macOS and Linux, and threshold
calibration on footage other than Fuji and GoPro. A pull request should come
with a test in `tests/` written as a plain script run via
`python tests/test_something.py` (there is no pytest in this repo). No new pip
dependencies beyond what is already in the lock - if something is genuinely
missing, describe it in an issue first.
