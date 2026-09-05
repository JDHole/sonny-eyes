"""Przeglad HTML pomiarow percepcji: jedna strona z ceglami, liczbami, flagami i werdyktami Kuby.

Uzycie (venv):
  scripts/przeglad_html.py --project "Canarian Tweety EP03" [--out sciezka.html]
Czyta: raporty {vault}/40_Pracownie/Analog Studio/Projekty/{P}/Color/reports/*.json,
       werdykty.json i probka_kalibracyjna_v0.json z tego samego Color/,
       cegly i skopy z {cache_root}/{P}/{id}/.
Pisze: {cache_root}/{P}/_przeglad.html oraz --out (kopia do publikacji). Nic wiecej.
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
from eyes.config import load_config  # noqa: E402

MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


def data_uri(path: Path) -> str:
    if not path or not path.exists():
        return ""
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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--vault", default=None)
    ap.add_argument("--cache-root", default=None)
    args = ap.parse_args(argv)

    cfg = load_config(REPO_ROOT / "config.toml", overrides={"vault": args.vault, "cache_root": args.cache_root})
    vault, cache_root = Path(cfg.vault), Path(cfg.cache_root)
    color_dir = vault / "40_Pracownie" / "Analog Studio" / "Projekty" / args.project / "Color"
    reports_dir = color_dir / "reports"
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
        cegla = data_uri(project_cache / i / "frames" / f"{i}_najostrzejsza.png")
        wave = data_uri(project_cache / i / "scopes" / f"{i}_waveform.png")
        ruch_png = data_uri(project_cache / i / "scopes" / f"{i}_przebieg.png")
        klasa = "+".join(m.get("klasa", []) or [])
        jitter = m.get("jitter_rms_pct")
        wersja = str(r.get("wersja_metryk", ""))
        if m.get("mediana_jitter_srodka_pct") is not None:
            jitter_txt = f"drganie środka (mediana) {fmt(m.get('mediana_jitter_srodka_pct'), 2, '%')}"
            jitter_sort = m.get("mediana_jitter_srodka_pct") or 0
        else:
            jitter_txt = f"jitter {fmt(jitter, 2, '%')}"
            jitter_sort = jitter or 0
        ver_html = f'<span class="vwarn">v{html.escape(wersja)} niewiarygodne</span>' if wersja == "0.1" else f'<span class="vok">v{html.escape(wersja)}</span>'
        nazwa = pr.get("nazwa") or i
        flags_html = "".join(f'<span class="chip chip-{"bad" if f.startswith("clip_hi") or f == "trzesie" else "warn"}">{html.escape(f)}</span>' for f in flags) or '<span class="chip chip-ok">bez flag</span>'
        kuba_html = ""
        if wk:
            et = ", ".join(f"{a}: {b}" for a, b in (wk.get("etykiety") or {}).items())
            kuba_html = (f'<div class="verdict verdict-fresh"><div class="v-label">Werdykt Kuby &middot; {html.escape(wk.get("data", ""))}</div>'
                         f'<blockquote>{html.escape(wk.get("cytat", ""))}</blockquote>'
                         f'<div class="v-meta">{html.escape(et)}</div></div>')
        hist_html = ""
        if pr.get("werdykt"):
            hist_html = (f'<div class="verdict verdict-hist"><div class="v-label">Z logów &middot; {html.escape(pr.get("czyj", ""))} &middot; {html.escape(pr.get("o_czym", ""))}</div>'
                         f'<blockquote>{html.escape(pr["werdykt"])}</blockquote>'
                         f'<div class="v-meta">{html.escape(pr.get("zrodlo", ""))}</div></div>')
        note_html = f'<div class="note"><span class="v-label">Sonny:</span> {html.escape(pr["zgodnosc_v01"])}</div>' if pr.get("zgodnosc_v01") else ""
        srodek = m.get("srodek")
        srodek_txt = f' &middot; środek {srodek["od_s"]}-{srodek["do_s"]} s' if isinstance(srodek, dict) and srodek else ""
        imgs = [("cegla", cegla, "cegła"), ("wave", wave, "waveform")]
        if ruch_png:
            imgs.append(("ruch", ruch_png, "przebieg"))
        img_btns = "".join(f'<button type="button" class="imgbtn{" active" if n == 0 else ""}" data-img="{key}">{lab}</button>' for n, (key, _, lab) in enumerate(imgs) if _)
        img_data = " ".join(f'data-{key}="{uri}"' for key, uri, _ in imgs if uri and key != "cegla")  # cegla jest juz w src
        cards.append(f"""
<article class="card" data-id="{html.escape(i)}" data-cam="{html.escape(cam)}" data-p5="{t.get('p5', 0)}" data-cliphi="{t.get('clip_hi_pct', 0)}" data-lapvar="{o.get('lapvar', 0)}" data-jitter="{jitter or 0}" data-flags="{html.escape(' '.join(flags))}" data-kuba="{1 if wk else 0}">
  <div class="thumb" {img_data}>
    <img src="{cegla}" alt="najostrzejsza klatka {html.escape(i)}" loading="lazy">
    <div class="imgbar">{img_btns}</div>
  </div>
  <header class="slate">
    <div class="slate-id">{html.escape(i)}</div>
    <div class="slate-name">{html.escape(nazwa)}</div>
    <div class="slate-cam cam-{html.escape(cam.lower())}">{html.escape(cam)} &middot; {html.escape(str(z.get('profil') or '-'))} &middot; {fmt(z.get('czas_s'), 1, ' s')}</div>
  </header>
  <dl class="nums">
    <div><dt>czerń p5</dt><dd>{fmt(t.get('p5'))}</dd></div>
    <div><dt>środek p50</dt><dd>{fmt(t.get('p50'))}</dd></div>
    <div><dt>światła p99</dt><dd>{fmt(t.get('p99'))}</dd></div>
    <div><dt>przepał</dt><dd>{fmt(t.get('clip_hi_pct'), 2, '%')}</dd></div>
    <div><dt>ostrość</dt><dd>{fmt(o.get('lapvar'), 0)}</dd></div>
    <div><dt>nasycenie</dt><dd>{fmt(k.get('sat_mean'))}</dd></div>
    <div class="wide"><dt>ruch {ver_html}</dt><dd>{html.escape(klasa or '-')} &middot; {jitter_txt}{srodek_txt}</dd></div>
  </dl>
  <div class="flags">{flags_html}</div>
  {kuba_html}{hist_html}{note_html}
</article>""")

    gen = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    wersje = sorted({str(r.get("wersja_metryk")) for r in reports})
    flag_filters = "".join(f'<label class="chk"><input type="checkbox" data-flag="{html.escape(f)}"> {html.escape(f)} <span class="cnt">{c}</span></label>' for f, c in sorted(flag_counts.items()))

    page = f"""<title>Oczy Sonny'ego</title>
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
      <div class="eyebrow">Percepcja materiału &middot; {html.escape(args.project)} &middot; metryki v{html.escape("/".join(wersje))}</div>
      <h1>Oczy Sonny'ego</h1>
    </div>
    <div class="stats">
      <div><b>{len(reports)}</b>klipów zmierzonych</div>
      <div><b>{n_fuji}</b>Fuji</div>
      <div><b>{n_gopro}</b>GoPro</div>
      <div><b>{n_kuba}</b>ze świeżym werdyktem Kuby</div>
      <div><b>{gen}</b>wygenerowano</div>
    </div>
  </div>

  <div class="status">
    <div class="eyebrow">Stan weekendu</div>
    Blok 2 zamknięty: repo, venv, pomiar v0.1 na trzech klipach, bramki zielone. Blok 3 w toku: 13 klipów próbki kalibracyjnej zmierzonych, czekam na Twoje oko. Metryka ruchu v0.1 jest niewiarygodna (liczyła pierwsze 5 s klipu), v0.2 w robocie. Czerń i przepał są wiarygodne.
  </div>

  <details class="legend">
    <summary>Jak czytać liczby</summary>
    <dl>
      <dt>czerń p5</dt><dd>Jasność (0 czarne, 1 białe), poniżej której leży 5% najciemniejszych pikseli. Robocze progi z lipca: 0.02 do 0.04 osadzona, powyżej 0.06 mleczna. Scena jasna z natury (high-key) nie ma czerni i to nie jest błąd.</dd>
      <dt>środek p50</dt><dd>Mediana jasności kadru.</dd>
      <dt>światła p99</dt><dd>Jasność, powyżej której leży 1% najjaśniejszych pikseli.</dd>
      <dt>przepał</dt><dd>Procent pikseli wypalonych do białego. Roboczy próg: powyżej 1% flaga.</dd>
      <dt>ostrość</dt><dd>Ile drobnych krawędzi i faktury w klatce. Zależy od treści: gąszcz liści da tysiące, mgła i gładkie niebo kilkaset, choć są ostre. Dobra do porównań w jednej scenie.</dd>
      <dt>nasycenie</dt><dd>Średnie nasycenie koloru po LUT (0 szare, 1 maksymalne).</dd>
      <dt>ruch</dt><dd>Klasa (statyw / ręka / trzęsie, plus pan) i jitter: o ile kadr drga z klatki na klatkę w procentach szerokości. W v0.1 liczone tylko z pierwszych 5 s klipu, więc traktuj jako podpowiedź. v0.2 liczy cały klip i pokazuje odcinki stabilne.</dd>
    </dl>
  </details>

  <div class="controls">
    <label>Sortuj <select id="sort">
      <option value="id">po numerze</option>
      <option value="p5-asc">czerń p5 rosnąco</option>
      <option value="p5-desc">czerń p5 malejąco</option>
      <option value="cliphi-desc">przepał malejąco</option>
      <option value="lapvar-desc">ostrość malejąco</option>
      <option value="jitter-desc">jitter malejąco</option>
    </select></label>
    <label>Kamera <select id="cam"><option value="">wszystkie</option><option>Fuji</option><option>GoPro</option></select></label>
    <label class="chk"><input type="checkbox" id="onlykuba"> tylko z werdyktem Kuby</label>
    {flag_filters}
    <label>Szukaj <input type="search" id="q" placeholder="DSCF…" size="10"></label>
  </div>

  <section class="grid" id="grid">
    {''.join(cards)}
  </section>
  <p class="empty" id="empty" hidden>Nic nie pasuje do filtrów.</p>
</div>
<script>
(function(){{
  var grid=document.getElementById('grid'), cards=Array.prototype.slice.call(grid.children);
  var sortSel=document.getElementById('sort'), camSel=document.getElementById('cam'), onlyKuba=document.getElementById('onlykuba'), q=document.getElementById('q');
  var flagBoxes=Array.prototype.slice.call(document.querySelectorAll('input[data-flag]'));
  function num(el,k){{return parseFloat(el.dataset[k]||'0')||0;}}
  function apply(){{
    var s=sortSel.value, cam=camSel.value, kuba=onlyKuba.checked, needle=(q.value||'').trim().toLowerCase();
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
      if(kuba && c.dataset.kuba!=='1') ok=false;
      if(needle && c.dataset.id.toLowerCase().indexOf(needle)<0) ok=false;
      if(flags.length){{var f=(c.dataset.flags||'').split(' ');ok=ok&&flags.every(function(x){{return f.indexOf(x)>=0;}});}}
      c.hidden=!ok; if(ok) shown++;
      grid.appendChild(c);
    }});
    document.getElementById('empty').hidden=shown>0;
  }}
  [sortSel,camSel,onlyKuba,q].concat(flagBoxes).forEach(function(el){{el.addEventListener('change',apply);el.addEventListener('input',apply);}});
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
    if args.out:
        op = Path(args.out)
        op.parent.mkdir(parents=True, exist_ok=True)
        op.write_text(page, encoding="utf-8")
        outs.append(op)
    for p in outs:
        print(f"{p}  ({p.stat().st_size/1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
