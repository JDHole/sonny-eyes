"""Przeglad HTML pomiarow percepcji: jedna strona z ceglami, liczbami, flagami i werdyktami Kuby.
Wywolywane przez `python -m eyes review` (eyes/cli.py) i przez alias `scripts/przeglad_html.py`.

Uzycie (venv):
  python -m eyes review --project "Canarian Tweety EP03" [--out-file sciezka.html]
Czyta: raporty {reports_root}/*.json (patrz eyes/config.py:Config.reports_dir),
       werdykty.json i probka_kalibracyjna_v0.json z color_dir sasiadujacego z reports_root,
       cegly i skopy z {cache_root}/{P}/{id}/.
Pisze: {cache_root}/{P}/_przeglad.html oraz --out-file (kopia do publikacji). Nic wiecej.
Obrazy wchodza do HTML jako data URI (strona ma dzialac bez dostepu do dysku).
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import html
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
from eyes.config import load_config, overrides_from_out  # noqa: E402
from eyes.i18n import FLAG_GLOSS_EN, t as tr  # noqa: E402

MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


def data_uri(path: Path, width: int | None = None, jpeg_q: int | None = None) -> str:
    """Obraz jako data URI. Gdy podano width/jpeg_q (tryb kompaktowy), skaluje i zapisuje jako JPEG
    (artefakt ma limit 16 MB, wiec przy setkach klipow pelne PNG sie nie mieszcza)."""
    if not path or not path.exists():
        return ""
    if width or jpeg_q:
        import io as _io
        from PIL import Image
        im = Image.open(path).convert("RGB")
        if width and im.width > width:
            im = im.resize((width, round(im.height * width / im.width)))
        buf = _io.BytesIO()
        im.save(buf, "JPEG", quality=jpeg_q or 78, optimize=True)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    b = path.read_bytes()
    return f"data:{MIME.get(path.suffix.lower(), 'application/octet-stream')};base64," + base64.b64encode(b).decode("ascii")


def load_json(path: Path, default):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def fmt(v, nd=3, suffix=""):
    if v is None:
        return "-"
    if isinstance(v, (int, float)):
        return f"{v:.{nd}f}{suffix}"
    return html.escape(str(v))


def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Przeglad HTML pomiarow percepcji (sonny-eyes)")
    ap.add_argument("--project", required=True)
    ap.add_argument("--out-file", default=None, help="kopia strony do publikacji (oprocz {cache_root}/{P}/_przeglad.html)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--config", default=None)
    ap.add_argument("--compact", action="store_true", help="male JPEG-i (cegla 320 px, przebieg 480 px, bez waveformu) pod limit artefaktu")
    ap.add_argument("--status", default=None, help="tekst 'Stan' na gorze strony (domyslnie: z pliku Color/_stan_przegladu.txt, jesli istnieje)")
    ap.add_argument("--lang", choices=["pl", "en"], default=None, help="jezyk strony (pl|en); domyslnie z configu/env, inaczej en")
    ap.add_argument("--cache-root", default=None, help=argparse.SUPPRESS)  # przestarzale: alias --out
    return ap.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)

    overrides = overrides_from_out(args.out or args.cache_root)
    if args.lang:
        overrides["lang"] = args.lang
    cfg = load_config(args.config, overrides=overrides)
    lang = cfg.lang
    cache_root = Path(cfg.cache_root)
    reports_dir = cfg.reports_dir(args.project)
    color_dir = cfg.color_dir(args.project)
    project_cache = cache_root / args.project

    werdykty = {w["src_id"]: w for w in load_json(color_dir / "werdykty.json", {"werdykty": []})["werdykty"]}
    probka = {k["src_id"]: k for k in load_json(color_dir / "probka_kalibracyjna_v0.json", {"klipy": []})["klipy"]}
    reports = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(reports_dir.glob("*.json"))]

    cards = []
    n_fuji = n_gopro = n_kuba = 0
    flag_counts: dict[str, int] = {}
    for r in reports:
        i = r["id"]
        z, t, o, m, k = r["zrodlo"], r["tonalnosc"], r["ostrosc"], r["ruch"], r.get("kolor", {})
        cam = z.get("kamera", "?")
        n_fuji += cam == "Fuji"
        n_gopro += cam == "GoPro"
        flags = r.get("flagi_prowizoryczne", []) or []
        for f in flags:
            flag_counts[f] = flag_counts.get(f, 0) + 1
        pr = probka.get(i, {})
        wk = werdykty.get(i)
        n_kuba += 1 if wk else 0
        if args.compact:
            cegla = data_uri(project_cache / i / "frames" / f"{i}_najostrzejsza.png", width=320, jpeg_q=75)
            wave = ""
            ruch_png = data_uri(project_cache / i / "scopes" / f"{i}_przebieg.png", width=480, jpeg_q=80)
        else:
            cegla = data_uri(project_cache / i / "frames" / f"{i}_najostrzejsza.png")
            wave = data_uri(project_cache / i / "scopes" / f"{i}_waveform.png")
            ruch_png = data_uri(project_cache / i / "scopes" / f"{i}_przebieg.png")
        klasa = "+".join(m.get("klasa", []) or [])
        jitter = m.get("jitter_rms_pct")
        wersja = str(r.get("wersja_metryk", ""))
        if m.get("mediana_jitter_srodka_pct") is not None:
            jitter_txt = f"{tr(lang, 'jitter_center')} {fmt(m.get('mediana_jitter_srodka_pct'), 2, '%')}"
            jitter_sort = m.get("mediana_jitter_srodka_pct") or 0
        else:
            jitter_txt = f"{tr(lang, 'jitter_word')} {fmt(jitter, 2, '%')}"
            jitter_sort = jitter or 0
        ver_html = (f'<span class="vwarn">v{html.escape(wersja)} {tr(lang, "unreliable")}</span>' if wersja == "0.1"
                    else f'<span class="vok">v{html.escape(wersja)}</span>')
        nazwa = pr.get("nazwa") or i

        def _flag_title(f: str) -> str:
            gloss = FLAG_GLOSS_EN.get(f) if lang == "en" else None
            return f' title="{html.escape(gloss)}"' if gloss else ""

        flags_html = "".join(
            f'<span class="chip chip-{"bad" if f.startswith("clip_hi") or f == "trzesie" else "warn"}"{_flag_title(f)}>{html.escape(f)}</span>'
            for f in flags
        ) or f'<span class="chip chip-ok">{tr(lang, "no_flags")}</span>'
        kuba_html = ""
        if wk:
            et = ", ".join(f"{a}: {b}" for a, b in (wk.get("etykiety") or {}).items())
            kuba_html = (f'<div class="verdict verdict-fresh"><div class="v-label">{tr(lang, "verdict_label")} &middot; {html.escape(wk.get("data", ""))}</div>'
                         f'<blockquote>{html.escape(wk.get("cytat", ""))}</blockquote>'
                         f'<div class="v-meta">{html.escape(et)}</div></div>')
        hist_html = ""
        if pr.get("werdykt"):
            hist_html = (f'<div class="verdict verdict-hist"><div class="v-label">{tr(lang, "hist_label")} &middot; {html.escape(pr.get("czyj", ""))} &middot; {html.escape(pr.get("o_czym", ""))}</div>'
                         f'<blockquote>{html.escape(pr["werdykt"])}</blockquote>'
                         f'<div class="v-meta">{html.escape(pr.get("zrodlo", ""))}</div></div>')
        note_html = f'<div class="note"><span class="v-label">Sonny:</span> {html.escape(pr["zgodnosc_v01"])}</div>' if pr.get("zgodnosc_v01") else ""
        srodek = m.get("srodek")
        srodek_txt = f' &middot; {tr(lang, "center_word")} {srodek["od_s"]}-{srodek["do_s"]} s' if isinstance(srodek, dict) and srodek else ""
        imgs = [("cegla", cegla, tr(lang, "img_thumb")), ("wave", wave, tr(lang, "img_wave"))]
        if ruch_png:
            imgs.append(("ruch", ruch_png, tr(lang, "img_profile")))
        img_btns = "".join(f'<button type="button" class="imgbtn{" active" if n == 0 else ""}" data-img="{key}">{lab}</button>' for n, (key, _, lab) in enumerate(imgs) if _)
        img_data = " ".join(f'data-{key}="{uri}"' for key, uri, _ in imgs if uri and key != "cegla")  # cegla jest juz w src
        cards.append(f"""
<article class="card" data-id="{html.escape(i)}" data-cam="{html.escape(cam)}" data-p5="{t.get('p5', 0)}" data-cliphi="{t.get('clip_hi_pct', 0)}" data-lapvar="{o.get('lapvar', 0)}" data-jitter="{jitter or 0}" data-flags="{html.escape(' '.join(flags))}" data-verdict="{1 if wk else 0}">
  <div class="thumb" {img_data}>
    <img src="{cegla}" alt="{tr(lang, 'thumb_alt')} {html.escape(i)}" loading="lazy">
    <div class="imgbar">{img_btns}</div>
  </div>
  <header class="slate">
    <div class="slate-id">{html.escape(i)}</div>
    <div class="slate-name">{html.escape(nazwa)}</div>
    <div class="slate-cam cam-{html.escape(cam.lower())}">{html.escape(cam)} &middot; {html.escape(str(z.get('profil') or '-'))} &middot; {fmt(z.get('czas_s'), 1, ' s')}</div>
  </header>
  <dl class="nums">
    <div><dt>{tr(lang, 'label_p5')}</dt><dd>{fmt(t.get('p5'))}</dd></div>
    <div><dt>{tr(lang, 'label_p50')}</dt><dd>{fmt(t.get('p50'))}</dd></div>
    <div><dt>{tr(lang, 'label_p99')}</dt><dd>{fmt(t.get('p99'))}</dd></div>
    <div><dt>{tr(lang, 'label_przepal')}</dt><dd>{fmt(t.get('clip_hi_pct'), 2, '%')}</dd></div>
    <div><dt>{tr(lang, 'label_ostrosc')}</dt><dd>{fmt(o.get('lapvar'), 0)}</dd></div>
    <div><dt>{tr(lang, 'label_nasycenie')}</dt><dd>{fmt(k.get('sat_mean'))}</dd></div>
    <div class="wide"><dt>{tr(lang, 'label_ruch')} {ver_html}</dt><dd>{html.escape(klasa or '-')} &middot; {jitter_txt}{srodek_txt}</dd></div>
  </dl>
  <div class="flags">{flags_html}</div>
  {kuba_html}{hist_html}{note_html}
</article>""")

    gen = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    stan_plik = color_dir / "_stan_przegladu.txt"
    status_txt = args.status or (stan_plik.read_text(encoding="utf-8").strip() if stan_plik.exists() else
                                 tr(lang, "status_default"))
    wersje = sorted({str(r.get("wersja_metryk")) for r in reports})

    def _flag_filter_title(f: str) -> str:
        gloss = FLAG_GLOSS_EN.get(f) if lang == "en" else None
        return f' title="{html.escape(gloss)}"' if gloss else ""

    flag_filters = "".join(
        f'<label class="chk"{_flag_filter_title(f)}><input type="checkbox" data-flag="{html.escape(f)}"> {html.escape(f)} <span class="cnt">{c}</span></label>'
        for f, c in sorted(flag_counts.items())
    )

    page = f"""<title>{tr(lang, 'app_title')}</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600&family=IBM+Plex+Sans:ital,wght@0,400;0,500;1,400&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root{{--bg:#141618;--surface:#1d2023;--surface2:#24282c;--line:#31363b;--ink:#e8e6df;--muted:#9a9c94;--accent:#c58048;--accent-ink:#141618;--ok:#6fb37a;--warn:#d9b24a;--bad:#d9605a;--wave:#9fd39f;--shadow:0 1px 0 rgba(255,255,255,.03) inset,0 8px 24px rgba(0,0,0,.35);color-scheme:dark}}
@media (prefers-color-scheme: light){{:root:not([data-theme="dark"]){{--bg:#eceef0;--surface:#ffffff;--surface2:#f4f5f6;--line:#d5d9dd;--ink:#1b1d20;--muted:#5c6066;--accent:#a8642f;--accent-ink:#ffffff;--ok:#2f8a4a;--warn:#a67c0a;--bad:#b83a34;--wave:#2f7a3a;--shadow:0 1px 2px rgba(0,0,0,.06),0 8px 24px rgba(20,30,40,.08);color-scheme:light}}}}
:root[data-theme="light"]{{--bg:#eceef0;--surface:#ffffff;--surface2:#f4f5f6;--line:#d5d9dd;--ink:#1b1d20;--muted:#5c6066;--accent:#a8642f;--accent-ink:#ffffff;--ok:#2f8a4a;--warn:#a67c0a;--bad:#b83a34;--wave:#2f7a3a;--shadow:0 1px 2px rgba(0,0,0,.06),0 8px 24px rgba(20,30,40,.08);color-scheme:light}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 "IBM Plex Sans",system-ui,Segoe UI,sans-serif}}
.wrap{{max-width:1480px;margin:0 auto;padding:28px 24px 64px}}
.top{{display:flex;flex-wrap:wrap;align-items:flex-end;justify-content:space-between;gap:16px 32px;border-bottom:2px solid var(--accent);padding-bottom:14px}}
.eyebrow{{font:500 12px/1 "IBM Plex Mono",ui-monospace,monospace;letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}}
h1{{font:600 44px/1 "Barlow Condensed","Arial Narrow",sans-serif;letter-spacing:.01em;margin:8px 0 0;text-wrap:balance}}
.stats{{display:flex;gap:22px;flex-wrap:wrap;font-family:"IBM Plex Mono",ui-monospace,monospace;font-variant-numeric:tabular-nums;font-size:13px;color:var(--muted)}}
.stats b{{color:var(--ink);font-weight:500;font-size:20px;display:block;line-height:1.1}}
.status{{margin:18px 0 0;padding:12px 16px;background:var(--surface);border-left:3px solid var(--accent);border-radius:4px;color:var(--ink);max-width:78ch}}
.status .eyebrow{{margin-bottom:6px}}
details.legend{{margin:16px 0 0;max-width:90ch}}
details.legend summary{{cursor:pointer;color:var(--accent);font-weight:500}}
details.legend dl{{display:grid;grid-template-columns:max-content 1fr;gap:6px 18px;margin:10px 0 0}}
details.legend dt{{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:13px;color:var(--muted);white-space:nowrap}}
details.legend dd{{margin:0;max-width:70ch}}
.controls{{display:flex;flex-wrap:wrap;gap:10px 18px;align-items:center;margin:22px 0 14px;padding:10px 12px;background:var(--surface);border:1px solid var(--line);border-radius:6px}}
.controls label{{color:var(--muted);font-size:13px}}
.controls select,.controls input[type=search]{{background:var(--surface2);color:var(--ink);border:1px solid var(--line);border-radius:4px;padding:6px 8px;font:inherit;font-size:13px}}
.chk{{display:inline-flex;align-items:center;gap:6px;font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:12px}}
.chk .cnt{{color:var(--muted)}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:18px}}
.card{{background:var(--surface);border:1px solid var(--line);border-radius:6px;box-shadow:var(--shadow);display:flex;flex-direction:column;overflow:hidden}}
.card[hidden]{{display:none}}
.thumb{{position:relative;aspect-ratio:16/9;background:#000}}
.thumb img{{width:100%;height:100%;object-fit:contain;display:block}}
.imgbar{{position:absolute;left:8px;bottom:8px;display:flex;gap:4px}}
.imgbtn{{font:500 11px/1 "IBM Plex Mono",ui-monospace,monospace;letter-spacing:.06em;text-transform:uppercase;padding:5px 8px;border-radius:3px;border:1px solid rgba(255,255,255,.25);background:rgba(0,0,0,.55);color:#e8e6df;cursor:pointer}}
.imgbtn.active{{background:var(--accent);border-color:var(--accent);color:var(--accent-ink)}}
.imgbtn:focus-visible{{outline:2px solid var(--accent);outline-offset:2px}}
.slate{{display:grid;grid-template-columns:auto 1fr;gap:2px 12px;align-items:baseline;padding:12px 14px 6px;border-bottom:1px dashed var(--line)}}
.slate-id{{font:600 24px/1 "Barlow Condensed","Arial Narrow",sans-serif;letter-spacing:.02em}}
.slate-name{{font-weight:500}}
.slate-cam{{grid-column:1/-1;font:400 12px/1.4 "IBM Plex Mono",ui-monospace,monospace;color:var(--muted)}}
.nums{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px 12px;margin:0;padding:10px 14px}}
.nums div{{min-width:0}}
.nums .wide{{grid-column:1/-1}}
.nums dt{{font:500 11px/1.2 "IBM Plex Mono",ui-monospace,monospace;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}}
.nums dd{{margin:2px 0 0;font:500 16px/1.2 "IBM Plex Mono",ui-monospace,monospace;font-variant-numeric:tabular-nums}}
.nums .wide dd{{font-size:14px}}
.nums dt span{{text-transform:none;letter-spacing:0;color:var(--warn)}}
.flags{{display:flex;flex-wrap:wrap;gap:6px;padding:0 14px 10px}}
.chip{{font:500 11px/1 "IBM Plex Mono",ui-monospace,monospace;padding:4px 7px;border-radius:3px;border:1px solid currentColor}}
.chip-bad{{color:var(--bad)}} .chip-warn{{color:var(--warn)}} .chip-ok{{color:var(--ok)}}
.verdict{{margin:0 14px 10px;padding:10px 12px;border-radius:4px;background:var(--surface2)}}
.verdict-fresh{{border-left:3px solid var(--accent)}}
.verdict-hist{{border-left:3px solid var(--line)}}
.v-label{{font:500 11px/1.3 "IBM Plex Mono",ui-monospace,monospace;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}}
.verdict blockquote{{margin:6px 0 4px;font-style:italic;font-size:14px;line-height:1.45}}
.v-meta{{font:400 11px/1.4 "IBM Plex Mono",ui-monospace,monospace;color:var(--muted);overflow-wrap:anywhere}}
.note{{margin:0 14px 14px;font-size:13px;color:var(--muted);line-height:1.45}}
.note .v-label{{display:inline}}
.empty{{padding:32px;text-align:center;color:var(--muted)}}
@media (prefers-reduced-motion:no-preference){{.imgbtn{{transition:background .15s}}}}
</style>
<div class="wrap">
  <div class="top">
    <div>
      <div class="eyebrow">{tr(lang, 'eyebrow_perception')} &middot; {html.escape(args.project)} &middot; {tr(lang, 'eyebrow_metrics')} v{html.escape("/".join(wersje))}</div>
      <h1>{tr(lang, 'app_title')}</h1>
    </div>
    <div class="stats">
      <div><b>{len(reports)}</b>{tr(lang, 'stat_measured')}</div>
      <div><b>{n_fuji}</b>Fuji</div>
      <div><b>{n_gopro}</b>GoPro</div>
      <div><b>{n_kuba}</b>{tr(lang, 'stat_verdict')}</div>
      <div><b>{gen}</b>{tr(lang, 'stat_generated')}</div>
    </div>
  </div>

  <div class="status">
    <div class="eyebrow">{tr(lang, 'status_label')}</div>
    {html.escape(status_txt)}
  </div>

  <details class="legend">
    <summary>{tr(lang, 'legend_summary')}</summary>
    <dl>
      <dt>{tr(lang, 'label_p5')}</dt><dd>{tr(lang, 'desc_p5')}</dd>
      <dt>{tr(lang, 'label_p50')}</dt><dd>{tr(lang, 'desc_p50')}</dd>
      <dt>{tr(lang, 'label_p99')}</dt><dd>{tr(lang, 'desc_p99')}</dd>
      <dt>{tr(lang, 'label_przepal')}</dt><dd>{tr(lang, 'desc_przepal')}</dd>
      <dt>{tr(lang, 'label_ostrosc')}</dt><dd>{tr(lang, 'desc_ostrosc')}</dd>
      <dt>{tr(lang, 'label_nasycenie')}</dt><dd>{tr(lang, 'desc_nasycenie')}</dd>
      <dt>{tr(lang, 'label_ruch')}</dt><dd>{tr(lang, 'desc_ruch')}</dd>
    </dl>
  </details>

  <div class="controls">
    <label>{tr(lang, 'sort_label')} <select id="sort">
      <option value="id">{tr(lang, 'sort_id')}</option>
      <option value="p5-asc">{tr(lang, 'sort_p5_asc')}</option>
      <option value="p5-desc">{tr(lang, 'sort_p5_desc')}</option>
      <option value="cliphi-desc">{tr(lang, 'sort_cliphi_desc')}</option>
      <option value="lapvar-desc">{tr(lang, 'sort_lapvar_desc')}</option>
      <option value="jitter-desc">{tr(lang, 'sort_jitter_desc')}</option>
    </select></label>
    <label>{tr(lang, 'camera_label')} <select id="cam"><option value="">{tr(lang, 'camera_all')}</option><option>Fuji</option><option>GoPro</option></select></label>
    <label class="chk"><input type="checkbox" id="onlyverdict"> {tr(lang, 'onlyverdict_label')}</label>
    {flag_filters}
    <label>{tr(lang, 'search_label')} <input type="search" id="q" placeholder="DSCF…" size="10"></label>
  </div>

  <section class="grid" id="grid">
    {''.join(cards)}
  </section>
  <p class="empty" id="empty" hidden>{tr(lang, 'empty_msg')}</p>
</div>
<script>
(function(){{
  var grid=document.getElementById('grid'), cards=Array.prototype.slice.call(grid.children);
  var sortSel=document.getElementById('sort'), camSel=document.getElementById('cam'), onlyVerdict=document.getElementById('onlyverdict'), q=document.getElementById('q');
  var flagBoxes=Array.prototype.slice.call(document.querySelectorAll('input[data-flag]'));
  function num(el,k){{return parseFloat(el.dataset[k]||'0')||0;}}
  function apply(){{
    var s=sortSel.value, cam=camSel.value, verdict=onlyVerdict.checked, needle=(q.value||'').trim().toLowerCase();
    var flags=flagBoxes.filter(function(b){{return b.checked;}}).map(function(b){{return b.dataset.flag;}});
    var sorted=cards.slice().sort(function(a,b){{
      if(s==='id') return a.dataset.id.localeCompare(b.dataset.id);
      var k=s.split('-')[0], dir=s.split('-')[1]==='asc'?1:-1;
      return (num(a,k)-num(b,k))*dir;
    }});
    var shown=0;
    sorted.forEach(function(c){{
      var ok=true;
      if(cam && c.dataset.cam!==cam) ok=false;
      if(verdict && c.dataset.verdict!=='1') ok=false;
      if(needle && c.dataset.id.toLowerCase().indexOf(needle)<0) ok=false;
      if(flags.length){{var f=(c.dataset.flags||'').split(' ');ok=ok&&flags.every(function(x){{return f.indexOf(x)>=0;}});}}
      c.hidden=!ok; if(ok) shown++;
      grid.appendChild(c);
    }});
    document.getElementById('empty').hidden=shown>0;
  }}
  [sortSel,camSel,onlyVerdict,q].concat(flagBoxes).forEach(function(el){{el.addEventListener('change',apply);el.addEventListener('input',apply);}});
  grid.addEventListener('click',function(e){{
    var btn=e.target.closest('.imgbtn'); if(!btn) return;
    var thumb=btn.closest('.thumb'), img0=thumb.querySelector('img');
    if(!thumb.dataset.cegla) thumb.dataset.cegla=img0.src;
    var key=btn.dataset.img, uri=thumb.dataset[key];
    if(!uri) return;
    thumb.querySelector('img').src=uri;
    thumb.querySelectorAll('.imgbtn').forEach(function(b){{b.classList.toggle('active',b===btn);}});
  }});
}})();
</script>
"""
    out_cache = project_cache / "_przeglad.html"
    out_cache.parent.mkdir(parents=True, exist_ok=True)
    out_cache.write_text(page, encoding="utf-8")
    outs = [out_cache]
    if args.out_file:
        op = Path(args.out_file)
        op.parent.mkdir(parents=True, exist_ok=True)
        op.write_text(page, encoding="utf-8")
        outs.append(op)
    for p in outs:
        print(f"{p}  ({p.stat().st_size/1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
