"""Slownik napisow interfejsu (PL/EN) dla strony przegladu (cmd_review.py) i
wykresu przebiegu (przebieg.py). SSOT dla i18n - obie strony czytaja stad,
zeby nie duplikowac tlumaczen i nie rozjezdzac ich w czasie.

Jezyk (lang) to zawsze "pl" albo "en" - patrz eyes/config.py:load_config,
kolejnosc nadpisan: CLI (--lang) > EYES_LANG > config.toml[lang] > "en".

Wartosci z raportu (nazwy flag typu "czern_mleczna", klasy ruchu typu
"shaky"/"postawiona") NIE sa tlumaczone - to identyfikatory danych, nie tekst
interfejsu. W wersji en dla flag dokladamy krotkie tlumaczenie w tooltipie -
patrz FLAG_GLOSS_EN nizej.
"""
from __future__ import annotations

LANGS = ("pl", "en")

STRINGS: dict[str, dict[str, str]] = {
    "pl": {
        "app_title": "Oczy Sonny'ego",
        "eyebrow_perception": "Percepcja materiału",
        "eyebrow_metrics": "metryki",
        "stat_measured": "klipów zmierzonych",
        "stat_verdict": "ze świeżym werdyktem",
        "stat_generated": "wygenerowano",
        "status_label": "Stan",
        "status_default": (
            "Progi flag są prowizoryczne (do kalibracji na werdyktach). "
            "Czerń i przepał wiarygodne; ruch v0.2 liczony z całego klipu."
        ),
        "legend_summary": "Jak czytać liczby",
        "label_p5": "czerń p5",
        "label_p50": "środek p50",
        "label_p99": "światła p99",
        "label_przepal": "przepał",
        "label_ostrosc": "ostrość",
        "label_nasycenie": "nasycenie",
        "label_ruch": "ruch",
        "desc_p5": (
            "Jasność (0 czarne, 1 białe), poniżej której leży 5% najciemniejszych "
            "pikseli. Robocze progi z lipca: 0.02 do 0.04 osadzona, powyżej 0.06 "
            "mleczna. Scena jasna z natury (high-key) nie ma czerni i to nie jest błąd."
        ),
        "desc_p50": "Mediana jasności kadru.",
        "desc_p99": "Jasność, powyżej której leży 1% najjaśniejszych pikseli.",
        "desc_przepal": "Procent pikseli wypalonych do białego. Roboczy próg: powyżej 1% flaga.",
        "desc_ostrosc": (
            "Ile drobnych krawędzi i faktury w klatce. Zależy od treści: gąszcz "
            "liści da tysiące, mgła i gładkie niebo kilkaset, choć są ostre. Dobra "
            "do porównań w jednej scenie."
        ),
        "desc_nasycenie": "Średnie nasycenie koloru po LUT (0 szare, 1 maksymalne).",
        "desc_ruch": (
            "Klasa (statyw / ręka / trzęsie, plus pan) i jitter: o ile kadr drga z "
            "klatki na klatkę w procentach szerokości. W v0.1 liczone tylko z "
            "pierwszych 5 s klipu, więc traktuj jako podpowiedź. v0.2 liczy cały "
            "klip i pokazuje odcinki stabilne."
        ),
        "sort_label": "Sortuj",
        "sort_id": "po numerze",
        "sort_p5_asc": "czerń p5 rosnąco",
        "sort_p5_desc": "czerń p5 malejąco",
        "sort_cliphi_desc": "przepał malejąco",
        "sort_lapvar_desc": "ostrość malejąco",
        "sort_jitter_desc": "jitter malejąco",
        "camera_label": "Kamera",
        "camera_all": "wszystkie",
        "onlyverdict_label": "tylko z werdyktem",
        "search_label": "Szukaj",
        "empty_msg": "Nic nie pasuje do filtrów.",
        "verdict_label": "Werdykt",
        "hist_label": "Z logów",
        "no_flags": "bez flag",
        "unreliable": "niewiarygodne",
        "thumb_alt": "najostrzejsza klatka",
        "img_thumb": "cegła",
        "img_wave": "waveform",
        "img_profile": "przebieg",
        "jitter_center": "drganie środka (mediana)",
        "center_word": "środek",
        "jitter_word": "jitter",
        # --- eyes/przebieg.py ---
        "przebieg_panel1_title": "jasność po LUT · p5 czerń · p50 środek · p99 światła",
        "przebieg_panel2_title": "drganie (jitter, % szerokości kadru)",
        "przebieg_panel3_title": "ruch zamierzony (% szerokości kadru na s)",
        "przebieg_xlabel": "sekundy",
        "przebieg_stable": "stabilny",
        "przebieg_threshold": "próg stabilności",
        "przebieg_offscale": "↑ poza skalę",
        "przebieg_header_suffix": "przebieg ujęcia v0.2",
    },
    "en": {
        "app_title": "sonny-eyes",
        "eyebrow_perception": "Perception report",
        "eyebrow_metrics": "metrics",
        "stat_measured": "clips measured",
        "stat_verdict": "with fresh verdict",
        "stat_generated": "generated",
        "status_label": "Status",
        "status_default": (
            "Flag thresholds are provisional (to be calibrated against verdicts). "
            "Blacks and highlight clipping are reliable; motion v0.2 is computed "
            "from the whole clip."
        ),
        "legend_summary": "How to read the numbers",
        "label_p5": "black p5",
        "label_p50": "midtone p50",
        "label_p99": "highlights p99",
        "label_przepal": "clipping",
        "label_ostrosc": "sharpness",
        "label_nasycenie": "saturation",
        "label_ruch": "motion",
        "desc_p5": (
            "Brightness (0 black, 1 white) below which lie the 5% darkest pixels. "
            "Working thresholds from July: 0.02 to 0.04 is settled black, above "
            "0.06 is milky. A naturally bright (high-key) scene has no black and "
            "that is not a bug."
        ),
        "desc_p50": "Median brightness of the frame.",
        "desc_p99": "Brightness above which lie the 1% brightest pixels.",
        "desc_przepal": "Percent of pixels burned out to white. Working threshold: above 1% raises a flag.",
        "desc_ostrosc": (
            "How much fine edge detail and texture is in the frame. Depends on "
            "content: dense foliage gives thousands, fog and smooth sky give "
            "hundreds even when in focus. Good for comparisons within one scene."
        ),
        "desc_nasycenie": "Average color saturation after the LUT (0 gray, 1 maximum).",
        "desc_ruch": (
            "Class (tripod / handheld / shaky, plus pan) and jitter: how much the "
            "frame drifts from one frame to the next, in percent of frame width. "
            "In v0.1 this was computed from only the first 5 s of the clip, so "
            "treat it as a hint. v0.2 computes the whole clip and shows stable "
            "segments."
        ),
        "sort_label": "Sort",
        "sort_id": "by number",
        "sort_p5_asc": "black p5 ascending",
        "sort_p5_desc": "black p5 descending",
        "sort_cliphi_desc": "clipping descending",
        "sort_lapvar_desc": "sharpness descending",
        "sort_jitter_desc": "jitter descending",
        "camera_label": "Camera",
        "camera_all": "all",
        "onlyverdict_label": "verdict only",
        "search_label": "Search",
        "empty_msg": "Nothing matches the filters.",
        "verdict_label": "Verdict",
        "hist_label": "From logs",
        "no_flags": "no flags",
        "unreliable": "unreliable",
        "thumb_alt": "sharpest frame",
        "img_thumb": "thumbnail",
        "img_wave": "waveform",
        "img_profile": "profile",
        "jitter_center": "center jitter (median)",
        "center_word": "center",
        "jitter_word": "jitter",
        # --- eyes/przebieg.py ---
        "przebieg_panel1_title": "brightness after LUT · p5 black · p50 midtone · p99 highlights",
        "przebieg_panel2_title": "jitter (% of frame width)",
        "przebieg_panel3_title": "intentional motion (% of frame width per s)",
        "przebieg_xlabel": "seconds",
        "przebieg_stable": "stable",
        "przebieg_threshold": "stability threshold",
        "przebieg_offscale": "↑ out of range",
        "przebieg_header_suffix": "clip profile v0.2",
    },
}


def t(lang: str, key: str) -> str:
    """Napis dla danego jezyka i klucza. Brak klucza/jezyka -> KeyError
    CELOWO (zamiast .get z fallbackiem) - literowka w kluczu ma wywalic
    testy/uzycie, nie po cichu wyswietlic nic albo klucz surowy."""
    return STRINGS[lang][key]


# Krotkie tlumaczenie nazw flag (wartosci z raportu, patrz eyes/metrics.py)
# na potrzeby tooltipu w wersji en - same nazwy flag NIE sa tlumaczone.
FLAG_GLOSS_EN: dict[str, str] = {
    "clip_hi>1%": "highlight clipping over 1%",
    "czern_mleczna": "milky blacks",
    "czern_zabita": "crushed blacks",
    "nieostre": "out of focus",
    "trzesie": "shaky",
}
