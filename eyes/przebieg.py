"""Obrazek 'przebieg ujecia' (v0.2): jasnosc + jitter + ruch zamierzony w
czasie, jeden PNG 960x540 na klip. Wylacznie z danych JUZ policzonych w
raporcie (tonalnosc.profil, ruch.profil/odcinki/srodek, progi_prowizoryczne)
- brak ponownego dekodowania/pomiaru tutaj.

Trzy panele jeden pod drugim, wspolna os X (sekundy). Paleta i uklad sa
CELOWO ograniczone (patrz stale kolorow nizej) - nie dodawaj innych kolorow
bez zmiany specyfikacji.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib import transforms  # noqa: E402
from matplotlib.collections import LineCollection  # noqa: E402

# --- paleta (WYLACZNIE te kolory - zwalidowana dla ciemnego tla) ---
TLO = "#1a1a19"
SIATKA = "#2c2c2a"
OS = "#383835"
GLOWNY = "#ffffff"          # tylko naglowek
DRUGORZEDNY = "#c3c2b7"     # tytuly panelu, etykiety, legenda
WYCISZONY = "#898781"       # ticki, progi

KOLOR_P5 = "#3987e5"
KOLOR_P50 = "#d95926"
KOLOR_P99 = "#199e70"
KOLOR_SERIA = "#3987e5"     # panel 2 i 3 (jedna seria kazdy)

PAS_ALPHA_ZWYKLY = 0.10
PAS_ALPHA_SRODEK = 0.18
PROG_LINESTYLE = (0, (4, 3))
PROG_LINEWIDTH = 0.9
NIEPEWNE_ALPHA = 0.35

FIG_W_IN, FIG_H_IN, DPI = 9.6, 5.4, 100

plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["Segoe UI", "DejaVu Sans"]


def _fmt_czas(czas_s: float) -> str:
    txt = f"{czas_s:.1f}"
    if txt.endswith(".0"):
        txt = txt[:-2]
    return txt


def _stylizuj_panel(ax) -> None:
    ax.set_facecolor(TLO)
    ax.grid(axis="y", color=SIATKA, linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["bottom"].set_color(OS)
    ax.spines["left"].set_color(OS)
    ax.tick_params(colors=WYCISZONY, labelsize=8, length=3)


def _rysuj_pasy_stabilne(ax, odcinki: list[dict], srodek: dict | None) -> None:
    for o in odcinki or []:
        if o.get("typ") != "stabilny":
            continue
        od_s, do_s = o.get("od_s"), o.get("do_s")
        if od_s is None or do_s is None:
            continue
        jest_srodkiem = (
            srodek is not None and od_s == srodek.get("od_s") and do_s == srodek.get("do_s")
        )
        alpha = PAS_ALPHA_SRODEK if jest_srodkiem else PAS_ALPHA_ZWYKLY
        ax.axvspan(od_s, do_s + 1, color=DRUGORZEDNY, alpha=alpha, lw=0, zorder=1)


def _etykieta_konca_linii(ax, x_ost: float, y_ost: float, kolor: str, tekst: str) -> None:
    if x_ost is None or y_ost is None or not np.isfinite(y_ost):
        return
    ax.annotate(
        "", xy=(x_ost, y_ost), xytext=(14, 0), textcoords="offset points",
        arrowprops=dict(arrowstyle="-", color=kolor, linewidth=2, shrinkA=0, shrinkB=0),
        annotation_clip=False, zorder=6,
    )
    ax.annotate(
        tekst, xy=(x_ost, y_ost), xytext=(19, 0), textcoords="offset points",
        va="center", ha="left", color=DRUGORZEDNY, fontsize=8,
        annotation_clip=False, zorder=6,
    )


def _prog_poziomy(ax, wartosc: float | None, etykieta: str) -> None:
    if wartosc is None:
        return
    ax.axhline(wartosc, color=WYCISZONY, linewidth=PROG_LINEWIDTH, linestyle=PROG_LINESTYLE, zorder=2)
    blended = transforms.blended_transform_factory(ax.transAxes, ax.transData)
    ax.text(
        1.012, wartosc, etykieta, transform=blended, color=WYCISZONY, fontsize=8,
        va="center", ha="left", clip_on=False, zorder=6,
    )


def _seria_z_pewnoscia(ax, t_s: list[int], wartosci: list, conf: list, kolor: str, domyslny_top: float) -> None:
    """Linia 2px z gapami (None -> NaN) - segmenty dotykajace sekundy o
    conf < 0.3 rysowane sciszone (alpha 0.35), zeby niepewny tracking nie
    wygladal jak fakt. Os Y 0..max(domyslny_top, p95*1.2), z przycieciem
    wartosci powyzej i etykieta '(uparrow) poza skale' jesli cos przycieto."""
    t = np.asarray(t_s, dtype=float)
    y = np.array([np.nan if v is None else float(v) for v in wartosci], dtype=float)
    c = np.array([0.0 if v is None else float(v) for v in conf], dtype=float)

    valid = np.isfinite(y)
    p95 = float(np.percentile(y[valid], 95)) if valid.any() else 0.0
    top = max(domyslny_top, p95 * 1.2)
    ax.set_ylim(0, top)

    przycieto = bool(valid.any() and np.nanmax(y) > top)

    if len(t) >= 2:
        pts = np.stack([t, y], axis=1)
        segmenty = np.stack([pts[:-1], pts[1:]], axis=1)
        ok = np.isfinite(segmenty[:, 0, 1]) & np.isfinite(segmenty[:, 1, 1])
        sciszone = (c[:-1] < 0.3) | (c[1:] < 0.3)
        segmenty, sciszone = segmenty[ok], sciszone[ok]
        if len(segmenty):
            kolory = [(*matplotlib.colors.to_rgb(kolor), NIEPEWNE_ALPHA if s else 1.0) for s in sciszone]
            lc = LineCollection(segmenty, colors=kolory, linewidths=2, capstyle="round", zorder=3)
            ax.add_collection(lc)
    elif len(t) == 1 and np.isfinite(y[0]):
        alpha = NIEPEWNE_ALPHA if c[0] < 0.3 else 1.0
        ax.plot(t, y, color=kolor, linewidth=2, alpha=alpha, marker="o", markersize=3, zorder=3)

    if przycieto:
        ax.annotate(
            "↑ poza skalę", xy=(0.99, 0.94), xycoords="axes fraction",
            ha="right", va="top", color=WYCISZONY, fontsize=8, zorder=6,
        )


def render_przebieg(report: dict, out_path: Path) -> Path | None:
    """Rysuje PNG 960x540 'przebieg ujecia' z danych JUZ obecnych w `report`.
    Zwraca `out_path` gdy narysowano, `None` (i nic nie zapisuje) gdy w
    raporcie brakuje `tonalnosc.profil` (stare raporty sprzed tej funkcji)."""
    profil_jasnosci = (report.get("tonalnosc") or {}).get("profil")
    if not profil_jasnosci:
        return None

    ruch = report.get("ruch") or {}
    ruch_profil = ruch.get("profil") or []
    odcinki = ruch.get("odcinki") or []
    srodek = ruch.get("srodek")
    progi = report.get("progi_prowizoryczne") or {}
    prog_jitter = progi.get("jitter_stabilny_max")
    prog_ruch = progi.get("ruch_stabilny_max")

    zrodlo = report.get("zrodlo") or {}
    id_ = report.get("id", "?")
    kamera = zrodlo.get("kamera", "?")
    czas_s = zrodlo.get("czas_s")
    if czas_s is None:
        maks_t = [p["t_s"] for p in profil_jasnosci] + [p["t_s"] for p in ruch_profil]
        czas_s = (max(maks_t) + 1) if maks_t else 1.0
    czas_s = float(czas_s)

    fig = plt.figure(figsize=(FIG_W_IN, FIG_H_IN), dpi=DPI)
    fig.patch.set_facecolor(TLO)

    gs = fig.add_gridspec(
        3, 1, height_ratios=[45, 27, 28],
        left=0.065, right=0.86, top=0.88, bottom=0.10, hspace=0.32,
    )
    ax1 = fig.add_subplot(gs[0])
    ax2 = fig.add_subplot(gs[1], sharex=ax1)
    ax3 = fig.add_subplot(gs[2], sharex=ax1)

    for ax in (ax1, ax2, ax3):
        _stylizuj_panel(ax)
        _rysuj_pasy_stabilne(ax, odcinki, srodek)
    ax1.tick_params(labelbottom=False)
    ax2.tick_params(labelbottom=False)
    ax3.set_xlabel("sekundy", color=DRUGORZEDNY, fontsize=8, labelpad=4)

    if srodek is not None:
        cx = (srodek["od_s"] + srodek["do_s"] + 1) / 2.0
        blended2 = transforms.blended_transform_factory(ax2.transData, ax2.transAxes)
        ax2.text(
            cx, 0.90, "stabilny", transform=blended2, ha="center", va="top",
            color=DRUGORZEDNY, fontsize=8, zorder=6,
        )

    # --- panel 1: jasnosc po LUT ---
    ax1.set_title(
        "jasność po LUT · p5 czerń · p50 środek · p99 światła",
        loc="left", color=DRUGORZEDNY, fontsize=9, pad=8,
    )
    t1 = [p["t_s"] for p in profil_jasnosci]
    for klucz, kolor, etykieta in (("p5", KOLOR_P5, "p5"), ("p50", KOLOR_P50, "p50"), ("p99", KOLOR_P99, "p99")):
        ys = [p[klucz] for p in profil_jasnosci]
        ax1.plot(t1, ys, color=kolor, linewidth=2, label=etykieta, zorder=3, solid_capstyle="round")
        _etykieta_konca_linii(ax1, t1[-1], ys[-1], kolor, etykieta)
    ax1.set_ylim(0, 1)
    legenda = ax1.legend(
        loc="upper right", frameon=True, fontsize=8, labelcolor=DRUGORZEDNY,
        handlelength=1.3, handletextpad=0.5, borderaxespad=0.5, labelspacing=0.3,
        borderpad=0.4,
    )
    legenda.get_frame().set_facecolor(TLO)
    legenda.get_frame().set_edgecolor(TLO)
    legenda.get_frame().set_alpha(0.8)

    # --- panel 2: jitter ---
    ax2.set_title("drganie (jitter, % szerokości kadru)", loc="left", color=DRUGORZEDNY, fontsize=9, pad=8)
    t2 = [p["t_s"] for p in ruch_profil]
    _seria_z_pewnoscia(
        ax2, t2, [p["jitter_pct"] for p in ruch_profil], [p["conf"] for p in ruch_profil],
        KOLOR_SERIA, domyslny_top=1.0,
    )
    _prog_poziomy(ax2, prog_jitter, "próg stabilności")

    # --- panel 3: ruch zamierzony ---
    ax3.set_title("ruch zamierzony (% szerokości kadru na s)", loc="left", color=DRUGORZEDNY, fontsize=9, pad=8)
    t3 = [p["t_s"] for p in ruch_profil]
    _seria_z_pewnoscia(
        ax3, t3, [p["ruch_pct"] for p in ruch_profil], [p["conf"] for p in ruch_profil],
        KOLOR_SERIA, domyslny_top=5.0,
    )
    _prog_poziomy(ax3, prog_ruch, "próg stabilności")

    for ax in (ax1, ax2, ax3):
        ax.set_xlim(0, czas_s)

    naglowek = f"{id_} · {kamera} · {_fmt_czas(czas_s)} s · przebieg ujęcia v0.2"
    fig.text(0.018, 0.975, naglowek, color=GLOWNY, fontsize=9, ha="left", va="top")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=DPI, facecolor=fig.get_facecolor())
    plt.close(fig)
    return out_path
