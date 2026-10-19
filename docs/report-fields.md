# Report fields

Dictionary for the shot report written by `python -m eyes measure` (one JSON
per clip, at `{reports_root}/{id}.json`). Field names are in Polish because the
report is a data contract already consumed by other tools; this document is the
English translation of that contract.

Everything below is derived from the code (`eyes/report.py`, `eyes/metrics.py`,
`eyes/cmd_measure.py`, `eyes/probe.py`) as of metrics version `0.2`.

## Conventions

- **Rounding.** Every float in the report is rounded to 3 decimal places on
  write (`eyes/report.py:round_floats`). Booleans are left alone.
- **Luma.** Brightness metrics use BT.709 luma (`0.2126 R + 0.7152 G +
  0.0722 B`) on a 0-1 scale, computed after the LUT when one applies.
- **"% of frame width".** Motion values are normalized by the measurement
  width, not the source width. The measurement width is 480 px
  (`okno_pomiaru.szerokosc_px`), so the numbers are resolution-independent.
- **`null` means "not computed".** It never means zero. A metric that could not
  be produced (too few tracked features, a non-finite estimate, a missing
  optional dependency) is written as `null`.
- **Two samples.** Sample A is a short window (default 5-25 s; a clip under
  30 s is measured in full from 0) at 2 fps and 480 px, after the LUT - it
  feeds `tonalnosc` (except `profil`), `kolor`, `ostrosc`, `szum`, `klatki` and
  the scope timestamps. Sample B is the whole clip from 0 s at 10 fps (clips up
  to 60 s) or 5 fps (longer), capped at 180 s of material, also after the LUT -
  it feeds `ruch`, `plynnosc` and `tonalnosc.profil`.

## Top level

| field | type | meaning | notes |
|---|---|---|---|
| `wersja_metryk` | string | Metrics schema version of this report. | `"0.2"` in the current code. Reports tagged `"0.1"` used a different (less reliable) motion method; the review page marks them explicitly. |
| `id` | string | Record key for the clip: filename without its last extension. | Collisions inside one run get `stem@parent_folder`, and a second collision on that adds `~2`, `~3`. Never contains `#`, `/` or a backslash. The report file is always `{id}.json`. |
| `projekt` | string | Project name passed via `--project`. | Groups reports and cache. Fills the `{project}` placeholder in `reports_root`. |
| `zrodlo` | object | The source file: identity, size, camera, LUT. | See below. |
| `stream` | object | Video stream parameters read by ffprobe. | See below. |
| `okno_pomiaru` | object | What was actually sampled and how. | See below. |
| `tonalnosc` | object | Brightness distribution metrics. | See below. |
| `kolor` | object | Saturation, cast and color temperature. | See below. |
| `ostrosc` | object | Laplacian-variance sharpness metrics. | See below. |
| `szum` | object | Noise sigma estimate. | See below. |
| `ruch` | object | Camera motion (v0.2 LK + RANSAC affine). | See below. |
| `plynnosc` | object | Cadence: VFR, duplicate frames, inter-frame difference. | See below. |
| `montaz` | object | Editing-level data. | Duration only; cut detection is not implemented. |
| `klatki` | array of object | Extracted still frames on disk. | See below. |
| `skopy` | array of object | Scope and chart images on disk. | See below. |
| `flagi_prowizoryczne` | array of string | Provisional flags raised by the thresholds in `progi_prowizoryczne`. | Empty array when nothing fired. Possible values listed below. |
| `progi_prowizoryczne` | object | The exact thresholds used for this measurement. | Copied into every report so classification can be recomputed later without re-measuring. |
| `werdykty` | null | Human judgement slot. | Always `null` on write. The tool never fills it; a person or a downstream process does. |
| `niepewnosc` | object | Explicit "what I do not know about this measurement". | See below. |
| `pomiar` | object | Provenance of the measurement run itself. | See below. |

## `zrodlo` - source file

| field | type | meaning | notes |
|---|---|---|---|
| `zrodlo.plik` | string | File name with extension. | |
| `zrodlo.sciezka_rel` | string | Absolute path to the source file, backslashes normalized to forward slashes. | The name is historical: reports written before the public version stored a path relative to a shared root, so old and new reports can differ here. |
| `zrodlo.hash_4mb` | string | sha1 hex of the first 4 MB of the file. | Used for content-duplicate detection: a file whose `hash_4mb` matches an earlier file in the same run is skipped and logged as `duplikat`. A cheap heuristic, not proof - `eyes dupes --verify` re-hashes the whole file. |
| `zrodlo.rozmiar_b` | integer | File size in bytes. | |
| `zrodlo.mtime` | string | File modification time, ISO 8601 with local timezone offset. | |
| `zrodlo.kamera` | string | Detected camera: `"Fuji"`, `"GoPro"` or `"nieznana"` (unknown). | Detected from the filename only: `DSCF*.MOV` maps to Fuji, `GX*/GH*/GOPR*.MP4` to GoPro. |
| `zrodlo.profil` | string or null | Assumed capture profile for that camera: `"F-Log"` for Fuji, `"Rec709"` for GoPro. | `null` for an unknown camera. A lookup by camera name, not a measurement - the container does not carry this information. |
| `zrodlo.lut_pomiarowy` | string or null | File name of the `.cube` LUT applied before measuring. | `null` means the clip was measured with no LUT. Source is either `--lut` (forced on every clip) or the `[lut]` table in `config.toml`, keyed by lowercased camera name. |
| `zrodlo.czas_s` | number | Clip duration in seconds, from ffprobe. | `0.0` when ffprobe reported no duration. |

## `stream` - ffprobe stream parameters

All values come straight from the first video stream reported by `ffprobe`;
any of them can be `null` if the container does not carry the tag.

| field | type | meaning | notes |
|---|---|---|---|
| `stream.codec` | string or null | Codec name (`codec_name`), e.g. `"hevc"`. | |
| `stream.w` | integer or null | Frame width in pixels (source). | |
| `stream.h` | integer or null | Frame height in pixels (source). | |
| `stream.fps` | number or null | Nominal frame rate (`r_frame_rate`) as a float. | |
| `stream.fps_avg` | number or null | Average frame rate (`avg_frame_rate`) as a float. | A mismatch with `fps` sets `plynnosc.vfr`. |
| `stream.pix_fmt` | string or null | Pixel format, e.g. `"yuv420p10le"`. | |
| `stream.range` | string or null | Color range tag (`color_range`), e.g. `"pc"` or `"tv"`. | |
| `stream.transfer` | string or null | Transfer characteristics tag (`color_transfer`). | Do not trust it for log footage: a Fuji F-Log file reports `smpte170m` while the pixel values are logarithmic. That is exactly why a LUT has to be supplied by hand. |
| `stream.primaries` | string or null | Color primaries tag (`color_primaries`). | |
| `stream.nb_frames` | integer or null | Frame count declared by the container. | `null` when the container does not declare an integer count. |

## `okno_pomiaru` - measurement window

| field | type | meaning | notes |
|---|---|---|---|
| `okno_pomiaru.start_s` | number | Start of sample A in seconds. | `--window-start` (default 5.0), or `0.0` for a clip shorter than 30 s. |
| `okno_pomiaru.koniec_s` | number | End of sample A in seconds (`start_s` plus window length). | For a clip shorter than 30 s this equals the clip duration. |
| `okno_pomiaru.fps_probki_a` | integer | Sampling rate of sample A, frames per second. | Constant `2` in this version. |
| `okno_pomiaru.fps_probki_b` | number | Sampling rate of sample B, frames per second. | `10` for clips up to 60 s, `5` above. |
| `okno_pomiaru.szerokosc_px` | integer | Width in pixels both samples were scaled to before measurement. | Constant `480`. Sharpness and motion values are only comparable between clips measured at the same width. |
| `okno_pomiaru.liczba_klatek_a` | integer | Number of frames actually decoded for sample A. | |
| `okno_pomiaru.liczba_klatek_b` | integer | Number of frames actually decoded for sample B. | |

## `tonalnosc` - brightness distribution

Computed on sample A (except `profil`), over all pixels of all frames pooled
together, on BT.709 luma in 0-1.

| field | type | meaning | notes |
|---|---|---|---|
| `tonalnosc.p1` | number | 1st percentile of luma. | |
| `tonalnosc.p5` | number | 5th percentile of luma - the working "where the black sits" number. | Author's working reading after a LUT: 0.02-0.04 seated black, above 0.06 milky. Provisional, and a genuinely high-key scene has no black at all. |
| `tonalnosc.p50` | number | Median luma. | |
| `tonalnosc.p95` | number | 95th percentile of luma. | |
| `tonalnosc.p99` | number | 99th percentile of luma - the working "where the highlights sit" number. | |
| `tonalnosc.clip_lo_pct` | number | Percentage of pixels below 0.01 luma (crushed blacks). | |
| `tonalnosc.clip_hi_pct` | number | Percentage of pixels above 0.99 luma (clipped highlights). | |
| `tonalnosc.kontrast_rms` | number | Standard deviation of luma over all pooled pixels. | A distribution width, not a formal contrast ratio. |
| `tonalnosc.p50_rozrzut` | number | Standard deviation of the per-frame median across the window's frames. | A high value means exposure moved during the window (auto exposure, a pan into the sun). |
| `tonalnosc.profil` | array of object | Per-second brightness profile over the whole clip. | Computed on sample B, so it covers the whole clip (capped at 180 s), not just the A window. |
| `tonalnosc.profil[].t_s` | integer | Second index, counted from 0 s of the clip. | |
| `tonalnosc.profil[].p5` | number | 5th percentile of luma over all pixels of that second's frames. | |
| `tonalnosc.profil[].p50` | number | Median luma for that second. | |
| `tonalnosc.profil[].p99` | number | 99th percentile of luma for that second. | |

A trailing partial second (when the frame count is not a multiple of the
sampling rate) is dropped, so percentiles are never computed from a handful of
frames.

## `kolor` - color

Computed on sample A.

| field | type | meaning | notes |
|---|---|---|---|
| `kolor.sat_mean` | number | Mean HSV saturation (0-1) over all pixels of all window frames. | HSV conversion via OpenCV on normalized float RGB. |
| `kolor.sat_p95` | number | 95th percentile of HSV saturation. | A value of exactly `1.0` means at least 5% of pixels are fully saturated. |
| `kolor.cast_rg` | number | Mean R minus mean G, on 0-1 channels. | Computed over ALL pixels of the sample, not restricted to mid-tones. Gray-world logic: meaningful for consistency between shots, misleading on a scene with a genuine dominant color (a forest reads "green cast" at correct white balance). |
| `kolor.cast_bg` | number | Mean B minus mean G, on 0-1 channels. | Negative means the image leans yellow or orange, positive means it leans blue. Same caveat as `cast_rg`. |
| `kolor.cct_est_k` | number or null | Correlated color temperature estimate in kelvin from the mean RGB of the sample (sRGB to XYZ to xy to CCT, McCamy 1992). | `null` when `colour-science` is unavailable or the result is not finite. An estimate from an average pixel, not a white-balance measurement of a known neutral. |

## `ostrosc` - sharpness

Computed on sample A. Grayscale conversion here uses OpenCV's
`COLOR_RGB2GRAY` (BT.601 weights), unlike the BT.709 luma used for tonality.

| field | type | meaning | notes |
|---|---|---|---|
| `ostrosc.lapvar` | number | Mean Laplacian variance across the window's frames. | Content-dependent: a thicket of leaves scores in the thousands, smooth fog scores in the hundreds even when perfectly sharp. Useful for comparisons within one scene, not as an absolute quality score. Also reacts to noise. |
| `ostrosc.lapvar_min` | number | Lowest per-frame Laplacian variance in the window. | |
| `ostrosc.lapvar_max` | number | Highest per-frame Laplacian variance in the window - the sharpest frame. | The frame that produced this value is saved as `najostrzejsza` and used for the scopes and the noise estimate. |
| `ostrosc.siatka_3x3` | array of 9 numbers | Laplacian variance per cell of a 3x3 grid on the sharpest frame, row-major from the top-left. | Tells whether sharpness sits in the subject or across the field: a center cell several times above the mean suggests shallow depth of field with the subject hit. |
| `ostrosc.skala_pomiaru_px` | integer | Width in pixels the frames were measured at. | Constant `480`. Same-scale rule: comparing Laplacian variance between different measurement widths is meaningless. |

## `szum` - noise

| field | type | meaning | notes |
|---|---|---|---|
| `szum.sigma` | number or null | Estimated noise standard deviation on the sharpest frame, averaged over channels, on a 0-1 image (`skimage.restoration.estimate_sigma`). | `null` when scikit-image is unavailable or the estimate is not finite. Does not separate wanted grain from sensor noise - that distinction is not solved here. |

## `ruch` - camera motion (v0.2)

Computed on sample B (the whole clip from 0 s, capped at 180 s) on grayscale
frames. Method: `goodFeaturesToTrack` on the first frame of each pair,
`calcOpticalFlowPyrLK` to track them onto the second, `estimateAffinePartial2D`
with RANSAC to fit a similarity transform. Points on moving objects are usually
outliers to the common background motion and RANSAC rejects them, which is what
separates camera motion from subject motion. A pair is rejected (`null`) when
fewer than 12 points are tracked or the RANSAC inlier ratio falls below 30%.

Two different notions of "middle" appear here and they are not the same thing.
`ruch.srodek` is the longest DETECTED stable segment. The aggregates below are
computed over a FIXED trimmed range: the whole clip minus the first and last
2 seconds (a clip whose sampled span is shorter than 6 s uses all seconds).

| field | type | meaning | notes |
|---|---|---|---|
| `ruch.ruch_zamierzony_pct_s` | number or null | Intended camera motion: mean of the per-second `ruch_pct` over the trimmed range, in percent of frame width per second. | Same field name as in v0.1 but a different computation. |
| `ruch.jitter_rms_pct` | number or null | Shake: RMS of the per-second `jitter_pct` over the trimmed range, in percent of frame width. | This is the value gating `handheld` versus `shaky`. |
| `ruch.mediana_jitter_pct` | number or null | Median `jitter_pct` over ALL seconds of the clip (no trim). | Used for the `static` class, because a median ignores a single broken second. |
| `ruch.p90_jitter_pct` | number or null | 90th percentile of `jitter_pct` over all seconds (no trim). | Reported, not used in classification. |
| `ruch.mediana_jitter_srodka_pct` | number or null | Median `jitter_pct` over the trimmed range. | Used (with the field below) to decide whether the middle is stable, for the `postawiona` class and for `ruch.brzegi`. A median is used instead of the mean or RMS because a real camera pickup slightly longer than the 2 s trim contaminates one edge second. |
| `ruch.mediana_ruch_srodka_pct` | number or null | Median `ruch_pct` over the trimmed range. | Same role as above. |
| `ruch.profil` | array of object | Per-second motion profile over the whole sampled range. | Empty array when the sample had fewer than 3 frames. |
| `ruch.profil[].t_s` | integer | Second index, counted from 0 s of the clip. | |
| `ruch.profil[].ruch_pct` | number or null | Intended motion for that second: mean of the absolute 0.5 s moving average of displacement, expressed as percent of frame width per second. | `null` when no pair in that second was confident. |
| `ruch.profil[].jitter_pct` | number or null | Shake for that second: RMS of the deviation of raw displacement from that same moving average, in percent of frame width. | `null` under the same condition. |
| `ruch.profil[].conf` | number | Mean RANSAC inlier ratio of the pairs in that second, 0-1. | An indicative confidence in that second's measurement. It does not enter the stability classification, but a second must have `conf >= 0.30` to be allowed to confirm an unstable edge (see `ruch.brzegi`). |
| `ruch.odcinki` | array of object | Adjacent seconds of the same stability type merged into runs. | A second is "stable" when `jitter_pct < jitter_stabilny_max` AND `ruch_pct < ruch_stabilny_max`; a second with no data counts as unstable. |
| `ruch.odcinki[].od_s` | integer | First second of the run, inclusive. | |
| `ruch.odcinki[].do_s` | integer | Last second of the run, inclusive. | A one-second run has `od_s` equal to `do_s`. |
| `ruch.odcinki[].typ` | string | `"stabilny"` (stable) or `"ruch"` (moving). | |
| `ruch.srodek` | object or null | The longest stable run: `{"od_s": int, "do_s": int}`. | `null` when no run came out stable. This is the DETECTED middle, distinct from the fixed trimmed range used for the aggregates above. |
| `ruch.brzegi` | object | Whether the clip starts or ends in motion (typical of putting the camera down or picking it up). | |
| `ruch.brzegi.poczatek_ruch` | boolean | `true` when every one of the first 2 seconds is confirmed unstable (beyond threshold AND `conf >= 0.30`) and the median middle is stable. | The confidence gate exists because a tracking breakdown (a hand over the lens) otherwise faked an unstable edge on a tripod shot. |
| `ruch.brzegi.koniec_ruch` | boolean | Same as above for the last 2 seconds. | |
| `ruch.pary_niepewne` | integer | Number of frame pairs rejected as unreliable. | Rejected means fewer than 12 tracked points, or a RANSAC inlier ratio below 30%. Compare against the total pair count (`okno_pomiaru.liczba_klatek_b` minus 1) to judge how much of the clip could be measured at all. |
| `ruch.klasa` | array of string | Shot class. | Exactly one of `postawiona` / `static` / `handheld` / `shaky` / `nieznana` (first match wins), with `pan` appended independently when intended motion exceeds `ruch_stabilny_max`. Definitions below. |
| `ruch.zrodlo` | string | Identifier of the method used. | `"lk_ransac_affine"` in v0.2. v0.1 reports carry a different value. |
| `ruch.obcieto_s` | number or null | `180.0` when the clip was longer than the 180 s cap and was truncated for the motion measurement, otherwise `null`. | Set by the caller, not by the motion function itself. |

Class definitions (`ruch.klasa`):

| value | condition |
|---|---|
| `postawiona` | The median middle is stable AND at least one edge is confirmed in motion. Literally "camera put down": a static shot bracketed by placing and picking up the camera. |
| `static` | The WHOLE clip (no trim, medians of both jitter and motion) is stable. |
| `handheld` | `jitter_rms_pct` (trimmed range) is below `jitter_shaky_min`. |
| `shaky` | `jitter_rms_pct` (trimmed range) is at or above `jitter_shaky_min`. Also raises the `trzesie` flag. |
| `nieznana` | No aggregate could be computed (too little usable data). |
| `pan` | Added on top of any of the above when `ruch_zamierzony_pct_s` exceeds `ruch_stabilny_max`. |

Rotation and scale are extracted from the affine matrix but are not used in
v0.2, so camera roll and zoom do not affect the class.

## `plynnosc` - cadence

Computed on sample B, which is sampled at 5 or 10 fps, NOT at the clip's native
frame rate. Duplicate detection therefore works at the sampling rate: it will
catch a freeze, but not a single duplicated frame in 50 fps footage.

| field | type | meaning | notes |
|---|---|---|---|
| `plynnosc.vfr` | boolean | `true` when `stream.fps` and `stream.fps_avg` differ. | A preliminary signal of a variable frame rate, not proof. A reliable check would look at the distribution of `pts_time`. |
| `plynnosc.duplikaty` | integer | Number of consecutive sample pairs whose mean absolute difference is below 0.002. | At the sampling rate, see the caveat above. |
| `plynnosc.tdiff` | number or null | Mean absolute difference between consecutive sample frames, on a 0-1 grayscale image. | `null` when there were fewer than 2 frames. A rough "how much is happening" number. |

## `montaz` - editing

| field | type | meaning | notes |
|---|---|---|---|
| `montaz.dlugosc_s` | number | Clip duration in seconds. | Same value as `zrodlo.czas_s`. |
| `montaz.segmenty` | array | Detected cuts inside the clip. | Always empty in this version - cut detection is not implemented. The field exists so the schema does not change when it is. |

## `klatki` - extracted frames

Array of objects, always two entries in this version.

| field | type | meaning | notes |
|---|---|---|---|
| `klatki[].rola` | string | `"pierwsza"` (the first frame of window A) or `"najostrzejsza"` (the frame with the highest Laplacian variance in window A). | |
| `klatki[].t_s` | number | Timestamp of that frame in the clip, in seconds. | For `pierwsza` this equals `okno_pomiaru.start_s`. |
| `klatki[].plik` | string | Path to the PNG, relative to `cache_root`, with forward slashes. | Written at 480 px wide; re-saved at 360 px if the PNG would exceed 500 KB. |

## `skopy` - scopes and charts

Array of objects, up to three entries.

| field | type | meaning | notes |
|---|---|---|---|
| `skopy[].typ` | string | `"waveform"`, `"vectorscope"` or `"przebieg"` (the clip profile chart). | |
| `skopy[].t_s` | number or null | Timestamp the scope was rendered from. | Equals the sharpest frame's timestamp for `waveform` and `vectorscope`; `null` for `przebieg`, which covers the whole clip. |
| `skopy[].plik` | string | Path to the PNG, relative to `cache_root`, with forward slashes. | |

The `przebieg` entry is appended only if the chart was actually drawn, which
requires `tonalnosc.profil` to be present. `eyes profile` can add it to an
existing report later, without re-measuring.

## `flagi_prowizoryczne` - provisional flags

Array of strings; empty when nothing fired. All thresholds are provisional (see
the next section).

| value | condition |
|---|---|
| `clip_hi>1%` | `tonalnosc.clip_hi_pct > clip_hi_pct_max` - more than 1% of pixels clipped to white. |
| `czern_mleczna` | `tonalnosc.p5 > p5_czern_mleczna_max` - "milky black", the floor is lifted. Normal for un-corrected log footage. |
| `czern_zabita` | `tonalnosc.p1 < p1_czern_zabita_max` AND `tonalnosc.clip_lo_pct > clip_lo_pct_czern_zabita_min` - "crushed black": both an extremely low p1 and a meaningful share of pixels at zero. |
| `nieostre` | `ostrosc.lapvar < lapvar_nieostre_max` - out of focus. Content-dependent, see the sharpness caveats. |
| `trzesie` | `"shaky"` is in `ruch.klasa` - shake in the trimmed middle, not at the edges. |

## `progi_prowizoryczne` - thresholds used

The exact values used for this measurement, copied into every report so a
report can be reinterpreted later. Defaults come from
`eyes/metrics.py:PROGI_PROWIZORYCZNE` and were hand-calibrated on three clips
with a human verdict attached, not on a diverse sample.

| field | type | meaning | notes |
|---|---|---|---|
| `progi_prowizoryczne.jitter_stabilny_max` | number | Below this `jitter_pct`, a second counts as stable. Default `0.4`. | Raised from 0.15 during calibration: at 0.15 an active subject inside an otherwise stable shot fragmented one long stable run into a dozen short ones. |
| `progi_prowizoryczne.ruch_stabilny_max` | number | Below this `ruch_pct`, a second counts as stable; above it at the aggregate level, `pan` is added. Default `3.0`. | Raised from 1.0 for the same reason. |
| `progi_prowizoryczne.jitter_shaky_min` | number | At or above this `jitter_rms_pct`, the class is `shaky` rather than `handheld`. Default `0.6`. | |
| `progi_prowizoryczne.clip_hi_pct_max` | number | Highlight clipping percentage above which the `clip_hi>1%` flag fires. Default `1.0`. | |
| `progi_prowizoryczne.p5_czern_mleczna_max` | number | `tonalnosc.p5` above which black is called milky. Default `0.06`. | |
| `progi_prowizoryczne.p1_czern_zabita_max` | number | `tonalnosc.p1` below which black may be called crushed. Default `0.005`. | Only fires together with the next threshold. |
| `progi_prowizoryczne.clip_lo_pct_czern_zabita_min` | number | `tonalnosc.clip_lo_pct` above which black may be called crushed. Default `2.0`. | |
| `progi_prowizoryczne.lapvar_nieostre_max` | number | `ostrosc.lapvar` below which the `nieostre` flag fires. Default `5.0`. | |

## `werdykty` - verdicts

| field | type | meaning | notes |
|---|---|---|---|
| `werdykty` | null | Slot for human judgement about the shot. | The measurement code always writes `null` here, by design: the automation flags and sorts, a person decides. The review page reads verdicts from a separate `werdykty.json` file, not from this field. |

## `niepewnosc` - uncertainty

Explicit statement of what could compromise this particular measurement.

| field | type | meaning | notes |
|---|---|---|---|
| `niepewnosc.pomiar_bez_lut` | boolean | `true` when a Fuji clip was measured with no LUT applied. | This matters: measuring raw F-Log means measuring the camera's curve, not the image. Tonality and color numbers from such a report are not comparable with LUT-corrected ones. |
| `niepewnosc.kamera_nieznana` | boolean | `true` when the filename did not match any known camera pattern. | Implies `zrodlo.profil` is `null` and no per-camera LUT could be selected. |
| `niepewnosc.gpu_fallback_cpu` | boolean | `true` when at least one ffmpeg call fell back from `-hwaccel cuda` to CPU decoding. | Affects speed, not the pixel result. |
| `niepewnosc.okno_krotsze_niz_zadane` | boolean | `true` when the clip was shorter than the requested window end, so less material was measured than asked for. | Expected for short clips: anything under 30 s is measured in full from 0. |

## `pomiar` - measurement provenance

| field | type | meaning | notes |
|---|---|---|---|
| `pomiar.data` | string | Timestamp of the measurement, ISO 8601 with local timezone offset. | |
| `pomiar.czas_dekodowania_s` | number | Seconds spent decoding both samples. | |
| `pomiar.czas_calkowity_s` | number | Total seconds for this clip: decoding plus all metrics, frame and scope writing. | Useful for estimating a batch: motion sampling over the whole clip dominates the cost on long clips. |
| `pomiar.gpu` | boolean | `true` when BOTH samples decoded with GPU acceleration. | See `niepewnosc.gpu_fallback_cpu` for the partial case. |
| `pomiar.ffmpeg` | string | ffmpeg version string, as reported by `ffmpeg -version`. | `"unknown"` when the call failed. |
| `pomiar.opencv` | string | OpenCV version used. | |
| `pomiar.host` | string | Machine label. | `platform.node()` - the OS-reported hostname of the machine that ran the measurement, not a fixed value. |

## Photos and assets

`python -m eyes photo` (photos/images) and `python -m eyes asset` (audio,
plus image and video dispatched per file) write the SAME top-level schema as
a clip - same keys, same order - so downstream code does not need a branch
per kind. The difference is `zrodlo.rodzaj` plus a few sections that are
either reshaped to a minimal placeholder or replaced with kind-specific data.
Everything not listed here (`werdykty`, `montaz.segmenty`, rounding, etc.)
behaves exactly as documented above. This part of the schema was added
2026-09-12 (still metrics version `"0.2"`).

### `zrodlo` additions

| field | type | meaning | notes |
|---|---|---|---|
| `zrodlo.rodzaj` | string | `"video"` \| `"photo"` \| `"image"` \| `"audio"`. | Absent (not `null` - the key itself is missing) on a clip report written by `eyes measure`/`eyes batch` with no `--rodzaj`, which means "video". `"photo"` is a `batch --rodzaj foto` or `eyes photo` shot; `"image"` is the same code path used for a plain image inside `batch --rodzaj assets` (EXIF is optional there, not required). |
| `zrodlo.plik_pomiaru` | string | Path of the file actually decoded. | Equals `zrodlo.plik`'s resolved path for a JPG/PNG/audio file. For a RAF with a JPG of the same name in the same folder, it points at that JPG. For a RAF with no JPG sibling, it is the RAF's own resolved path with `#embedded` appended (the pixel data came from the JPEG preview embedded in the RAF header, not from an on-disk JPEG). |
| `zrodlo.kamera` | string | For photo/image: EXIF `Model` when present (e.g. `"X-T4"`), else `"nieznana"`. For audio: always `"nieznana"`. | Not the `DSCF*.MOV`/`GX*.MP4` filename pattern used for video - a still image's filename does not carry that signal, EXIF does. |
| `zrodlo.profil`, `zrodlo.lut_pomiarowy` | null | Always `null` for photo/image/audio. | LUTs are a video/log-footage concept and do not apply here. |
| `zrodlo.czas_s` | number or null | `null` for photo/image; clip duration in seconds (from ffprobe) for audio. | |

### `stream`, `okno_pomiaru`, `ruch`, `plynnosc`, `montaz` for non-video

| field | photo/image | audio |
|---|---|---|
| `stream` | `codec` (e.g. `"jpeg"`), `w`, `h`, `pix_fmt` (e.g. `"rgb"`) filled in; `fps`, `fps_avg`, `range`, `transfer`, `primaries`, `nb_frames` all `null`. | `codec`, `sample_rate`, `channels`, `bits` filled in (from ffprobe; `bits` is `null` when the container does not declare it); everything else (including `w`/`h`/`pix_fmt`) `null`. |
| `okno_pomiaru` | `{"tryb": "still"}` - nothing else. | `{"tryb": "audio"}` - nothing else. |
| `ruch` | `{"klasa": [], "metoda": null}`. | Same. |
| `plynnosc` | `{}` (empty object). | Same. |
| `montaz` | `{"segmenty": []}` (no `dlugosc_s`). | Same. |

### `tonalnosc`, `kolor`, `ostrosc`, `szum` for photo/image

Computed with the exact same functions as video (`compute_tonalnosc` /
`compute_kolor` / `compute_ostrosc` / `compute_szum`), on a SINGLE frame: the
decoded image (EXIF orientation already applied via `ImageOps.exif_transpose`)
downscaled so its longer side is 960 px (never upscaled - a smaller source
keeps its native size). For audio all four are `null`.

| field | type | meaning | notes |
|---|---|---|---|
| `ostrosc.skala_pomiaru_px` | integer | `960` for photo/image. | `compute_ostrosc` itself always writes `480` (the video constant) - the photo/image code overwrites it with `960` afterward, since the working frame here is 960 px, not 480. Do not compare `ostrosc.lapvar` between a video report and a photo report - different scale. |
| `ostrosc.fokus_komorka` | integer, 0-8 | Index into `ostrosc.siatka_3x3` of the cell with the highest Laplacian variance, row-major from the top-left. | Not present on video reports. A center cell (index 4) several times above the others suggests a shallow-DOF subject centered in frame. |
| `tonalnosc.histogram_64` | array of 64 numbers | Luma (BT.709, same 0-1 scale as the rest of `tonalnosc`) histogram of the 960 px working frame, 64 equal-width bins over `[0, 1)`, normalized so the bins sum to 1. | Not present on video reports. Sums to `1.0` before the report's global 3-decimal rounding (`eyes/report.py:round_floats`); after rounding, expect the sum to land within a few thousandths of `1.0`, not exactly `1.0`. |

### `exif` - only photo/image

Read via Pillow `im.getexif()` (IFD0 tags) plus the Exif sub-IFD at tag
`0x8769` (`exif.get_ifd(0x8769)`) for everything camera-specific. An image
with no EXIF (a plain PNG, a screenshot) gets every field `null` - that is
not an error.

| field | type | meaning | notes |
|---|---|---|---|
| `exif.aparat` | string or null | Camera model (`Model`, tag `0x0110`). | |
| `exif.obiektyw` | string or null | Lens model (`LensModel`, tag `0xA434`). | |
| `exif.ogniskowa_mm` | number or null | Focal length in mm (`FocalLength`, tag `0x920A`). | |
| `exif.ogniskowa_35mm` | integer or null | 35 mm-equivalent focal length (`FocalLengthIn35mmFilm`, tag `0xA405`). | |
| `exif.przyslona` | number or null | Aperture, f-number (`FNumber`, tag `0x829D`). | |
| `exif.czas_naswietlania` | string or null | Human-readable shutter speed, e.g. `"1/400"` for sub-second, `"2s"` for one second or longer. | Derived from `czas_naswietlania_s`; the fraction is rounded to the nearest whole denominator. |
| `exif.czas_naswietlania_s` | number or null | Shutter speed in seconds (`ExposureTime`, tag `0x829A`). | |
| `exif.iso` | integer or null | ISO speed (`ISOSpeedRatings`, tag `0x8827`). | Feeds the `iso_wysokie` flag. |
| `exif.ev` | number or null | Exposure compensation (`ExposureBiasValue`, tag `0x9204`). | Can be negative. |
| `exif.wb` | string or null | White balance (`WhiteBalance`, tag `0xA403`): `"auto"` (tag value `0`) or `"reczny"` (tag value `1`, "manual"). | `null` for any other/absent tag value, not just a missing tag. |
| `exif.data` | string or null | Capture timestamp (`DateTimeOriginal`, tag `0x9003`), reformatted from EXIF's `"YYYY:MM:DD HH:MM:SS"` to `"YYYY-MM-DD HH:MM:SS"`. | |
| `exif.orientacja` | integer or null | Raw EXIF `Orientation` tag value (`0x0112`), 1-8, as it was BEFORE the pixel data was rotated/flipped to match it. | `kadr.w`/`kadr.h`/`kadr.orientacja` describe the image AFTER this orientation was applied to the pixels - they are consistent with what you see, not with this raw tag. |

### `kadr` - only photo/image

| field | type | meaning | notes |
|---|---|---|---|
| `kadr.w`, `kadr.h` | integer | Pixel dimensions after EXIF orientation is applied. | For a RAF measured from its embedded preview, these are the preview's dimensions (smaller than the sensor's raw output - e.g. 4416x2944 embedded vs. a larger true raw size on a Fujifilm X-T4). |
| `kadr.mpx` | number | Megapixels, `w * h / 1e6`, rounded to 1 decimal place. | Rounded to 1 decimal BEFORE the report's global 3-decimal rounding pass, so it always reads as one decimal digit (`26.0`, not `26.001`). |
| `kadr.proporcje` | string | Aspect ratio as a reduced fraction `"w:h"` (via `gcd`), e.g. `"3:2"`, `"2:3"`, `"16:9"`, `"1:1"`. | Not normalized to landscape - a portrait 3:2 shot reads `"2:3"`, not `"3:2"`. |
| `kadr.orientacja` | string | `"poziom"` (landscape, `w > h`), `"pion"` (portrait, `h > w`) or `"kwadrat"` (square). | |
| `kadr.entropia` | number | Shannon entropy of the 960 px working frame's luma, 8-bit histogram (256 bins), range 0-8. | Computed on the same downscaled frame as `tonalnosc`/`ostrosc`, not on the full-resolution image. |

### `warianty` - only photo/image

Describes files with the same stem that belong to the same shot - independent
of which one was actually decoded (`zrodlo.plik_pomiaru`).

Lookup order: first a sibling in the measured file's own folder, then - when
the measurement was started by `batch --rodzaj foto|assets`, or by
`photo`/`asset` with `--warianty-root FOLDER...` - anywhere under those
folders (scanned recursively once per run). Retouched `_IG` exports are
typically kept in their own folder rather than next to the camera JPG, so
without those roots `warianty.ig` stays `null`.

| field | type | meaning | notes |
|---|---|---|---|
| `warianty.jpg` | boolean | A `.jpg`/`.jpeg` with the same stem exists (sibling first, then the scanned roots). | `true` even when the JPG itself is the measured file. |
| `warianty.raf` | boolean | A `.raf` with the same stem exists (sibling first, then the scanned roots). | |
| `warianty.ig` | object or null | The `{stem}_IG.jpg`/`.jpeg` export, if present - usually found in a separate retouch folder via the scanned roots. | `{"plik", "w", "h", "proporcje", "rozmiar_b", "crop"}` - `crop` is `true` when the IG export's aspect ratio differs from `kadr.proporcje` (i.e. it was cropped for a platform, not just re-exported at the same framing). |
| `warianty.xmp` | object or null | The `{stem}.xmp` sidecar, if present. | `{"plik", "crs": {...}}` - `crs` is every `crs:*` setting found in the XMP, written either as an attribute (`crs:Exposure2012="+0.50"`, what Lightroom emits) or as a simple element (`<crs:Exposure2012>+0.50</crs:Exposure2012>`); nested lists such as `crs:ToneCurvePV2012` are skipped (Lightroom/ACR develop settings: exposure, tone curve sliders, crop, noise reduction, the active "Look" under the key `"Look"`, etc.), as floats where the value parses as a number, otherwise as the raw string (e.g. `crs:WhiteBalance="Custom"` stays the string `"Custom"`). This is every `crs:*` attribute present in the file, not a fixed subset - an XMP with more Lightroom sliders touched produces more keys. |

### `audio` - only audio

All values from ffmpeg/ffprobe on the file as a whole (no windowing, unlike
video's two-sample scheme).

| field | type | meaning | notes |
|---|---|---|---|
| `audio.czas_s` | number | Duration in seconds (ffprobe). | Same value as `zrodlo.czas_s` and `stream.czas_s`. |
| `audio.sample_rate` | integer or null | Sample rate in Hz. | |
| `audio.channels` | integer or null | Channel count. | |
| `audio.lufs_i` | number or null | Integrated loudness in LUFS (`ffmpeg -af ebur128=peak=true`, the "Integrated loudness / I:" line of the Summary block). | `null` if ffmpeg's ebur128 filter produced no Summary (e.g. a file too short to measure). |
| `audio.lra` | number or null | Loudness range in LU (ebur128 Summary "LRA:"). | |
| `audio.true_peak_dbtp` | number or null | True peak in dBTP (ebur128 Summary "Peak:", `peak=true` mode). | Feeds `glosno` and `klip`. |
| `audio.cisza_start_s` | number | Length in seconds of a silent run touching the very start of the file (`ffmpeg -af silencedetect=n=-50dB:d=0.3`), else `0`. | Not `null` when absent - `0` means "does not start in silence". |
| `audio.cisza_koniec_s` | number | Same as above, for a silent run touching the very end of the file. | |
| `audio.szczyt_rms_db` | number or null | Crest factor in dB: astats `Peak level dB` minus `RMS level dB`, from the `Overall` block of `ffmpeg -af astats`. | A high value means a spiky/dynamic signal relative to its average level; a value near 0 means the signal sits close to its own peak most of the time (heavily limited/compressed). |

### `klatki` and `skopy` for photo/image and audio

Entries here carry only `{"rola"/"typ", "plik"}` - no `t_s` timestamp (a
still image or a whole audio file has no single relevant instant).

| kind | `klatki` | `skopy` |
|---|---|---|
| photo/image | `pierwsza` and `najostrzejsza` both point at the same `{id}_podglad.jpg` (JPEG, longer side 1920 px, never upscaled); `kafel` points at `{id}_kafel.jpg` (longer side 640 px). | Four entries - `waveform`, `parade` (RGB parade, `waveform=mode=column:components=7`), `vectorscope`, `histogram` (`histogram=display_mode=stack`) - all rendered from the 1024 px `podglad`, files at `scopes/{id}_{typ}.png`. |
| audio | `pierwsza` and `najostrzejsza` both point at `{id}_fala.png` (`showwavespic`, 1600x400); `kafel` points at `{id}_kafel.png` (showwavespic, 640x160). | `[]` - no scopes for audio. |

### `flagi_prowizoryczne` and `progi_prowizoryczne` for photo/image

Separate threshold table (`eyes/cmd_photo.py:PROGI_FOTO`), not
`PROGI_PROWIZORYCZNE`. `clip_hi_pct_max`, `p5_czern_mleczna_max`,
`p1_czern_zabita_max` and `clip_lo_pct_czern_zabita_min` reuse the exact
video default values and flag logic (`clip_hi>1%`, `czern_mleczna`,
`czern_zabita`). Two extra flags exist only here:

| value | condition | notes |
|---|---|---|
| `nieostre` | `ostrosc.lapvar < lapvar_nieostre_max` (default `184.6`, at the 960 px scale). | Calibrated 2026-09-12 on the first 20 JPGs (by filename) of a single shooting-day folder: the lowest/highest `lapvar` extremes were visually checked and turned out to be low-texture/backlit content rather than genuinely out-of-focus shots (the same content-dependence caveat as video's `ostrosc.lapvar`, see above) - so the threshold falls back to the contract's rule for that case, one third of the sample median (median `553.9` -> `184.6`). Treat it as provisional, same spirit as `PROGI_PROWIZORYCZNE`. |
| `iso_wysokie` | `exif.iso > iso_wysokie_min` (default `3200`). | `false`/absent whenever `exif.iso` is `null` (no EXIF). |
| `szum` | `szum.sigma > sigma_szum_max` (default `0.02`). | This default was NOT calibrated against real photos (unlike `lapvar_nieostre_max`) - it is a working placeholder, flagged here so it is not mistaken for a measured value. |

### `flagi_prowizoryczne` and `progi_prowizoryczne` for audio

Separate table (`eyes/cmd_asset.py:PROGI_AUDIO`), taken directly from the
session contract, not independently calibrated.

| value | condition |
|---|---|
| `cicho` | `audio.lufs_i < cicho_lufs_max` (`-30.0`). |
| `glosno` | `audio.true_peak_dbtp > glosno_dbtp_min` (`-1.0`). |
| `klip` | `audio.true_peak_dbtp > klip_dbtp_min` (`0.0`). |
| `cisza_start` | `audio.cisza_start_s > cisza_start_s_min` (`1.0`). |
| `cisza_koniec` | `audio.cisza_koniec_s > cisza_koniec_s_min` (`2.0`). |

`glosno` and `klip` are independent checks, not mutually exclusive - a
clipped file (`klip`) is also over the `glosno` threshold and gets both flags.

### Formats with no decoder

HEIC and DNG (photo/image) have no decoder in this repo (Pillow has no
RAW/HEIF plugin installed, and `pip install` is off the table) - a file with
either extension is skipped with a log entry (`status: "pominieto"`,
`"powod": "brak_dekodera"` in `_log.jsonl`), not treated as an error and not
allowed to fail the rest of a batch. SVG is skipped the same way inside
`batch --rodzaj assets`, for the same reason (no rasterizer available).
