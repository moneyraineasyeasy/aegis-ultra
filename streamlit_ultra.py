from __future__ import annotations

import os

import requests

os.environ["ARROW_DEFAULT_MEMORY_POOL"] = "system"

import hashlib
import json
import math
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

import aegis_ultra_engine as aegis
import ultra_publisher as publisher

# ============================================================
# AEGIS ULTRA V1.1 — STREAMLIT COMMAND CENTER
# ============================================================

APP_NAME = "Aegis Ultra"
APP_VERSION = "1.1.0"


st.set_page_config(
    page_title=APP_NAME,
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# 1. Styling
# ============================================================

st.markdown(
    """
    <style>
    /* Main application */
    .stApp {
        background:
            radial-gradient(
                circle at 15% 10%,
                rgba(74, 108, 247, 0.12),
                transparent 26%
            ),
            radial-gradient(
                circle at 85% 5%,
                rgba(161, 72, 255, 0.10),
                transparent 24%
            ),
            linear-gradient(
                180deg,
                #090b12 0%,
                #0d1019 48%,
                #090b12 100%
            );
    }

    .block-container {
        max-width: 1500px;
        padding-top: 1.4rem;
        padding-bottom: 4rem;
    }

    /* Sidebar */
    [data-testid="stSidebar"] {
        background:
            linear-gradient(
                180deg,
                rgba(18, 21, 34, 0.98),
                rgba(10, 12, 20, 0.98)
            );
        border-right: 1px solid rgba(255, 255, 255, 0.08);
    }

    /* Hero */
    .ultra-hero {
        padding: 2rem 2.2rem;
        margin-bottom: 1.35rem;
        border-radius: 24px;
        background:
            linear-gradient(
                120deg,
                rgba(76, 94, 255, 0.22),
                rgba(143, 69, 255, 0.16),
                rgba(0, 214, 170, 0.10)
            );
        border: 1px solid rgba(255, 255, 255, 0.12);
        box-shadow:
            0 18px 60px rgba(0, 0, 0, 0.35),
            inset 0 1px 0 rgba(255, 255, 255, 0.08);
        backdrop-filter: blur(16px);
    }

    .ultra-title {
        margin: 0;
        color: #ffffff;
        font-size: 3rem;
        font-weight: 850;
        letter-spacing: -0.055em;
        line-height: 1.05;
    }

    .ultra-subtitle {
        margin-top: 0.75rem;
        margin-bottom: 0;
        color: rgba(255, 255, 255, 0.72);
        font-size: 1.05rem;
        line-height: 1.55;
    }

    .ultra-badge {
        display: inline-block;
        padding: 0.35rem 0.7rem;
        margin-bottom: 0.85rem;
        border-radius: 999px;
        color: #bfffea;
        background: rgba(0, 213, 163, 0.13);
        border: 1px solid rgba(0, 213, 163, 0.28);
        font-size: 0.78rem;
        font-weight: 750;
        letter-spacing: 0.08em;
        text-transform: uppercase;
    }

    /* Section headers */
    .section-label {
        margin-top: 1.1rem;
        margin-bottom: 0.85rem;
        color: rgba(255, 255, 255, 0.55);
        font-size: 0.78rem;
        font-weight: 800;
        letter-spacing: 0.12em;
        text-transform: uppercase;
    }

    /* Cards */
    .glass-card {
        padding: 1.15rem 1.3rem;
        margin: 0.5rem 0;
        border-radius: 18px;
        background: rgba(255, 255, 255, 0.045);
        border: 1px solid rgba(255, 255, 255, 0.09);
        box-shadow: 0 10px 35px rgba(0, 0, 0, 0.22);
    }

    .official-banner {
        padding: 0.65rem 0.9rem;
        border-radius: 12px;
        color: #caffef;
        background: rgba(0, 214, 163, 0.13);
        border: 1px solid rgba(0, 214, 163, 0.26);
        font-weight: 750;
    }

    .reference-banner {
        padding: 0.65rem 0.9rem;
        border-radius: 12px;
        color: #ffe9b2;
        background: rgba(255, 187, 66, 0.11);
        border: 1px solid rgba(255, 187, 66, 0.24);
    }

    .danger-banner {
        padding: 0.65rem 0.9rem;
        border-radius: 12px;
        color: #ffd1d1;
        background: rgba(255, 73, 92, 0.12);
        border: 1px solid rgba(255, 73, 92, 0.25);
    }

    .ah-preview {
        padding: 1rem 1.15rem;
        border-radius: 15px;
        background:
            linear-gradient(
                120deg,
                rgba(255, 180, 59, 0.10),
                rgba(255, 255, 255, 0.035)
            );
        border: 1px solid rgba(255, 180, 59, 0.22);
        color: rgba(255, 255, 255, 0.86);
    }

    .score-card {
        text-align: center;
        padding: 1.45rem 1rem;
        border-radius: 20px;
        background:
            linear-gradient(
                145deg,
                rgba(123, 91, 255, 0.15),
                rgba(255, 255, 255, 0.035)
            );
        border: 1px solid rgba(147, 117, 255, 0.22);
        box-shadow: 0 12px 38px rgba(0, 0, 0, 0.24);
    }

    .score-value {
        color: white;
        font-size: 2.25rem;
        font-weight: 850;
        letter-spacing: -0.04em;
    }

    .score-probability {
        margin-top: 0.45rem;
        color: #cfc5ff;
        font-size: 1rem;
        font-weight: 700;
    }

    /* Metrics */
    [data-testid="stMetric"] {
        padding: 1rem 1.05rem;
        border-radius: 16px;
        background: rgba(255, 255, 255, 0.042);
        border: 1px solid rgba(255, 255, 255, 0.075);
        box-shadow: 0 8px 28px rgba(0, 0, 0, 0.17);
    }

    [data-testid="stMetricValue"] {
        font-weight: 800;
        letter-spacing: -0.035em;
    }

    /* Inputs */
    [data-baseweb="input"] > div,
    [data-baseweb="textarea"] > div,
    [data-baseweb="select"] > div {
        background: rgba(255, 255, 255, 0.045);
        border-color: rgba(255, 255, 255, 0.10);
    }

    textarea,
    input {
        font-family:
            Inter,
            -apple-system,
            BlinkMacSystemFont,
            "Segoe UI",
            sans-serif !important;
    }

    /* Buttons */
    .stButton > button,
    .stDownloadButton > button {
        border-radius: 13px;
        min-height: 3rem;
        font-weight: 750;
        border: 1px solid rgba(255, 255, 255, 0.12);
        transition:
            transform 0.15s ease,
            box-shadow 0.15s ease;
    }

    .stButton > button:hover,
    .stDownloadButton > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 10px 28px rgba(0, 0, 0, 0.24);
    }

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 0.55rem;
        padding: 0.35rem;
        border-radius: 14px;
        background: rgba(255, 255, 255, 0.035);
    }

    .stTabs [data-baseweb="tab"] {
        border-radius: 10px;
        padding-left: 1.15rem;
        padding-right: 1.15rem;
        font-weight: 700;
    }

    /* Dataframes */
    [data-testid="stDataFrame"] {
        border-radius: 16px;
        overflow: hidden;
        border: 1px solid rgba(255, 255, 255, 0.08);
    }

    /* Dividers */
    hr {
        border-color: rgba(255, 255, 255, 0.08);
    }

    @media (max-width: 700px) {
        .ultra-title {
            font-size: 2.2rem;
        }

        .ultra-hero {
            padding: 1.4rem 1.3rem;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


st.markdown(
    f"""
    <div class="ultra-hero">
        <div class="ultra-badge">
            Hit-first reconstruction engine · V{APP_VERSION}
        </div>
        <h1 class="ultra-title">
            🛡️ Aegis Ultra
        </h1>
        <p class="ultra-subtitle">
            Target-line-out sharp-market reconstruction,
            conservative hit probability and contradiction-safe
            official recommendations.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# 2. Generic helpers
# ============================================================

def tokenize(text: Any) -> List[str]:
    return (
        str(text)
        .replace(",", " ")
        .split()
    )


def is_skip_token(value: Any) -> bool:
    return str(value).strip().lower() in {
        "",
        "-",
        "x",
        "na",
        "n/a",
        "none",
        "null",
    }


def safe_float(
    value: Any,
    default: Optional[float] = None,
) -> Optional[float]:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return default

    if not math.isfinite(value):
        return default

    return value


def format_probability(
    value: Any,
    decimals: int = 1,
) -> str:
    value = safe_float(value)

    if value is None:
        return "N/A"

    return (
        f"{value * 100.0:.{decimals}f}%"
    )


def format_percentage_points(
    value: Any,
    decimals: int = 2,
) -> str:
    value = safe_float(value)

    if value is None:
        return "N/A"

    return (
        f"{value * 100.0:+.{decimals}f} pp"
    )


def format_odds(
    value: Any,
    decimals: int = 3,
) -> str:
    value = safe_float(value)

    if value is None:
        return "N/A"

    return f"{value:.{decimals}f}"


def format_ev(
    value: Any,
    decimals: int = 2,
) -> str:
    value = safe_float(value)

    if value is None:
        return "N/A"

    return (
        f"{value * 100.0:+.{decimals}f}%"
    )


def probability_value(
    record: Dict[str, Any],
    metric: str,
    statistic: str = "minimum",
):
    return (
        record
        .get("probability", {})
        .get(metric, {})
        .get(statistic)
    )


def summary_value(
    record: Dict[str, Any],
    field: str,
    statistic: str = "minimum",
):
    return (
        record
        .get(field, {})
        .get(statistic)
    )


def html_escape(value: Any) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# ============================================================
# 3. Odds parsers
# ============================================================

def parse_required_triplet(
    text: str,
    label: str,
) -> Dict[str, float]:
    tokens = tokenize(text)

    if len(tokens) != 3:
        raise ValueError(
            f"{label}: enter exactly three odds."
        )

    if any(
        is_skip_token(token)
        for token in tokens
    ):
        raise ValueError(
            f"{label}: all three odds are required."
        )

    return {
        "home": aegis.validate_odds(
            tokens[0],
            f"{label} home",
        ),
        "draw": aegis.validate_odds(
            tokens[1],
            f"{label} draw",
        ),
        "away": aegis.validate_odds(
            tokens[2],
            f"{label} away",
        ),
    }


def parse_optional_triplet(
    text: str,
    label: str,
):
    if not str(text).strip():
        return None

    tokens = tokenize(text)

    if len(tokens) != 3:
        raise ValueError(
            f"{label}: enter exactly three values."
        )

    values = []

    for index, token in enumerate(tokens):
        if is_skip_token(token):
            values.append(None)
        else:
            values.append(
                aegis.validate_odds(
                    token,
                    (
                        f"{label} "
                        f"#{index + 1}"
                    ),
                )
            )

    if all(
        value is None
        for value in values
    ):
        return None

    return {
        "home": values[0],
        "draw": values[1],
        "away": values[2],
    }


def parse_sharp_ah(
    text: str,
    label: str,
) -> List[Dict[str, float]]:
    rows = []
    seen_lines = set()

    for row_number, raw_line in enumerate(
        str(text).splitlines(),
        start=1,
    ):
        raw_line = raw_line.strip()

        if not raw_line:
            continue

        tokens = tokenize(raw_line)

        if len(tokens) != 3:
            raise ValueError(
                f"{label} row {row_number}: "
                "expected HOME_line HOME_odds "
                "AWAY_odds."
            )

        line = aegis.validate_quarter_line(
            tokens[0],
            (
                f"{label} row "
                f"{row_number} line"
            ),
        )

        if line in seen_lines:
            raise ValueError(
                f"{label}: duplicate line "
                f"{line:g}."
            )

        if (
            is_skip_token(tokens[1])
            or is_skip_token(tokens[2])
        ):
            raise ValueError(
                f"{label} row {row_number}: "
                "both prices are required."
            )

        seen_lines.add(line)

        rows.append({
            "line": line,
            "home": aegis.validate_odds(
                tokens[1],
                (
                    f"{label} row "
                    f"{row_number} home"
                ),
            ),
            "away": aegis.validate_odds(
                tokens[2],
                (
                    f"{label} row "
                    f"{row_number} away"
                ),
            ),
        })

    return rows


def parse_sharp_ou(
    text: str,
    label: str,
) -> List[Dict[str, float]]:
    rows = []
    seen_lines = set()

    for row_number, raw_line in enumerate(
        str(text).splitlines(),
        start=1,
    ):
        raw_line = raw_line.strip()

        if not raw_line:
            continue

        tokens = tokenize(raw_line)

        if len(tokens) != 3:
            raise ValueError(
                f"{label} row {row_number}: "
                "expected line OVER_odds "
                "UNDER_odds."
            )

        line = aegis.validate_quarter_line(
            tokens[0],
            (
                f"{label} row "
                f"{row_number} line"
            ),
        )

        if line in seen_lines:
            raise ValueError(
                f"{label}: duplicate line "
                f"{line:g}."
            )

        if (
            is_skip_token(tokens[1])
            or is_skip_token(tokens[2])
        ):
            raise ValueError(
                f"{label} row {row_number}: "
                "both prices are required."
            )

        seen_lines.add(line)

        rows.append({
            "line": line,
            "over": aegis.validate_odds(
                tokens[1],
                (
                    f"{label} row "
                    f"{row_number} over"
                ),
            ),
            "under": aegis.validate_odds(
                tokens[2],
                (
                    f"{label} row "
                    f"{row_number} under"
                ),
            ),
        })

    return rows


def parse_hkjc_ah(
    text: str,
    label: str,
) -> List[Dict[str, Optional[float]]]:
    rows = []
    seen_lines = set()

    for row_number, raw_line in enumerate(
        str(text).splitlines(),
        start=1,
    ):
        raw_line = raw_line.strip()

        if not raw_line:
            continue

        tokens = tokenize(raw_line)

        if len(tokens) != 3:
            raise ValueError(
                f"{label} row {row_number}: "
                "expected HOME_line HOME_odds "
                "AWAY_odds."
            )

        line = aegis.validate_quarter_line(
            tokens[0],
            (
                f"{label} row "
                f"{row_number} line"
            ),
        )

        if line in seen_lines:
            raise ValueError(
                f"{label}: duplicate line "
                f"{line:g}."
            )

        seen_lines.add(line)

        home_odds = (
            None
            if is_skip_token(tokens[1])
            else aegis.validate_odds(
                tokens[1],
                (
                    f"{label} row "
                    f"{row_number} home"
                ),
            )
        )

        away_odds = (
            None
            if is_skip_token(tokens[2])
            else aegis.validate_odds(
                tokens[2],
                (
                    f"{label} row "
                    f"{row_number} away"
                ),
            )
        )

        if (
            home_odds is None
            and away_odds is None
        ):
            raise ValueError(
                f"{label} row {row_number}: "
                "enter at least one price."
            )

        rows.append({
            "line": line,
            "home": home_odds,
            "away": away_odds,
        })

    return rows


def parse_hkjc_ou(
    text: str,
    label: str,
) -> List[Dict[str, Optional[float]]]:
    rows = []
    seen_lines = set()

    for row_number, raw_line in enumerate(
        str(text).splitlines(),
        start=1,
    ):
        raw_line = raw_line.strip()

        if not raw_line:
            continue

        tokens = tokenize(raw_line)

        if len(tokens) != 3:
            raise ValueError(
                f"{label} row {row_number}: "
                "expected line OVER_odds "
                "UNDER_odds."
            )

        line = aegis.validate_quarter_line(
            tokens[0],
            (
                f"{label} row "
                f"{row_number} line"
            ),
        )

        if line in seen_lines:
            raise ValueError(
                f"{label}: duplicate line "
                f"{line:g}."
            )

        seen_lines.add(line)

        over_odds = (
            None
            if is_skip_token(tokens[1])
            else aegis.validate_odds(
                tokens[1],
                (
                    f"{label} row "
                    f"{row_number} over"
                ),
            )
        )

        under_odds = (
            None
            if is_skip_token(tokens[2])
            else aegis.validate_odds(
                tokens[2],
                (
                    f"{label} row "
                    f"{row_number} under"
                ),
            )
        )

        if (
            over_odds is None
            and under_odds is None
        ):
            raise ValueError(
                f"{label} row {row_number}: "
                "enter at least one price."
            )

        rows.append({
            "line": line,
            "over": over_odds,
            "under": under_odds,
        })

    return rows


# ============================================================
# 4. Manual input builder
# ============================================================

def build_manual_input(
    *,
    home_name: str,
    away_name: str,
    competition: str,
    kickoff: str,
    snapshot_time: str,
    primary_key: str,
    primary_title: str,
    primary_1x2: str,
    primary_ah: str,
    primary_ou: str,
    enable_second_source: bool,
    second_key: str,
    second_title: str,
    second_1x2: str,
    second_ah: str,
    second_ou: str,
    hkjc_1x2: str,
    hkjc_ah: str,
    hkjc_ou: str,
    minimum_odds: float,
    maximum_odds_enabled: bool,
    maximum_odds: float,
    maximum_recommendations: int,
    minimum_official_hit_pct: float,
    correct_score_count: int,
    devig_methods: List[str],
    ev_floor_enabled: bool,
    ev_rejection_floor_pct: float,
) -> Dict[str, Any]:
    home_name = str(home_name).strip()
    away_name = str(away_name).strip()

    if not home_name or not away_name:
        raise ValueError(
            "Home and away teams are required."
        )

    if (
        home_name.casefold()
        == away_name.casefold()
    ):
        raise ValueError(
            "Home and away teams cannot match."
        )

    primary_key = (
        str(primary_key)
        .strip()
        .lower()
    )

    primary_title = (
        str(primary_title).strip()
        or primary_key
    )

    if not primary_key:
        raise ValueError(
            "Primary source key is required."
        )

    primary_ah_rows = parse_sharp_ah(
        primary_ah,
        f"{primary_title} AH",
    )

    primary_ou_rows = parse_sharp_ou(
        primary_ou,
        f"{primary_title} O/U",
    )

    if not primary_ah_rows:
        raise ValueError(
            "Enter at least one primary AH line."
        )

    if not primary_ou_rows:
        raise ValueError(
            "Enter at least one primary O/U line."
        )

    sharp_books = [{
        "key": primary_key,
        "title": primary_title,
        "timestamp": (
            str(snapshot_time).strip()
        ),
        "markets": {
            "1X2": parse_required_triplet(
                primary_1x2,
                f"{primary_title} 1X2",
            ),
            "AH": primary_ah_rows,
            "OU": primary_ou_rows,
        },
    }]

    if enable_second_source:
        second_key = (
            str(second_key)
            .strip()
            .lower()
        )

        second_title = (
            str(second_title).strip()
            or second_key
        )

        if not second_key:
            raise ValueError(
                "Second source key is required."
            )

        if second_key == primary_key:
            raise ValueError(
                "Sharp source keys must differ."
            )

        second_ah_rows = parse_sharp_ah(
            second_ah,
            f"{second_title} AH",
        )

        second_ou_rows = parse_sharp_ou(
            second_ou,
            f"{second_title} O/U",
        )

        if not second_ah_rows:
            raise ValueError(
                "Enter at least one second-source "
                "AH line."
            )

        if not second_ou_rows:
            raise ValueError(
                "Enter at least one second-source "
                "O/U line."
            )

        sharp_books.append({
            "key": second_key,
            "title": second_title,
            "timestamp": (
                str(snapshot_time).strip()
            ),
            "markets": {
                "1X2": parse_required_triplet(
                    second_1x2,
                    f"{second_title} 1X2",
                ),
                "AH": second_ah_rows,
                "OU": second_ou_rows,
            },
        })

    hkjc_markets = []
    counter = 1

    hkjc_1x2_values = (
        parse_optional_triplet(
            hkjc_1x2,
            "HKJC 1X2",
        )
    )

    if hkjc_1x2_values is not None:
        one_x_two_specs = [
            (
                "home",
                "HOME",
                f"{home_name} 全場勝",
            ),
            (
                "draw",
                "DRAW",
                "全場和",
            ),
            (
                "away",
                "AWAY",
                f"{away_name} 全場勝",
            ),
        ]

        for key, selection, label in (
            one_x_two_specs
        ):
            odds = hkjc_1x2_values[key]

            if odds is None:
                continue

            hkjc_markets.append({
                "id": f"M{counter:03d}",
                "label": label,
                "period": "FT",
                "market": "1X2",
                "selection": selection,
                "odds": odds,
            })

            counter += 1

    for row in parse_hkjc_ah(
        hkjc_ah,
        "HKJC AH",
    ):
        if row["home"] is not None:
            hkjc_markets.append({
                "id": f"M{counter:03d}",
                "label": (
                    f"{home_name} "
                    f"{row['line']:+g}"
                ),
                "period": "FT",
                "market": "AH",
                "selection": "HOME",
                "line": row["line"],
                "odds": row["home"],
            })

            counter += 1

        if row["away"] is not None:
            hkjc_markets.append({
                "id": f"M{counter:03d}",
                "label": (
                    f"{away_name} "
                    f"{-row['line']:+g}"
                ),
                "period": "FT",
                "market": "AH",
                "selection": "AWAY",
                "line": row["line"],
                "odds": row["away"],
            })

            counter += 1

    for row in parse_hkjc_ou(
        hkjc_ou,
        "HKJC O/U",
    ):
        if row["over"] is not None:
            hkjc_markets.append({
                "id": f"M{counter:03d}",
                "label": (
                    "全場入球大 "
                    f"{row['line']:g}"
                ),
                "period": "FT",
                "market": "OU",
                "selection": "OVER",
                "line": row["line"],
                "odds": row["over"],
            })

            counter += 1

        if row["under"] is not None:
            hkjc_markets.append({
                "id": f"M{counter:03d}",
                "label": (
                    "全場入球細 "
                    f"{row['line']:g}"
                ),
                "period": "FT",
                "market": "OU",
                "selection": "UNDER",
                "line": row["line"],
                "odds": row["under"],
            })

            counter += 1

    if not hkjc_markets:
        raise ValueError(
            "Enter at least one HKJC market."
        )

    if not devig_methods:
        raise ValueError(
            "Select at least one de-vig method."
        )

    return {
        "match": {
            "name": (
                f"{home_name} vs {away_name}"
            ),
            "home": home_name,
            "away": away_name,
            "competition": (
                str(competition).strip()
            ),
            "kickoff": str(kickoff).strip(),
            "snapshot_time": (
                str(snapshot_time).strip()
            ),
        },
        "sharp_books": sharp_books,
        "hkjc_markets": hkjc_markets,
        "settings": {
            "primary_source": primary_key,
            "minimum_odds": float(
                minimum_odds
            ),
            "maximum_odds": (
                float(maximum_odds)
                if maximum_odds_enabled
                else None
            ),
            "max_recommendations": int(
                maximum_recommendations
            ),
            "minimum_official_hit_probability": (
                float(minimum_official_hit_pct)
                / 100.0
            ),
            "correct_score_count": int(
                correct_score_count
            ),
            "devig_methods": list(
                devig_methods
            ),
            "ev_rejection_floor": (
                float(
                    ev_rejection_floor_pct
                )
                / 100.0
                if ev_floor_enabled
                else None
            ),
        },
    }


# ============================================================
# 5. Cache and execution
# ============================================================

@st.cache_data(
    show_spinner=False,
    max_entries=32,
)
def cached_engine_run(
    canonical_json: str,
    engine_fingerprint: str,
) -> Dict[str, Any]:
    del engine_fingerprint

    return aegis.run_engine(
        json.loads(canonical_json)
    )


def execute_engine(
    input_data: Dict[str, Any],
) -> Dict[str, Any]:
    canonical_json = json.dumps(
        input_data,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

    with open(
        aegis.__file__,
        "rb",
    ) as engine_file:
        engine_fingerprint = (
            hashlib.sha256(
                engine_file.read()
            ).hexdigest()
        )

    analysis_hash = hashlib.sha256(
        (
            canonical_json
            + engine_fingerprint
        ).encode("utf-8")
    ).hexdigest()

    if (
        st.session_state.get(
            "ultra_analysis_hash"
        ) == analysis_hash
        and "ultra_result"
        in st.session_state
    ):
        return st.session_state[
            "ultra_result"
        ]

    output = cached_engine_run(
        canonical_json,
        engine_fingerprint,
    )

    st.session_state[
        "ultra_analysis_hash"
    ] = analysis_hash

    st.session_state[
        "ultra_result"
    ] = output

    st.session_state[
        "ultra_input"
    ] = output.get(
        "input_snapshot",
        input_data,
    )

    return output


# ============================================================
# 6. AH interpretation preview
# ============================================================

def display_ah_preview(
    home_name: str,
    away_name: str,
    text: str,
    label: str,
):
    if not text.strip():
        return

    try:
        rows = parse_hkjc_ah(
            text,
            label,
        )
    except Exception:
        return

    if not rows:
        return

    preview_lines = []

    home_display = (
        home_name.strip()
        or "HOME"
    )

    away_display = (
        away_name.strip()
        or "AWAY"
    )

    for row in rows:
        home_price = (
            "—"
            if row["home"] is None
            else f"{row['home']:.3f}"
        )

        away_price = (
            "—"
            if row["away"] is None
            else f"{row['away']:.3f}"
        )

        preview_lines.append(
            "<b>"
            + html_escape(home_display)
            + f" {row['line']:+g}"
            + "</b>"
            + f" @ {home_price}"
            + " &nbsp; / &nbsp; "
            + "<b>"
            + html_escape(away_display)
            + f" {-row['line']:+g}"
            + "</b>"
            + f" @ {away_price}"
        )

    st.markdown(
        """
        <div class="ah-preview">
            <b>⚠️ AH interpretation preview</b><br>
            The first number is always the handicap
            applied to the HOME team.<br><br>
        """
        + "<br>".join(preview_lines)
        + "</div>",
        unsafe_allow_html=True,
    )


# ============================================================
# 7. Dataframe builders
# ============================================================

def official_dataframe(
    output: Dict[str, Any],
) -> pd.DataFrame:
    rows = []

    for item in output.get(
        "recommendations",
        [],
    ):
        rows.append({
            "Rank": item.get("rank"),
            "Recommendation": item.get(
                "label"
            ),
            "HKJC odds": item.get(
                "hkjc_odds"
            ),
            "Conservative hit": (
                format_probability(
                    probability_value(
                        item,
                        "hit",
                        "minimum",
                    )
                )
            ),
            "Median hit": (
                format_probability(
                    probability_value(
                        item,
                        "hit",
                        "median",
                    )
                )
            ),
            "Conservative non-loss": (
                format_probability(
                    probability_value(
                        item,
                        "nonloss",
                        "minimum",
                    )
                )
            ),
            "Maximum full loss": (
                format_probability(
                    probability_value(
                        item,
                        "full_loss",
                        "maximum",
                    )
                )
            ),
            "Fair odds max": format_odds(
                summary_value(
                    item,
                    "fair_odds",
                    "maximum",
                )
            ),
            "EV minimum": format_ev(
                summary_value(
                    item,
                    "expected_return",
                    "minimum",
                )
            ),
            "Price": item.get(
                "price_status"
            ),
        })

    return pd.DataFrame(rows)


def reference_status(
    candidate: Dict[str, Any],
) -> str:
    if candidate.get("official"):
        return "✅ OFFICIAL"

    official_reasons = candidate.get(
        "official_exclusion_reasons",
        [],
    )

    base_reasons = candidate.get(
        "exclusion_reasons",
        [],
    )

    if (
        "BELOW_MINIMUM_OFFICIAL_"
        "HIT_PROBABILITY"
        in official_reasons
    ):
        return "📉 BELOW HIT THRESHOLD"

    if (
        "CONFLICTS_WITH_HIGHER_"
        "RANKED_OFFICIAL_PICK"
        in official_reasons
    ):
        return "⚔️ CONTRADICTORY"

    if (
        "MAXIMUM_RECOMMENDATIONS_REACHED"
        in official_reasons
    ):
        return "📋 MAX PICKS REACHED"

    if base_reasons:
        return "⛔ INELIGIBLE"

    return "ℹ️ REFERENCE"


def conflict_text(
    candidate: Dict[str, Any],
) -> str:
    conflicts = candidate.get(
        "conflicts_with",
        [],
    )

    labels = []

    for conflict in conflicts:
        label = conflict.get(
            "selected_label"
        )

        if label:
            labels.append(str(label))

    return ", ".join(labels)


def all_lines_dataframe(
    output: Dict[str, Any],
) -> pd.DataFrame:
    rows = []

    for candidate in output.get(
        "candidate_markets",
        [],
    ):
        reasons = (
            candidate.get(
                "official_exclusion_reasons",
                [],
            )
            + candidate.get(
                "exclusion_reasons",
                [],
            )
        )

        rows.append({
            "Status": reference_status(
                candidate
            ),
            "Option": candidate.get(
                "label"
            ),
            "Market": candidate.get(
                "market"
            ),
            "HKJC odds": candidate.get(
                "hkjc_odds"
            ),
            "Conservative hit": (
                format_probability(
                    probability_value(
                        candidate,
                        "hit",
                        "minimum",
                    )
                )
            ),
            "Median hit": (
                format_probability(
                    probability_value(
                        candidate,
                        "hit",
                        "median",
                    )
                )
            ),
            "Conservative non-loss": (
                format_probability(
                    probability_value(
                        candidate,
                        "nonloss",
                        "minimum",
                    )
                )
            ),
            "Maximum full loss": (
                format_probability(
                    probability_value(
                        candidate,
                        "full_loss",
                        "maximum",
                    )
                )
            ),
            "Fair odds max": format_odds(
                summary_value(
                    candidate,
                    "fair_odds",
                    "maximum",
                )
            ),
            "EV minimum": format_ev(
                summary_value(
                    candidate,
                    "expected_return",
                    "minimum",
                )
            ),
            "Price": candidate.get(
                "price_status"
            ),
            "Conflicts with": conflict_text(
                candidate
            ),
            "Reason": ", ".join(reasons),
        })

    return pd.DataFrame(rows)


# ============================================================
# 8. Result display
# ============================================================

def display_price_status(
    recommendation: Dict[str, Any],
):
    price_status = recommendation.get(
        "price_status",
        "UNKNOWN",
    )

    if price_status == "FAIR_OR_BETTER":
        st.markdown(
            """
            <div class="official-banner">
                💎 Price audit: fair or better
            </div>
            """,
            unsafe_allow_html=True,
        )

    elif price_status in {
        "POOR_PRICE",
        "SEVERELY_UNDERPAID",
    }:
        st.markdown(
            f"""
            <div class="danger-banner">
                ⚠️ Price audit: {html_escape(price_status)}
                — this does not change hit-first ranking.
            </div>
            """,
            unsafe_allow_html=True,
        )

    else:
        st.markdown(
            f"""
            <div class="reference-banner">
                Price audit: {html_escape(price_status)}
            </div>
            """,
            unsafe_allow_html=True,
        )


def display_official_recommendation(
    recommendation: Dict[str, Any],
):
    rank = recommendation.get(
        "rank",
        "?"
    )

    with st.container(border=True):
        st.markdown(
            f"""
            <div class="official-banner">
                OFFICIAL PICK #{rank}
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.subheader(
            recommendation.get(
                "label",
                "Recommendation",
            )
        )

        first, second, third, fourth = (
            st.columns(4)
        )

        first.metric(
            "保守命中概率",
            format_probability(
                probability_value(
                    recommendation,
                    "hit",
                    "minimum",
                )
            ),
            help=(
                "Lowest positive-return probability "
                "across valid target-line-out "
                "scenarios."
            ),
        )

        second.metric(
            "中位命中概率",
            format_probability(
                probability_value(
                    recommendation,
                    "hit",
                    "median",
                )
            ),
        )

        third.metric(
            "保守不輸概率",
            format_probability(
                probability_value(
                    recommendation,
                    "nonloss",
                    "minimum",
                )
            ),
        )

        fourth.metric(
            "HKJC 賠率",
            format_odds(
                recommendation.get(
                    "hkjc_odds"
                )
            ),
        )

        first, second, third, fourth = (
            st.columns(4)
        )

        first.metric(
            "最大全輸概率",
            format_probability(
                probability_value(
                    recommendation,
                    "full_loss",
                    "maximum",
                )
            ),
        )

        second.metric(
            "保守公平賠率",
            format_odds(
                summary_value(
                    recommendation,
                    "fair_odds",
                    "maximum",
                )
            ),
        )

        third.metric(
            "保守 EV",
            format_ev(
                summary_value(
                    recommendation,
                    "expected_return",
                    "minimum",
                )
            ),
            help=(
                "Price audit only. EV is not "
                "used to rank official picks."
            ),
        )

        fourth.metric(
            "市場差異",
            format_percentage_points(
                summary_value(
                    recommendation,
                    (
                        "fair_probability_"
                        "discrepancy"
                    ),
                    "median",
                )
            ),
            help=(
                "Target-line-out probability minus "
                "the direct de-vigged sharp-market "
                "probability."
            ),
        )

        display_price_status(
            recommendation
        )

        detail_tab, scenario_tab = st.tabs([
            "Settlement details",
            "Target-line-out audit",
        ])

        with detail_tab:
            rows = []

            labels = {
                "full_win": "Full win",
                "half_win": "Half win",
                "push": "Push",
                "half_loss": "Half loss",
                "full_loss": "Full loss",
            }

            for key, label in labels.items():
                record = (
                    recommendation
                    .get("probability", {})
                    .get(key, {})
                )

                rows.append({
                    "Settlement": label,
                    "Minimum": (
                        format_probability(
                            record.get("minimum"),
                            2,
                        )
                    ),
                    "Median": (
                        format_probability(
                            record.get("median"),
                            2,
                        )
                    ),
                    "Maximum": (
                        format_probability(
                            record.get("maximum"),
                            2,
                        )
                    ),
                })

            st.dataframe(
                pd.DataFrame(rows),
                use_container_width=True,
                hide_index=True,
            )

        with scenario_tab:
            scenario_rows = []

            for scenario in recommendation.get(
                "scenarios",
                [],
            ):
                scenario_rows.append({
                    "Source": scenario.get(
                        "source_title"
                    ),
                    "De-vig": scenario.get(
                        "devig_method"
                    ),
                    "Scenario": scenario.get(
                        "scenario_type"
                    ),
                    "Excluded": scenario.get(
                        "excluded_group"
                    ),
                    "Hit": (
                        format_probability(
                            scenario.get(
                                "hit_probability"
                            ),
                            2,
                        )
                    ),
                    "Non-loss": (
                        format_probability(
                            scenario.get(
                                "nonloss_probability"
                            ),
                            2,
                        )
                    ),
                    "Fair odds": format_odds(
                        scenario.get(
                            "fair_odds"
                        )
                    ),
                    "EV": format_ev(
                        scenario.get(
                            "expected_return"
                        )
                    ),
                    "Discrepancy": (
                        format_percentage_points(
                            scenario.get(
                                "fair_probability_"
                                "discrepancy"
                            )
                        )
                    ),
                })

            if scenario_rows:
                st.dataframe(
                    pd.DataFrame(
                        scenario_rows
                    ),
                    use_container_width=True,
                    hide_index=True,
                )

            if recommendation.get(
                "scenario_errors"
            ):
                st.write("Scenario errors")
                st.json(
                    recommendation[
                        "scenario_errors"
                    ]
                )


def display_correct_scores(
    output: Dict[str, Any],
):
    section = output.get(
        "correct_scores",
        {},
    )

    scores = section.get(
        "recommendations",
        [],
    )

    if not scores:
        return

    st.markdown(
        '<div class="section-label">High-risk reference</div>',
        unsafe_allow_html=True,
    )

    st.header("🎯 波膽參考")

    st.warning(
        section.get(
            "warning",
            (
                "Correct scores have much lower "
                "probabilities than main markets."
            ),
        )
    )

    columns = st.columns(
        len(scores)
    )

    for column, score in zip(
        columns,
        scores,
    ):
        probability = score.get(
            "probability",
            {},
        )

        with column:
            st.markdown(
                f"""
                <div class="score-card">
                    <div class="score-value">
                        {html_escape(score.get("score", "—"))}
                    </div>
                    <div class="score-probability">
                        保守概率
                        {format_probability(
                            probability.get("minimum"),
                            2
                        )}
                    </div>
                    <div style="
                        color: rgba(255,255,255,0.55);
                        margin-top: 0.35rem;
                    ">
                        中位概率
                        {format_probability(
                            probability.get("median"),
                            2
                        )}
                        · Fair
                        {format_odds(
                            score.get("central_fair_odds")
                        )}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    combined = section.get(
        "combined_probability",
        {},
    )

    st.info(
        "Combined conservative probability: "
        + format_probability(
            combined.get("minimum"),
            2,
        )
        + " ｜ Median: "
        + format_probability(
            combined.get("median"),
            2,
        )
    )

# ============================================================
# PORTAL PUBLISHING CENTRE
# ============================================================

def display_publishing_centre(
    output: Dict[str, Any],
):
    st.divider()

    st.markdown(
        """
        <div class="section-label">
            Client Portal Publishing
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.header("🚀 VIP Portal Publishing Centre")

    st.markdown(
        """
        <div class="glass-card">
            Select what clients can see, assign tiers,
            edit commentary, and publish directly to
            the VIP Match Centre.
        </div>
        """,
        unsafe_allow_html=True,
    )

    catalogue = publisher.publication_catalogue(
        output
    )

    if not catalogue:
        st.warning(
            "No recommendation or correct-score "
            "data are available to publish."
        )
        return

    match_id = publisher.make_match_id(
        output
    )

    match = output.get(
        "match",
        {},
    )

    st.caption(
        f"Portal Match ID: `{match_id}`"
    )

    # --------------------------------------------------------
    # Match presentation
    # --------------------------------------------------------

    with st.container(border=True):
        st.subheader("⚽ Match presentation")

        match_status = st.selectbox(
            "Portal status",
            options=[
                "published",
                "draft",
            ],
            index=0,
            key=f"portal_status_{match_id}",
            help=(
                "Published matches appear in the "
                "client portal. Draft matches remain "
                "hidden."
            ),
        )

        default_direction = (
            publisher.model_direction_text(
                output
            )
        )

        model_direction = st.text_input(
            "Model direction",
            value=default_direction,
            key=(
                f"portal_direction_"
                f"{match_id}"
            ),
            help=(
                "Short direction shown on the "
                "match card."
            ),
        )

        default_summary = (
            publisher.model_summary_text(
                output
            )
        )

        model_summary = st.text_area(
            "Client match summary",
            value=default_summary,
            height=110,
            key=(
                f"portal_summary_"
                f"{match_id}"
            ),
        )

        st.info(
            "Top score reference: "
            + (
                publisher.top_scores_text(
                    output
                )
                or "Not available"
            )
        )

    # --------------------------------------------------------
    # Publication editor
    # --------------------------------------------------------

    editor_df = pd.DataFrame(
        catalogue
    )

    for column in [
        "odds",
        "conservative_hit",
        "median_hit",
    ]:
        if column in editor_df.columns:
            editor_df[column] = (
                pd.to_numeric(
                    editor_df[column],
                    errors="coerce",
                )
            )

    st.subheader("🎛️ Select client content")

    st.caption(
        "Official picks are selected automatically. "
        "You may also publish alternatives and 波膽."
    )

    edited_df = st.data_editor(
        editor_df,
        hide_index=True,
        use_container_width=True,
        num_rows="fixed",
        key=f"portal_editor_{match_id}",
        disabled=[
            "source_type",
            "source_id",
            "market",
            "odds",
            "conservative_hit",
            "median_hit",
            "status",
        ],
        column_config={
            # Internal metadata stays hidden.
            "source_type": None,
            "source_id": None,

            "publish": st.column_config.CheckboxColumn(
                "Publish",
                help=(
                    "Tick to display this item "
                    "in the client portal."
                ),
                default=False,
            ),

            "tier": st.column_config.SelectboxColumn(
                "Client tier",
                options=[
                    "OFFICIAL",
                    "ALTERNATIVE",
                    "CORRECT_SCORE",
                ],
                required=True,
                width="medium",
            ),

            "rank": st.column_config.NumberColumn(
                "Rank",
                min_value=0,
                max_value=99,
                step=1,
                format="%d",
                width="small",
            ),

            "title": st.column_config.TextColumn(
                "Client title",
                required=True,
                width="large",
            ),

            "market": st.column_config.TextColumn(
                "Market",
                width="small",
            ),

            "odds": st.column_config.NumberColumn(
                "Odds",
                format="%.3f",
                width="small",
            ),

            "conservative_hit": (
                st.column_config.NumberColumn(
                    "Conservative hit",
                    format="percent",
                    width="small",
                )
            ),

            "median_hit": (
                st.column_config.NumberColumn(
                    "Median hit",
                    format="percent",
                    width="small",
                )
            ),

            "stars": st.column_config.NumberColumn(
                "Stars",
                help="Client-facing confidence stars.",
                min_value=1,
                max_value=5,
                step=1,
                format="%d ⭐",
                width="small",
            ),

            "is_heavy": (
                st.column_config.CheckboxColumn(
                    "🔥 重心",
                    help=(
                        "Mark as a highlighted "
                        "heavy recommendation."
                    ),
                    default=False,
                    width="small",
                )
            ),

            "commentary": (
                st.column_config.TextColumn(
                    "雨姐短評",
                    help=(
                        "Editable client-facing "
                        "commentary."
                    ),
                    width="large",
                )
            ),

            "status": st.column_config.TextColumn(
                "Ultra status",
                width="medium",
            ),
        },
    )

    selected_count = int(
        edited_df["publish"]
        .fillna(False)
        .astype(bool)
        .sum()
    )

    first, second, third = st.columns(3)

    first.metric(
        "Selected items",
        selected_count,
    )

    second.metric(
        "Official selected",
        int(
            (
                edited_df["publish"]
                .fillna(False)
                .astype(bool)
                & (
                    edited_df["tier"]
                    == "OFFICIAL"
                )
            ).sum()
        ),
    )

    third.metric(
        "Alternatives selected",
        int(
            (
                edited_df["publish"]
                .fillna(False)
                .astype(bool)
                & (
                    edited_df["tier"]
                    == "ALTERNATIVE"
                )
            ).sum()
        ),
    )

    # --------------------------------------------------------
    # Confirmation and publishing
    # --------------------------------------------------------

    confirm_publish = st.checkbox(
        "I have checked the titles, tiers, "
        "commentary and handicap directions.",
        key=f"portal_confirm_{match_id}",
    )

    publish_clicked = st.button(
        "📡 Publish Selected Items to VIP Portal",
        type="primary",
        use_container_width=True,
        disabled=(
            not confirm_publish
            or selected_count == 0
        ),
        key=f"portal_publish_{match_id}",
    )

    if publish_clicked:
        try:
            editor_rows = (
                edited_df
                .where(
                    pd.notnull(edited_df),
                    None,
                )
                .to_dict(
                    orient="records"
                )
            )

            bundle = (
                publisher.build_publish_bundle(
                    output=output,
                    editor_rows=editor_rows,
                    match_status=match_status,
                    model_direction=(
                        model_direction
                    ),
                    model_summary=(
                        model_summary
                    ),
                )
            )

            with st.spinner(
                "Publishing to the VIP Portal..."
            ):
                result = publisher.publish_bundle(
                    api_url=(
                        st.secrets[
                            "portal_api"
                        ]["url"]
                    ),
                    api_token=(
                        st.secrets[
                            "portal_api"
                        ]["token"]
                    ),
                    bundle=bundle,
                )

            st.success(
                "✅ Match and recommendations "
                "published successfully."
            )

            st.session_state[
                "last_portal_publish_result"
            ] = result

            st.json(result)

        except Exception as error:
            st.error(
                f"Publication failed: {error}"
            )
            st.exception(error)
# ============================================================
# 9. Sidebar
# ============================================================

with st.sidebar:
    st.markdown("## 🛡️ Aegis Ultra")

    st.caption(
        f"Command Center · V{APP_VERSION}"
    )

    # ...existing sidebar code...

    if st.button(
        "🗑️ Clear current analysis",
        use_container_width=True,
    ):
        for key in [
            "ultra_result",
            "ultra_input",
            "ultra_analysis_hash",
        ]:
            st.session_state.pop(key, None)

        st.success("Current analysis cleared.")

    st.markdown("---")

    # NEW CONNECTION TEST
    if st.button(
        "🔌 Test Portal Connection",
        use_container_width=True,
    ):
        try:
            response = requests.post(
    st.secrets["portal_api"]["url"],
    json={
        "token": st.secrets[
            "portal_api"
        ]["token"],
        "action": "ping",
    },
    timeout=20,
)

            response.raise_for_status()
            result = response.json()

            if result.get("ok"):
                st.success(
                    "Portal API connected securely."
                )
            else:
                st.error(
                    f"API rejected request: {result}"
                )

        except Exception as error:
            st.error(
                f"Connection failed: {error}"
            )

    st.caption(
        f"Command Center · V{APP_VERSION}"
    )

    st.success(
        "Hit-first ranking\n\n"
        "Contradiction-safe official picks"
    )

    st.markdown("---")

    st.markdown("### Engine policy")

    st.write(
        "• No historical team data"
    )
    st.write(
        "• No arbitrary model weights"
    )
    st.write(
        "• No Kelly ranking"
    )
    st.write(
        "• EV is price audit only"
    )
    st.write(
        "• All entered lines remain visible"
    )

    st.markdown("---")

# ============================================================
# 10. Input interface
# ============================================================

input_mode = st.radio(
    "Input method",
    [
        "🎛️ Manual entry",
        "📋 Paste JSON",
        "📁 Upload JSON",
    ],
    horizontal=True,
)

input_to_run = None


# ============================================================
# 11. Manual input
# ============================================================

if input_mode == "🎛️ Manual entry":
    st.markdown(
        '<div class="section-label">Match information</div>',
        unsafe_allow_html=True,
    )

    first, second = st.columns(2)

    with first:
        home_name = st.text_input(
            "Home team",
            key="ultra_home_name",
        )

    with second:
        away_name = st.text_input(
            "Away team",
            key="ultra_away_name",
        )

    first, second, third = st.columns(3)

    with first:
        competition = st.text_input(
            "Competition",
            key="ultra_competition",
        )

    with second:
        kickoff = st.text_input(
            "Kickoff",
            placeholder=(
                "2026-07-24T20:00:00+08:00"
            ),
            key="ultra_kickoff",
        )

    with third:
        snapshot_time = st.text_input(
            "Odds snapshot time",
            value=(
                datetime.now()
                .astimezone()
                .isoformat(
                    timespec="minutes"
                )
            ),
            key="ultra_snapshot_time",
        )

    st.markdown(
        '<div class="section-label">Sharp market</div>',
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        st.subheader("⚡ Primary sharp source")

        first, second = st.columns(2)

        with first:
            primary_key = st.text_input(
                "Source key",
                value="pinnacle",
                key="ultra_primary_key",
            )

        with second:
            primary_title = st.text_input(
                "Source name",
                value="Pinnacle",
                key="ultra_primary_title",
            )

        primary_1x2 = st.text_input(
            "1X2 — Home / Draw / Away",
            placeholder="2.20 3.60 3.40",
            key="ultra_primary_1x2",
        )

        first, second = st.columns(2)

        with first:
            primary_ah = st.text_area(
                "AH ladder",
                placeholder=(
                    "HOME_line HOME_odds AWAY_odds\n"
                    "0.00 1.65 2.30\n"
                    "-0.25 1.98 1.92\n"
                    "-0.50 2.20 1.72"
                ),
                height=230,
                key="ultra_primary_ah",
                help=(
                    "The line is always the handicap "
                    "applied to the HOME team."
                ),
            )

        with second:
            primary_ou = st.text_area(
                "O/U ladder",
                placeholder=(
                    "line OVER_odds UNDER_odds\n"
                    "2.00 1.75 2.15\n"
                    "2.25 2.02 1.88\n"
                    "2.50 2.35 1.68\n"
                    "2.75 2.70 1.48"
                ),
                height=230,
                key="ultra_primary_ou",
            )

    enable_second_source = st.checkbox(
        "Add a second sharp source",
        value=False,
        key="ultra_enable_second",
    )

    if enable_second_source:
        with st.container(border=True):
            st.subheader(
                "🔭 Second sharp source"
            )

            first, second = st.columns(2)

            with first:
                second_key = st.text_input(
                    "Second source key",
                    value="sharp_source_2",
                    key="ultra_second_key",
                )

            with second:
                second_title = st.text_input(
                    "Second source name",
                    value="Second sharp source",
                    key="ultra_second_title",
                )

            second_1x2 = st.text_input(
                "Second 1X2 — Home / Draw / Away",
                placeholder="2.18 3.55 3.45",
                key="ultra_second_1x2",
            )

            first, second = st.columns(2)

            with first:
                second_ah = st.text_area(
                    "Second AH ladder",
                    placeholder=(
                        "HOME_line HOME_odds AWAY_odds\n"
                        "0.00 1.66 2.28\n"
                        "-0.25 1.96 1.94"
                    ),
                    height=210,
                    key="ultra_second_ah",
                )

            with second:
                second_ou = st.text_area(
                    "Second O/U ladder",
                    placeholder=(
                        "line OVER_odds UNDER_odds\n"
                        "2.25 2.00 1.90\n"
                        "2.50 2.32 1.70"
                    ),
                    height=210,
                    key="ultra_second_ou",
                )

    else:
        second_key = ""
        second_title = ""
        second_1x2 = ""
        second_ah = ""
        second_ou = ""

    st.markdown(
        '<div class="section-label">HKJC candidates</div>',
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        st.subheader("🏇 HKJC market")

        st.caption(
            "Use X or - for unavailable prices. "
            "All entered lines will remain in the "
            "private reference summary."
        )

        hkjc_1x2 = st.text_input(
            "HKJC 1X2 — Home / Draw / Away",
            placeholder="2.25 3.45 3.25",
            key="ultra_hkjc_1x2",
        )

        first, second = st.columns(2)

        with first:
            hkjc_ah = st.text_area(
                "HKJC AH",
                placeholder=(
                    "HOME_line HOME_odds AWAY_odds\n"
                    "+0.25 1.86 2.02\n"
                    "0.00 1.65 2.30\n"
                    "-0.25 2.05 1.85"
                ),
                height=230,
                key="ultra_hkjc_ah",
                help=(
                    "Example: HOME +0.25 means the "
                    "away team is -0.25."
                ),
            )

        with second:
            hkjc_ou = st.text_area(
                "HKJC O/U",
                placeholder=(
                    "line OVER_odds UNDER_odds\n"
                    "2.50 2.42 1.62\n"
                    "3.25 2.10 1.72\n"
                    "3.50 2.35 1.52"
                ),
                height=230,
                key="ultra_hkjc_ou",
            )

        display_ah_preview(
            home_name=home_name,
            away_name=away_name,
            text=hkjc_ah,
            label="HKJC AH",
        )

    st.markdown(
        '<div class="section-label">Official pick policy</div>',
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        first, second, third = st.columns(3)

        with first:
            minimum_odds = st.number_input(
                "Minimum HKJC odds",
                min_value=1.01,
                value=1.50,
                step=0.05,
                format="%.2f",
                key="ultra_minimum_odds",
            )

        with second:
            maximum_recommendations = (
                st.selectbox(
                    "Maximum official picks",
                    options=[1, 2, 3, 4, 5],
                    index=2,
                    key="ultra_max_recommendations",
                    help=(
                        "This is a ceiling, not a "
                        "number the engine must fill."
                    ),
                )
            )

        with third:
            minimum_official_hit_pct = (
                st.number_input(
                    "Minimum official hit (%)",
                    min_value=0.0,
                    max_value=100.0,
                    value=50.0,
                    step=1.0,
                    format="%.1f",
                    key="ultra_min_hit_pct",
                    help=(
                        "Lines below this conservative "
                        "hit probability remain in the "
                        "reference summary but are not "
                        "official recommendations."
                    ),
                )
            )

        first, second = st.columns(2)

        with first:
            maximum_odds_enabled = st.checkbox(
                "Set maximum HKJC odds",
                value=False,
                key="ultra_enable_max_odds",
            )

            if maximum_odds_enabled:
                maximum_odds = st.number_input(
                    "Maximum HKJC odds",
                    min_value=1.01,
                    value=5.00,
                    step=0.10,
                    format="%.2f",
                    key="ultra_maximum_odds",
                )
            else:
                maximum_odds = 5.00

        with second:
            correct_score_count = (
                st.selectbox(
                    "波膽 reference count",
                    options=[0, 1, 2],
                    index=2,
                    key="ultra_score_count",
                )
            )

        devig_methods = st.multiselect(
            "De-vig scenarios",
            options=[
                "MULTIPLICATIVE",
                "POWER",
            ],
            default=[
                "MULTIPLICATIVE",
                "POWER",
            ],
            key="ultra_devig_methods",
            help=(
                "The methods remain separate. "
                "Ultra uses the conservative range."
            ),
        )

        ev_floor_enabled = st.checkbox(
            "Reject severely underpaid prices",
            value=False,
            key="ultra_enable_ev_floor",
            help=(
                "EV never controls ranking. This "
                "is an optional rejection gate only."
            ),
        )

        if ev_floor_enabled:
            ev_rejection_floor_pct = (
                st.number_input(
                    "Minimum permitted EV (%)",
                    min_value=-100.0,
                    max_value=100.0,
                    value=-10.0,
                    step=1.0,
                    format="%.1f",
                    key="ultra_ev_floor",
                )
            )
        else:
            ev_rejection_floor_pct = -10.0

    run_manual = st.button(
        "🚀 Launch Aegis Ultra",
        type="primary",
        use_container_width=True,
        key="ultra_manual_run",
    )

    if run_manual:
        try:
            input_to_run = build_manual_input(
                home_name=home_name,
                away_name=away_name,
                competition=competition,
                kickoff=kickoff,
                snapshot_time=snapshot_time,
                primary_key=primary_key,
                primary_title=primary_title,
                primary_1x2=primary_1x2,
                primary_ah=primary_ah,
                primary_ou=primary_ou,
                enable_second_source=(
                    enable_second_source
                ),
                second_key=second_key,
                second_title=second_title,
                second_1x2=second_1x2,
                second_ah=second_ah,
                second_ou=second_ou,
                hkjc_1x2=hkjc_1x2,
                hkjc_ah=hkjc_ah,
                hkjc_ou=hkjc_ou,
                minimum_odds=minimum_odds,
                maximum_odds_enabled=(
                    maximum_odds_enabled
                ),
                maximum_odds=maximum_odds,
                maximum_recommendations=(
                    maximum_recommendations
                ),
                minimum_official_hit_pct=(
                    minimum_official_hit_pct
                ),
                correct_score_count=(
                    correct_score_count
                ),
                devig_methods=devig_methods,
                ev_floor_enabled=(
                    ev_floor_enabled
                ),
                ev_rejection_floor_pct=(
                    ev_rejection_floor_pct
                ),
            )

        except Exception as error:
            st.error(
                f"Input error: {error}"
            )
            st.exception(error)


# ============================================================
# 12. JSON text input
# ============================================================

elif input_mode == "📋 Paste JSON":
    st.markdown(
        '<div class="section-label">Direct JSON input</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="glass-card">
            Paste an Ultra input JSON object below.
            This is usually faster than uploading a file.
        </div>
        """,
        unsafe_allow_html=True,
    )

    json_text = st.text_area(
        "Ultra input JSON",
        height=520,
        key="ultra_json_text",
        placeholder="""{
  "match": {
    "home": "Jaro",
    "away": "SJK",
    "competition": "Finland Veikkausliiga"
  },
  "sharp_books": [
    {
      "key": "pinnacle",
      "title": "Pinnacle",
      "markets": {
        "1X2": {
          "home": 3.40,
          "draw": 3.55,
          "away": 2.05
        },
        "AH": [
          {
            "line": 0.25,
            "home": 1.90,
            "away": 2.00
          }
        ],
        "OU": [
          {
            "line": 3.0,
            "over": 1.95,
            "under": 1.95
          },
          {
            "line": 3.5,
            "over": 2.35,
            "under": 1.60
          }
        ]
      }
    }
  ],
  "hkjc_markets": [],
  "settings": {
    "primary_source": "pinnacle",
    "minimum_odds": 1.5,
    "minimum_official_hit_probability": 0.5,
    "max_recommendations": 3,
    "correct_score_count": 2,
    "devig_methods": [
      "MULTIPLICATIVE",
      "POWER"
    ]
  }
}""",
    )

    run_json_text = st.button(
        "🚀 Run pasted JSON",
        type="primary",
        use_container_width=True,
        key="ultra_json_text_run",
    )

    if run_json_text:
        if not json_text.strip():
            st.error(
                "Paste a JSON object first."
            )

        else:
            try:
                parsed = json.loads(
                    json_text
                )

                if not isinstance(
                    parsed,
                    dict,
                ):
                    raise ValueError(
                        "JSON root must be an object."
                    )

                input_to_run = parsed

            except Exception as error:
                st.error(
                    f"JSON error: {error}"
                )
                st.exception(error)


# ============================================================
# 13. JSON upload input
# ============================================================

else:
    st.markdown(
        '<div class="section-label">File input</div>',
        unsafe_allow_html=True,
    )

    uploaded_file = st.file_uploader(
        "Upload Ultra JSON",
        type=["json"],
    )

    run_uploaded = st.button(
        "🚀 Run uploaded JSON",
        type="primary",
        use_container_width=True,
        key="ultra_upload_run",
    )

    if run_uploaded:
        if uploaded_file is None:
            st.error(
                "Upload a JSON file first."
            )

        else:
            try:
                text = (
                    uploaded_file
                    .getvalue()
                    .decode("utf-8-sig")
                )

                parsed = json.loads(text)

                if not isinstance(
                    parsed,
                    dict,
                ):
                    raise ValueError(
                        "JSON root must be an object."
                    )

                input_to_run = parsed

            except Exception as error:
                st.error(
                    f"JSON error: {error}"
                )
                st.exception(error)


# ============================================================
# 14. Execute engine
# ============================================================

if input_to_run is not None:
    try:
        with st.spinner(
            "Reconstructing the sharp market, "
            "removing target lines and checking "
            "official-pick compatibility..."
        ):
            output = execute_engine(
                input_to_run
            )

        st.success(
            "Aegis Ultra completed."
        )

    except Exception as error:
        st.error(
            f"Analysis failed: {error}"
        )
        st.exception(error)


# ============================================================
# 15. Results
# ============================================================

if "ultra_result" in st.session_state:
    output = st.session_state[
        "ultra_result"
    ]

    match = output.get(
        "match",
        {},
    )

    settings = output.get(
        "settings",
        {},
    )

    recommendations = output.get(
        "recommendations",
        [],
    )

    recommendation_set = output.get(
        "recommendation_set",
        {},
    )

    st.divider()

    st.markdown(
        '<div class="section-label">Analysis result</div>',
        unsafe_allow_html=True,
    )

    st.header(
        "📡 "
        + match.get(
            "name",
            "Match analysis",
        )
    )

    caption_parts = [
        match.get("competition"),
        match.get("kickoff"),
    ]

    caption = " ｜ ".join(
        str(item)
        for item in caption_parts
        if item
    )

    if caption:
        st.caption(caption)

    first, second, third, fourth = (
        st.columns(4)
    )

    first.metric(
        "Official picks",
        len(recommendations),
    )

    second.metric(
        "Official hit floor",
        format_probability(
            settings.get(
                "minimum_official_hit_probability"
            )
        ),
    )

    third.metric(
        "全部命中保守概率",
        format_probability(
            recommendation_set
            .get(
                "all_hit_probability",
                {},
            )
            .get("minimum")
        ),
    )

    fourth.metric(
        "至少一項命中保守概率",
        format_probability(
            recommendation_set
            .get(
                "at_least_one_hit_probability",
                {},
            )
            .get("minimum")
        ),
    )

    st.markdown(
        '<div class="section-label">Official recommendations</div>',
        unsafe_allow_html=True,
    )

    if not recommendations:
        st.warning(
            "No line passed the official hit threshold "
            "and compatibility rules. All lines are "
            "still available below for reference."
        )

    for recommendation in recommendations:
        display_official_recommendation(
            recommendation
        )

    if recommendations:
        st.subheader(
            "✅ Official recommendation summary"
        )

        official_table = official_dataframe(
            output
        )

        st.dataframe(
            official_table,
            use_container_width=True,
            hide_index=True,
        )

    st.divider()

    st.markdown(
        '<div class="section-label">Private reference</div>',
        unsafe_allow_html=True,
    )

    st.header("📋 All-line reference summary")

    st.caption(
        "Every HKJC line entered is retained here. "
        "Lines below the hit threshold or blocked for "
        "contradiction remain visible for your own review."
    )

    all_lines_table = all_lines_dataframe(
        output
    )

    if not all_lines_table.empty:
        st.dataframe(
            all_lines_table,
            use_container_width=True,
            hide_index=True,
        )

    with st.expander(
        "Why were reference lines not official?",
        expanded=False,
    ):
        for candidate in output.get(
            "candidate_markets",
            [],
        ):
            if candidate.get("official"):
                continue

            st.markdown(
                f"**{candidate.get('label')}**"
            )

            reasons = (
                candidate.get(
                    "official_exclusion_reasons",
                    [],
                )
                + candidate.get(
                    "exclusion_reasons",
                    [],
                )
            )

            if reasons:
                st.write(
                    ", ".join(reasons)
                )

            conflicts = candidate.get(
                "conflicts_with",
                [],
            )

            if conflicts:
                st.json(conflicts)

    st.divider()

display_correct_scores(output)

display_publishing_centre(output)

st.divider()

runtime = output.get(
        "runtime",
        {},
    )

first, second, third = st.columns(3)

first.metric(
        "Runtime",
        (
            f"{runtime.get('total_seconds', 0):.2f}s"
        ),
    )

second.metric(
        "Score states",
        output.get(
            "model",
            {},
        ).get(
            "state_count",
            0,
        ),
    )

third.metric(
        "Full scenarios",
        output.get(
            "model",
            {},
        ).get(
            "full_scenario_count",
            0,
        ),
    )

    with st.expander(
        "🔬 Internal audit",
        expanded=False,
    ):
        audit_tab_1, audit_tab_2, audit_tab_3 = (
            st.tabs([
                "Methodology",
                "Model scenarios",
                "Recommendation set",
            ])
        )

        with audit_tab_1:
            st.json(
                output.get(
                    "methodology",
                    {},
                )
            )

        with audit_tab_2:
            st.json(
                output.get(
                    "model",
                    {},
                )
            )

        with audit_tab_3:
            st.json(
                output.get(
                    "recommendation_set",
                    {},
                )
            )

    result_json = json.dumps(
        output,
        ensure_ascii=False,
        indent=2,
    )

    input_json = json.dumps(
        st.session_state.get(
            "ultra_input",
            {},
        ),
        ensure_ascii=False,
        indent=2,
    )

    first, second = st.columns(2)

    first.download_button(
        "⬇️ Download Ultra result",
        data=result_json,
        file_name="aegis_ultra_output.json",
        mime="application/json",
        use_container_width=True,
    )

    second.download_button(
        "⬇️ Download Ultra input",
        data=input_json,
        file_name="aegis_ultra_input.json",
        mime="application/json",
        use_container_width=True,
    )
