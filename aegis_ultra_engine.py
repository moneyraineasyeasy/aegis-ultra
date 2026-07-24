from __future__ import annotations

import copy
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from scipy.optimize import least_squares, linprog, minimize
from scipy.special import logsumexp
from scipy.stats import poisson


# ============================================================
# AEGIS ULTRA V1.1
#
# Sharp-market, target-line-out, hit-first engine.
#
# Core design:
# - No historical team data.
# - No arbitrary model weights.
# - No Kelly or EV-based ranking.
# - Multiple sharp-market lines supported.
# - De-vig methods remain separate.
# - Dixon-Coles supplies a football-shaped score prior.
# - Entropy projection reconciles sharp-market constraints.
# - The candidate's own sharp market group is excluded
#   when independently checking that candidate.
# - Official recommendations require a configurable minimum
#   conservative hit probability.
# - Contradictory official picks are never selected together.
# - All candidate lines remain available for private audit.
# - EV is a warning or optional rejection gate only.
# ============================================================


ENGINE_NAME = "Aegis Ultra Hit-First Reconstruction Engine"
ENGINE_VERSION = "1.1.0"

TOL = 1e-10


CONFIG = {
    # Score-grid safeguards.
    "INITIAL_MAX_GOALS": 12,
    "MAX_GOALS_SAFETY": 20,
    "TAIL_TOLERANCE": 1e-8,

    # Solver controls.
    "FIT_MAX_EVALUATIONS": 500,
    "PROJECTION_MAX_ITERATIONS": 1500,
    "PROJECTION_BUFFER": 1e-8,

    # Default de-vig interpretations.
    "DEFAULT_DEVIG_METHODS": (
        "MULTIPLICATIVE",
        "POWER",
    ),

    # Structural requirements.
    "MINIMUM_CONSTRAINTS": 3,
    "MINIMUM_MARKET_GROUPS": 2,

    # Recommendation defaults.
    "DEFAULT_MAX_RECOMMENDATIONS": 3,
    "DEFAULT_CORRECT_SCORE_COUNT": 2,
    "DEFAULT_MINIMUM_OFFICIAL_HIT": 0.50,

    # Price warnings only.
    "POOR_PRICE_EV_WARNING": -0.05,
    "SEVERE_PRICE_EV_WARNING": -0.10,
}


# ============================================================
# 1. Generic utilities
# ============================================================

def to_builtin(value):
    if isinstance(value, dict):
        return {
            str(key): to_builtin(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [
            to_builtin(item)
            for item in value
        ]

    if isinstance(value, np.ndarray):
        return value.tolist()

    if isinstance(value, np.floating):
        return float(value)

    if isinstance(value, np.integer):
        return int(value)

    if isinstance(value, np.bool_):
        return bool(value)

    return value


def clamp(value, minimum, maximum):
    return max(
        minimum,
        min(maximum, value),
    )


def sigmoid(value):
    value = float(value)

    if value >= 0:
        exponential = math.exp(-value)
        return 1.0 / (1.0 + exponential)

    exponential = math.exp(value)
    return exponential / (1.0 + exponential)


def safe_float(
    value,
    default=None,
):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return default

    if not math.isfinite(value):
        return default

    return value


def summary_statistics(values):
    values = np.asarray(
        list(values),
        dtype=float,
    )

    values = values[
        np.isfinite(values)
    ]

    if len(values) == 0:
        return {
            "minimum": None,
            "median": None,
            "maximum": None,
            "count": 0,
        }

    return {
        "minimum": float(
            np.min(values)
        ),
        "median": float(
            np.median(values)
        ),
        "maximum": float(
            np.max(values)
        ),
        "count": int(len(values)),
    }


def validate_odds(
    value,
    label="Odds",
):
    try:
        value = float(value)
    except (TypeError, ValueError):
        raise ValueError(
            f"{label} must be numeric."
        )

    if (
        not math.isfinite(value)
        or value <= 1.0
    ):
        raise ValueError(
            f"{label} must exceed 1.00."
        )

    return value


def validate_quarter_line(
    value,
    label="Line",
):
    try:
        value = float(value)
    except (TypeError, ValueError):
        raise ValueError(
            f"{label} must be numeric."
        )

    if not math.isfinite(value):
        raise ValueError(
            f"{label} must be finite."
        )

    units = value * 4.0

    if not math.isclose(
        units,
        round(units),
        abs_tol=1e-8,
    ):
        raise ValueError(
            f"{label} must be a multiple of 0.25."
        )

    return round(units) / 4.0


def split_quarter_line(line):
    line = validate_quarter_line(line)
    units = int(round(line * 4.0))

    if abs(units) % 2 == 1:
        return [
            line - 0.25,
            line + 0.25,
        ]

    return [line]


def normalize_market(value):
    market = str(
        value
    ).strip().upper()

    aliases = {
        "H2H": "1X2",
        "3WAY": "1X2",
        "HAD": "1X2",
        "SPREAD": "AH",
        "SPREADS": "AH",
        "HANDICAP": "AH",
        "ASIAN_HANDICAP": "AH",
        "TOTAL": "OU",
        "TOTALS": "OU",
        "OVER_UNDER": "OU",
    }

    market = aliases.get(
        market,
        market,
    )

    if market not in {
        "1X2",
        "AH",
        "OU",
    }:
        raise ValueError(
            f"Unsupported market: {market}"
        )

    return market


def normalize_selection(
    market,
    selection,
):
    market = normalize_market(market)

    selection = str(
        selection
    ).strip().upper()

    aliases = {
        "H": "HOME",
        "HOME": "HOME",
        "HOME_WIN": "HOME",

        "D": "DRAW",
        "DRAW": "DRAW",
        "X": "DRAW",

        "A": "AWAY",
        "AWAY": "AWAY",
        "AWAY_WIN": "AWAY",

        "O": "OVER",
        "OVER": "OVER",

        "U": "UNDER",
        "UNDER": "UNDER",
    }

    selection = aliases.get(
        selection,
        selection,
    )

    if market == "1X2":
        allowed = {
            "HOME",
            "DRAW",
            "AWAY",
        }

    elif market == "AH":
        allowed = {
            "HOME",
            "AWAY",
        }

    else:
        allowed = {
            "OVER",
            "UNDER",
        }

    if selection not in allowed:
        raise ValueError(
            f"Invalid {market} selection: "
            f"{selection}"
        )

    return selection


def candidate_key(
    market,
    selection,
    line=None,
):
    market = normalize_market(market)

    selection = normalize_selection(
        market,
        selection,
    )

    line_key = (
        None
        if line is None
        else round(float(line), 4)
    )

    return (
        market,
        selection,
        line_key,
    )


def market_group_key(
    market,
    line=None,
):
    market = normalize_market(market)

    if market == "1X2":
        return "1X2"

    if line is None:
        raise ValueError(
            f"{market} requires a line."
        )

    return (
        f"{market}:"
        f"{float(line):+.4f}"
    )


def score_arrays(max_goals):
    home, away = np.indices(
        (
            max_goals + 1,
            max_goals + 1,
        )
    )

    return (
        home.ravel().astype(float),
        away.ravel().astype(float),
    )


# ============================================================
# 2. Exact football settlement
#
# Gross payout per unit stake:
#
#     payout = A * odds + B
#
# Full win  : A=1.0, B=0.0
# Half win  : A=0.5, B=0.5
# Push      : A=0.0, B=1.0
# Half loss : A=0.0, B=0.5
# Full loss : A=0.0, B=0.0
# ============================================================

def settlement_coefficients(
    home_scores,
    away_scores,
    market,
    selection,
    line=None,
):
    market = normalize_market(market)

    selection = normalize_selection(
        market,
        selection,
    )

    home_scores = np.asarray(
        home_scores,
        dtype=float,
    )

    away_scores = np.asarray(
        away_scores,
        dtype=float,
    )

    if (
        home_scores.shape
        != away_scores.shape
    ):
        raise ValueError(
            "Score arrays must have "
            "identical shapes."
        )

    a_coeff = np.zeros(
        home_scores.shape,
        dtype=float,
    )

    b_coeff = np.zeros(
        home_scores.shape,
        dtype=float,
    )

    if market == "1X2":
        if selection == "HOME":
            wins = (
                home_scores > away_scores
            )

        elif selection == "DRAW":
            wins = (
                home_scores == away_scores
            )

        else:
            wins = (
                home_scores < away_scores
            )

        a_coeff[wins] = 1.0
        return a_coeff, b_coeff

    if line is None:
        raise ValueError(
            f"{market} requires a line."
        )

    component_lines = split_quarter_line(
        line
    )

    component_weight = (
        1.0 / len(component_lines)
    )

    for component_line in component_lines:
        if market == "AH":
            adjusted_margin = (
                home_scores
                - away_scores
                + component_line
            )

            if selection == "HOME":
                wins = (
                    adjusted_margin > TOL
                )
            else:
                wins = (
                    adjusted_margin < -TOL
                )

            pushes = (
                np.abs(
                    adjusted_margin
                )
                <= TOL
            )

        else:
            difference = (
                home_scores
                + away_scores
                - component_line
            )

            if selection == "OVER":
                wins = (
                    difference > TOL
                )
            else:
                wins = (
                    difference < -TOL
                )

            pushes = (
                np.abs(difference)
                <= TOL
            )

        a_coeff[wins] += (
            component_weight
        )

        b_coeff[pushes] += (
            component_weight
        )

    return a_coeff, b_coeff


def classify_settlement(
    a_coeff,
    b_coeff,
):
    a_coeff = np.asarray(
        a_coeff,
        dtype=float,
    )

    b_coeff = np.asarray(
        b_coeff,
        dtype=float,
    )

    return {
        "full_win": (
            np.isclose(a_coeff, 1.0)
            & np.isclose(b_coeff, 0.0)
        ),
        "half_win": (
            np.isclose(a_coeff, 0.5)
            & np.isclose(b_coeff, 0.5)
        ),
        "push": (
            np.isclose(a_coeff, 0.0)
            & np.isclose(b_coeff, 1.0)
        ),
        "half_loss": (
            np.isclose(a_coeff, 0.0)
            & np.isclose(b_coeff, 0.5)
        ),
        "full_loss": (
            np.isclose(a_coeff, 0.0)
            & np.isclose(b_coeff, 0.0)
        ),
    }


def effective_fair_probability(
    probabilities,
    a_coeff,
    b_coeff,
):
    probabilities = np.asarray(
        probabilities,
        dtype=float,
    )

    expected_a = float(
        probabilities @ a_coeff
    )

    expected_b = float(
        probabilities @ b_coeff
    )

    denominator = (
        1.0 - expected_b
    )

    if denominator <= TOL:
        return 0.0

    return (
        expected_a / denominator
    )


def candidate_metrics(
    probabilities,
    a_coeff,
    b_coeff,
    odds,
):
    probabilities = np.asarray(
        probabilities,
        dtype=float,
    )

    odds = validate_odds(odds)

    categories = classify_settlement(
        a_coeff,
        b_coeff,
    )

    category_probabilities = {
        name: float(
            probabilities
            @ mask.astype(float)
        )
        for name, mask
        in categories.items()
    }

    payout = (
        a_coeff * odds
        + b_coeff
    )

    profit = payout - 1.0

    hit_mask = (
        profit > TOL
    )

    nonloss_mask = (
        profit >= -TOL
    )

    loss_mask = (
        profit < -TOL
    )

    expected_return = float(
        probabilities @ profit
    )

    expected_a = float(
        probabilities @ a_coeff
    )

    expected_b = float(
        probabilities @ b_coeff
    )

    fair_odds = (
        (1.0 - expected_b)
        / expected_a
        if expected_a > TOL
        else None
    )

    return {
        "hit_probability": float(
            probabilities
            @ hit_mask.astype(float)
        ),
        "nonloss_probability": float(
            probabilities
            @ nonloss_mask.astype(float)
        ),
        "loss_probability": float(
            probabilities
            @ loss_mask.astype(float)
        ),
        "expected_return": (
            expected_return
        ),
        "effective_fair_probability": (
            effective_fair_probability(
                probabilities,
                a_coeff,
                b_coeff,
            )
        ),
        "fair_odds": fair_odds,
        **category_probabilities,
    }


# ============================================================
# 3. De-vigging
# ============================================================

def multiplicative_devig(odds):
    odds = np.asarray(
        [
            validate_odds(
                value,
                f"Odds #{index + 1}",
            )
            for index, value
            in enumerate(odds)
        ],
        dtype=float,
    )

    inverse = 1.0 / odds

    return (
        inverse / inverse.sum()
    )


def power_devig(odds):
    odds = np.asarray(
        [
            validate_odds(
                value,
                f"Odds #{index + 1}",
            )
            for index, value
            in enumerate(odds)
        ],
        dtype=float,
    )

    inverse = 1.0 / odds

    def equation(power):
        return float(
            np.sum(
                inverse ** power
            )
            - 1.0
        )

    lower = 1e-8
    upper = 100.0

    while (
        equation(upper) >= 0
        and upper < 100000
    ):
        upper *= 2.0

    if equation(upper) >= 0:
        raise RuntimeError(
            "Power de-vig root "
            "was not found."
        )

    for _ in range(220):
        middle = (
            lower + upper
        ) / 2.0

        if equation(middle) > 0:
            lower = middle
        else:
            upper = middle

    power = (
        lower + upper
    ) / 2.0

    probabilities = (
        inverse ** power
    )

    probabilities /= (
        probabilities.sum()
    )

    return probabilities


def devig_probabilities(
    odds,
    method,
):
    method = str(
        method
    ).strip().upper()

    if method == "MULTIPLICATIVE":
        return multiplicative_devig(
            odds
        )

    if method == "POWER":
        return power_devig(
            odds
        )

    raise ValueError(
        f"Unsupported de-vig method: "
        f"{method}"
    )


# ============================================================
# 4. Input normalization
# ============================================================

def normalize_one_x_two(
    raw,
    label,
):
    if not isinstance(raw, dict):
        raise ValueError(
            f"{label} must be an object."
        )

    home = (
        raw.get("home")
        if raw.get("home") is not None
        else raw.get("H")
    )

    draw = (
        raw.get("draw")
        if raw.get("draw") is not None
        else raw.get("D")
    )

    away = (
        raw.get("away")
        if raw.get("away") is not None
        else raw.get("A")
    )

    return {
        "home": validate_odds(
            home,
            f"{label} home",
        ),
        "draw": validate_odds(
            draw,
            f"{label} draw",
        ),
        "away": validate_odds(
            away,
            f"{label} away",
        ),
    }


def normalize_ah_rows(
    rows,
    label,
):
    if rows is None:
        return []

    if not isinstance(rows, list):
        raise ValueError(
            f"{label} must be a list."
        )

    output = []
    seen_lines = set()

    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(
                f"{label} row {index + 1} "
                "must be an object."
            )

        line = validate_quarter_line(
            row.get("line"),
            (
                f"{label} row "
                f"{index + 1} line"
            ),
        )

        if line in seen_lines:
            raise ValueError(
                f"{label} contains duplicate "
                f"line {line:g}."
            )

        seen_lines.add(line)

        output.append({
            "line": line,
            "home": validate_odds(
                row.get("home"),
                f"{label} {line:g} home",
            ),
            "away": validate_odds(
                row.get("away"),
                f"{label} {line:g} away",
            ),
        })

    return sorted(
        output,
        key=lambda item: item["line"],
    )


def normalize_ou_rows(
    rows,
    label,
):
    if rows is None:
        return []

    if not isinstance(rows, list):
        raise ValueError(
            f"{label} must be a list."
        )

    output = []
    seen_lines = set()

    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(
                f"{label} row {index + 1} "
                "must be an object."
            )

        line = validate_quarter_line(
            row.get("line"),
            (
                f"{label} row "
                f"{index + 1} line"
            ),
        )

        if line in seen_lines:
            raise ValueError(
                f"{label} contains duplicate "
                f"line {line:g}."
            )

        seen_lines.add(line)

        output.append({
            "line": line,
            "over": validate_odds(
                row.get("over"),
                f"{label} {line:g} over",
            ),
            "under": validate_odds(
                row.get("under"),
                f"{label} {line:g} under",
            ),
        })

    return sorted(
        output,
        key=lambda item: item["line"],
    )


def legacy_pinnacle_to_sharp_books(
    pinnacle,
):
    if not isinstance(pinnacle, dict):
        raise ValueError(
            "Pinnacle input must be an object."
        )

    if "FT" in pinnacle:
        ft = pinnacle.get("FT", {})
    else:
        ft = pinnacle

    one_x_two_raw = ft.get("1X2")

    if not isinstance(
        one_x_two_raw,
        dict,
    ):
        raise ValueError(
            "Legacy Pinnacle FT 1X2 "
            "input is required."
        )

    return [{
        "key": "pinnacle",
        "title": "Pinnacle",
        "markets": {
            "1X2": {
                "home": one_x_two_raw.get(
                    "H",
                    one_x_two_raw.get(
                        "home"
                    ),
                ),
                "draw": one_x_two_raw.get(
                    "D",
                    one_x_two_raw.get(
                        "draw"
                    ),
                ),
                "away": one_x_two_raw.get(
                    "A",
                    one_x_two_raw.get(
                        "away"
                    ),
                ),
            },
            "AH": copy.deepcopy(
                ft.get("AH", [])
            ),
            "OU": copy.deepcopy(
                ft.get("OU", [])
            ),
        },
    }]


def normalize_sharp_books(data):
    sharp_books = data.get(
        "sharp_books"
    )

    if sharp_books is None:
        pinnacle = data.get(
            "pinnacle"
        )

        if pinnacle is None:
            raise ValueError(
                "Provide sharp_books or "
                "legacy pinnacle input."
            )

        sharp_books = (
            legacy_pinnacle_to_sharp_books(
                pinnacle
            )
        )

    if (
        not isinstance(sharp_books, list)
        or not sharp_books
    ):
        raise ValueError(
            "sharp_books must be a "
            "non-empty list."
        )

    output = []
    seen_keys = set()

    for index, raw_book in enumerate(
        sharp_books
    ):
        if not isinstance(
            raw_book,
            dict,
        ):
            raise ValueError(
                f"Sharp book #{index + 1} "
                "must be an object."
            )

        key = str(
            raw_book.get(
                "key",
                f"source_{index + 1}",
            )
        ).strip().lower()

        if not key:
            raise ValueError(
                f"Sharp book #{index + 1} "
                "requires a key."
            )

        if key in seen_keys:
            raise ValueError(
                f"Duplicate sharp source: "
                f"{key}"
            )

        seen_keys.add(key)

        title = str(
            raw_book.get(
                "title",
                key,
            )
        ).strip()

        markets = raw_book.get(
            "markets",
            raw_book,
        )

        if not isinstance(
            markets,
            dict,
        ):
            raise ValueError(
                f"{title} markets must "
                "be an object."
            )

        one_x_two = normalize_one_x_two(
            markets.get("1X2"),
            f"{title} 1X2",
        )

        ah_rows = normalize_ah_rows(
            markets.get("AH", []),
            f"{title} AH",
        )

        ou_rows = normalize_ou_rows(
            markets.get("OU", []),
            f"{title} O/U",
        )

        if not ah_rows and not ou_rows:
            raise ValueError(
                f"{title} requires at least "
                "one AH or O/U line."
            )

        output.append({
            "key": key,
            "title": title,
            "timestamp": raw_book.get(
                "timestamp"
            ),
            "markets": {
                "1X2": one_x_two,
                "AH": ah_rows,
                "OU": ou_rows,
            },
        })

    return output


def default_candidate_label(
    match,
    market,
    selection,
    line,
):
    home = match["home"]
    away = match["away"]

    if market == "1X2":
        if selection == "HOME":
            return f"{home} 全場勝"

        if selection == "DRAW":
            return "全場和"

        return f"{away} 全場勝"

    if market == "AH":
        if selection == "HOME":
            return (
                f"{home} "
                f"{float(line):+g}"
            )

        return (
            f"{away} "
            f"{-float(line):+g}"
        )

    side = (
        "大"
        if selection == "OVER"
        else "細"
    )

    return (
        f"全場入球 {side} "
        f"{float(line):g}"
    )


def normalize_hkjc_markets(
    raw_markets,
    match,
):
    if (
        not isinstance(raw_markets, list)
        or not raw_markets
    ):
        raise ValueError(
            "At least one HKJC candidate "
            "market is required."
        )

    output = []
    seen_ids = set()

    for index, raw in enumerate(
        raw_markets
    ):
        if not isinstance(raw, dict):
            raise ValueError(
                f"HKJC market #{index + 1} "
                "must be an object."
            )

        period = str(
            raw.get("period", "FT")
        ).strip().upper()

        if period != "FT":
            raise ValueError(
                "Ultra V1 currently supports "
                "FT markets only."
            )

        market = normalize_market(
            raw.get("market")
        )

        selection = normalize_selection(
            market,
            raw.get("selection"),
        )

        if market in {"AH", "OU"}:
            line = validate_quarter_line(
                raw.get("line"),
                (
                    f"HKJC market "
                    f"#{index + 1} line"
                ),
            )
        else:
            line = None

        market_id = str(
            raw.get(
                "id",
                f"M{index + 1:03d}",
            )
        ).strip()

        if market_id in seen_ids:
            raise ValueError(
                f"Duplicate HKJC market ID: "
                f"{market_id}"
            )

        seen_ids.add(market_id)

        odds = validate_odds(
            raw.get("odds"),
            f"HKJC {market_id}",
        )

        label = str(
            raw.get(
                "label",
                default_candidate_label(
                    match,
                    market,
                    selection,
                    line,
                ),
            )
        ).strip()

        output.append({
            "id": market_id,
            "label": label,
            "period": "FT",
            "market": market,
            "selection": selection,
            "line": line,
            "odds": odds,
            "candidate_key": candidate_key(
                market,
                selection,
                line,
            ),
            "group_key": market_group_key(
                market,
                line,
            ),
            "original_index": index,
        })

    return output


def validate_input_data(input_data):
    if not isinstance(input_data, dict):
        raise ValueError(
            "Input must be an object."
        )

    data = copy.deepcopy(
        input_data
    )

    match_raw = data.get(
        "match",
        {},
    )

    if not isinstance(
        match_raw,
        dict,
    ):
        raise ValueError(
            "match must be an object."
        )

    home = str(
        match_raw.get("home", "")
    ).strip()

    away = str(
        match_raw.get("away", "")
    ).strip()

    if not home or not away:
        raise ValueError(
            "Home and away teams are required."
        )

    if (
        home.casefold()
        == away.casefold()
    ):
        raise ValueError(
            "Home and away teams cannot match."
        )

    match = {
        "name": str(
            match_raw.get(
                "name",
                f"{home} vs {away}",
            )
        ).strip(),
        "home": home,
        "away": away,
        "competition": str(
            match_raw.get(
                "competition",
                "",
            )
        ).strip(),
        "kickoff": str(
            match_raw.get(
                "kickoff",
                "",
            )
        ).strip(),
        "snapshot_time": str(
            match_raw.get(
                "snapshot_time",
                "",
            )
        ).strip(),
    }

    sharp_books = normalize_sharp_books(
        data
    )

    markets = normalize_hkjc_markets(
        data.get("hkjc_markets"),
        match,
    )

    settings_raw = data.get(
        "settings",
        {},
    )

    if not isinstance(
        settings_raw,
        dict,
    ):
        raise ValueError(
            "settings must be an object."
        )

    minimum_odds = validate_odds(
        settings_raw.get(
            "minimum_odds",
            1.50,
        ),
        "Minimum HKJC odds",
    )

    maximum_odds_raw = (
        settings_raw.get(
            "maximum_odds"
        )
    )

    maximum_odds = (
        None
        if maximum_odds_raw in {
            None,
            "",
        }
        else validate_odds(
            maximum_odds_raw,
            "Maximum HKJC odds",
        )
    )

    if (
        maximum_odds is not None
        and maximum_odds < minimum_odds
    ):
        raise ValueError(
            "Maximum odds cannot be below "
            "minimum odds."
        )

    maximum_recommendations = int(
        settings_raw.get(
            "max_recommendations",
            CONFIG[
                "DEFAULT_MAX_RECOMMENDATIONS"
            ],
        )
    )

    if not (
        1
        <= maximum_recommendations
        <= 10
    ):
        raise ValueError(
            "Maximum recommendations must "
            "be between 1 and 10."
        )

    minimum_official_hit_probability = float(
        settings_raw.get(
            "minimum_official_hit_probability",
            CONFIG[
                "DEFAULT_MINIMUM_OFFICIAL_HIT"
            ],
        )
    )

    if not math.isfinite(
        minimum_official_hit_probability
    ):
        raise ValueError(
            "Minimum official hit probability "
            "must be finite."
        )

    if not (
        0.0
        <= minimum_official_hit_probability
        <= 1.0
    ):
        raise ValueError(
            "Minimum official hit probability "
            "must be between 0 and 1."
        )

    correct_score_count = int(
        settings_raw.get(
            "correct_score_count",
            CONFIG[
                "DEFAULT_CORRECT_SCORE_COUNT"
            ],
        )
    )

    if not (
        0 <= correct_score_count <= 5
    ):
        raise ValueError(
            "Correct-score count must "
            "be between 0 and 5."
        )

    devig_methods_raw = (
        settings_raw.get(
            "devig_methods",
            CONFIG[
                "DEFAULT_DEVIG_METHODS"
            ],
        )
    )

    if isinstance(
        devig_methods_raw,
        str,
    ):
        devig_methods_raw = [
            item.strip()
            for item
            in devig_methods_raw.split(",")
            if item.strip()
        ]

    devig_methods = tuple(
        dict.fromkeys(
            str(item).strip().upper()
            for item in devig_methods_raw
        )
    )

    if not devig_methods:
        raise ValueError(
            "At least one de-vig method "
            "is required."
        )

    for method in devig_methods:
        if method not in {
            "MULTIPLICATIVE",
            "POWER",
        }:
            raise ValueError(
                f"Unsupported de-vig method: "
                f"{method}"
            )

    primary_source = str(
        settings_raw.get(
            "primary_source",
            sharp_books[0]["key"],
        )
    ).strip().lower()

    available_keys = {
        book["key"]
        for book in sharp_books
    }

    if primary_source not in available_keys:
        raise ValueError(
            f"Primary source "
            f"{primary_source!r} "
            "was not supplied."
        )

    ev_rejection_floor_raw = (
        settings_raw.get(
            "ev_rejection_floor"
        )
    )

    if ev_rejection_floor_raw in {
        None,
        "",
    }:
        ev_rejection_floor = None

    else:
        ev_rejection_floor = float(
            ev_rejection_floor_raw
        )

        if not math.isfinite(
            ev_rejection_floor
        ):
            raise ValueError(
                "EV rejection floor must "
                "be finite."
            )

        if ev_rejection_floor < -1.0:
            raise ValueError(
                "EV rejection floor cannot "
                "be below -1.00."
            )

    return {
        "match": match,
        "sharp_books": sharp_books,
        "hkjc_markets": markets,
        "settings": {
            "minimum_odds": (
                minimum_odds
            ),
            "maximum_odds": (
                maximum_odds
            ),
            "max_recommendations": (
                maximum_recommendations
            ),
            "minimum_official_hit_probability": (
                minimum_official_hit_probability
            ),
            "correct_score_count": (
                correct_score_count
            ),
            "devig_methods": list(
                devig_methods
            ),
            "primary_source": (
                primary_source
            ),
            "ev_rejection_floor": (
                ev_rejection_floor
            ),
        },
    }


# ============================================================
# 5. Sharp-market constraints
# ============================================================

def build_book_constraints(
    book,
    devig_method,
):
    constraints = []
    markets = book["markets"]

    def add_constraint(
        market,
        selection,
        line,
        target,
        odds,
    ):
        group_key = market_group_key(
            market,
            line,
        )

        constraints.append({
            "market": market,
            "selection": selection,
            "line": line,
            "group_key": group_key,
            "candidate_key": candidate_key(
                market,
                selection,
                line,
            ),
            "target": float(target),
            "odds": float(odds),
        })

    one_x_two = markets["1X2"]

    one_x_two_odds = [
        one_x_two["home"],
        one_x_two["draw"],
        one_x_two["away"],
    ]

    one_x_two_probabilities = (
        devig_probabilities(
            one_x_two_odds,
            devig_method,
        )
    )

    for selection, target, odds in zip(
        [
            "HOME",
            "DRAW",
            "AWAY",
        ],
        one_x_two_probabilities,
        one_x_two_odds,
    ):
        add_constraint(
            "1X2",
            selection,
            None,
            target,
            odds,
        )

    for row in markets["AH"]:
        line = float(
            row["line"]
        )

        odds = [
            row["home"],
            row["away"],
        ]

        probabilities = (
            devig_probabilities(
                odds,
                devig_method,
            )
        )

        add_constraint(
            "AH",
            "HOME",
            line,
            probabilities[0],
            odds[0],
        )

        add_constraint(
            "AH",
            "AWAY",
            line,
            probabilities[1],
            odds[1],
        )

    for row in markets["OU"]:
        line = float(
            row["line"]
        )

        odds = [
            row["over"],
            row["under"],
        ]

        probabilities = (
            devig_probabilities(
                odds,
                devig_method,
            )
        )

        add_constraint(
            "OU",
            "OVER",
            line,
            probabilities[0],
            odds[0],
        )

        add_constraint(
            "OU",
            "UNDER",
            line,
            probabilities[1],
            odds[1],
        )

    return constraints


def constraint_group_count(
    constraints,
):
    return len({
        item["group_key"]
        for item in constraints
    })


def validate_constraint_subset(
    constraints,
):
    if (
        len(constraints)
        < CONFIG[
            "MINIMUM_CONSTRAINTS"
        ]
    ):
        return False

    if (
        constraint_group_count(
            constraints
        )
        < CONFIG[
            "MINIMUM_MARKET_GROUPS"
        ]
    ):
        return False

    markets = {
        item["market"]
        for item in constraints
    }

    return len(markets) >= 2


# ============================================================
# 6. Dixon-Coles score prior
# ============================================================

def legal_rho_bounds(
    lambda_home,
    lambda_away,
):
    epsilon = 1e-8

    lower = max(
        -0.30,
        -1.0 / lambda_home + epsilon,
        -1.0 / lambda_away + epsilon,
    )

    upper = min(
        0.30,
        (
            1.0
            / (
                lambda_home
                * lambda_away
            )
        )
        - epsilon,
        1.0 - epsilon,
    )

    if lower >= upper:
        raise ValueError(
            "No legal Dixon-Coles "
            "rho interval."
        )

    return lower, upper


def decode_rho(
    lambda_home,
    lambda_away,
    raw_parameter,
):
    lower, upper = legal_rho_bounds(
        lambda_home,
        lambda_away,
    )

    return (
        lower
        + sigmoid(raw_parameter)
        * (upper - lower)
    )


def dixon_coles_distribution(
    lambda_home,
    lambda_away,
    rho,
    max_goals,
):
    values = np.arange(
        max_goals + 1
    )

    home_probability = poisson.pmf(
        values,
        lambda_home,
    )

    away_probability = poisson.pmf(
        values,
        lambda_away,
    )

    matrix = np.outer(
        home_probability,
        away_probability,
    )

    tau_00 = (
        1.0
        - lambda_home
        * lambda_away
        * rho
    )

    tau_10 = (
        1.0
        + lambda_away * rho
    )

    tau_01 = (
        1.0
        + lambda_home * rho
    )

    tau_11 = (
        1.0 - rho
    )

    if min(
        tau_00,
        tau_10,
        tau_01,
        tau_11,
    ) <= 0:
        raise ValueError(
            "Illegal Dixon-Coles "
            "low-score adjustment."
        )

    matrix[0, 0] *= tau_00
    matrix[1, 0] *= tau_10
    matrix[0, 1] *= tau_01
    matrix[1, 1] *= tau_11

    matrix /= matrix.sum()

    return matrix.ravel()


def enrich_constraints(
    constraints,
    max_goals,
):
    home_scores, away_scores = (
        score_arrays(max_goals)
    )

    enriched = []
    matrix_rows = []
    targets = []

    for constraint in constraints:
        a_coeff, b_coeff = (
            settlement_coefficients(
                home_scores,
                away_scores,
                constraint["market"],
                constraint["selection"],
                constraint["line"],
            )
        )

        target = float(
            constraint["target"]
        )

        item = dict(
            constraint
        )

        item["a_coeff"] = a_coeff
        item["b_coeff"] = b_coeff

        enriched.append(item)

        matrix_rows.append(
            a_coeff
            + target * b_coeff
        )

        targets.append(target)

    return (
        enriched,
        np.vstack(
            matrix_rows
        ).astype(float),
        np.asarray(
            targets,
            dtype=float,
        ),
    )


def fit_dixon_coles_prior(
    constraints,
    max_goals,
):
    enriched, _, _ = (
        enrich_constraints(
            constraints,
            max_goals,
        )
    )

    def residuals(parameters):
        try:
            lambda_home = math.exp(
                float(parameters[0])
            )

            lambda_away = math.exp(
                float(parameters[1])
            )

            rho = decode_rho(
                lambda_home,
                lambda_away,
                parameters[2],
            )

            probabilities = (
                dixon_coles_distribution(
                    lambda_home,
                    lambda_away,
                    rho,
                    max_goals,
                )
            )

            return np.asarray([
                (
                    effective_fair_probability(
                        probabilities,
                        item["a_coeff"],
                        item["b_coeff"],
                    )
                    - item["target"]
                )
                for item in enriched
            ])

        except Exception:
            return np.full(
                len(enriched),
                100.0,
                dtype=float,
            )

    starts = [
        (1.10, 1.10),
        (1.50, 0.90),
        (0.90, 1.50),
        (1.90, 1.20),
        (1.20, 1.90),
    ]

    results = []

    lower_bounds = np.asarray([
        math.log(0.03),
        math.log(0.03),
        -10.0,
    ])

    upper_bounds = np.asarray([
        math.log(8.0),
        math.log(8.0),
        10.0,
    ])

    for home_start, away_start in starts:
        result = least_squares(
            residuals,
            x0=np.asarray([
                math.log(home_start),
                math.log(away_start),
                0.0,
            ]),
            bounds=(
                lower_bounds,
                upper_bounds,
            ),
            method="trf",
            max_nfev=CONFIG[
                "FIT_MAX_EVALUATIONS"
            ],
            ftol=1e-11,
            xtol=1e-11,
            gtol=1e-11,
        )

        if np.all(
            np.isfinite(result.fun)
        ):
            results.append(result)

    if not results:
        raise RuntimeError(
            "Dixon-Coles prior fitting failed."
        )

    best = min(
        results,
        key=lambda item: (
            float(
                np.max(
                    np.abs(item.fun)
                )
            ),
            float(
                np.mean(
                    item.fun ** 2
                )
            ),
        ),
    )

    lambda_home = math.exp(
        float(best.x[0])
    )

    lambda_away = math.exp(
        float(best.x[1])
    )

    rho = decode_rho(
        lambda_home,
        lambda_away,
        best.x[2],
    )

    probabilities = (
        dixon_coles_distribution(
            lambda_home,
            lambda_away,
            rho,
            max_goals,
        )
    )

    return {
        "lambda_home": lambda_home,
        "lambda_away": lambda_away,
        "rho": rho,
        "probabilities": probabilities,
        "maximum_prior_residual": float(
            np.max(
                np.abs(best.fun)
            )
        ),
        "prior_rmse": float(
            math.sqrt(
                np.mean(
                    best.fun ** 2
                )
            )
        ),
        "optimizer_success": bool(
            best.success
        ),
        "optimizer_message": str(
            best.message
        ),
    }


# ============================================================
# 7. Market reconciliation
# ============================================================

def solve_minimum_slack(
    matrix,
    targets,
):
    matrix = np.asarray(
        matrix,
        dtype=float,
    )

    targets = np.asarray(
        targets,
        dtype=float,
    )

    quote_count, state_count = (
        matrix.shape
    )

    objective = np.zeros(
        state_count + 1,
        dtype=float,
    )

    objective[-1] = 1.0

    positive = np.hstack([
        matrix,
        -np.ones(
            (quote_count, 1),
            dtype=float,
        ),
    ])

    negative = np.hstack([
        -matrix,
        -np.ones(
            (quote_count, 1),
            dtype=float,
        ),
    ])

    equality = np.zeros(
        (1, state_count + 1),
        dtype=float,
    )

    equality[
        0,
        :state_count
    ] = 1.0

    result = linprog(
        c=objective,
        A_ub=np.vstack([
            positive,
            negative,
        ]),
        b_ub=np.concatenate([
            targets,
            -targets,
        ]),
        A_eq=equality,
        b_eq=np.asarray(
            [1.0],
            dtype=float,
        ),
        bounds=(
            [(0.0, 1.0)]
            * state_count
            + [(0.0, None)]
        ),
        method="highs",
    )

    if not result.success:
        raise RuntimeError(
            "Minimum-slack market LP failed: "
            f"{result.message}"
        )

    fallback = np.asarray(
        result.x[:state_count],
        dtype=float,
    )

    fallback = np.maximum(
        fallback,
        0.0,
    )

    fallback /= fallback.sum()

    return {
        "minimum_slack": float(
            result.x[-1]
        ),
        "fallback_probabilities": (
            fallback
        ),
        "solver_message": str(
            result.message
        ),
    }


def entropy_projection(
    prior,
    matrix,
    targets,
):
    prior = np.asarray(
        prior,
        dtype=float,
    )

    prior = np.maximum(
        prior,
        1e-300,
    )

    prior /= prior.sum()

    matrix = np.asarray(
        matrix,
        dtype=float,
    )

    targets = np.asarray(
        targets,
        dtype=float,
    )

    slack_result = solve_minimum_slack(
        matrix,
        targets,
    )

    minimum_slack = slack_result[
        "minimum_slack"
    ]

    allowed_slack = (
        minimum_slack
        + CONFIG[
            "PROJECTION_BUFFER"
        ]
    )

    lower = (
        targets - allowed_slack
    )

    upper = (
        targets + allowed_slack
    )

    inequality_matrix = np.vstack([
        matrix,
        -matrix,
    ])

    inequality_bound = np.concatenate([
        upper,
        -lower,
    ])

    log_prior = np.log(prior)

    def objective_and_gradient(
        multipliers,
    ):
        transformed = (
            log_prior
            - inequality_matrix.T
            @ multipliers
        )

        log_normalizer = logsumexp(
            transformed
        )

        probabilities = np.exp(
            transformed
            - log_normalizer
        )

        objective = (
            log_normalizer
            + inequality_bound
            @ multipliers
        )

        gradient = (
            inequality_bound
            - inequality_matrix
            @ probabilities
        )

        return (
            float(objective),
            np.asarray(
                gradient,
                dtype=float,
            ),
        )

    initial = np.zeros(
        len(inequality_bound),
        dtype=float,
    )

    result = minimize(
        fun=lambda values: (
            objective_and_gradient(
                values
            )[0]
        ),
        x0=initial,
        jac=lambda values: (
            objective_and_gradient(
                values
            )[1]
        ),
        method="L-BFGS-B",
        bounds=[
            (0.0, None)
            for _ in initial
        ],
        options={
            "maxiter": CONFIG[
                "PROJECTION_MAX_ITERATIONS"
            ],
            "ftol": 1e-12,
            "gtol": 1e-9,
            "maxls": 40,
        },
    )

    transformed = (
        log_prior
        - inequality_matrix.T
        @ result.x
    )

    probabilities = np.exp(
        transformed
        - logsumexp(transformed)
    )

    probabilities /= (
        probabilities.sum()
    )

    residual = float(
        np.max(
            np.abs(
                matrix @ probabilities
                - targets
            )
        )
    )

    if (
        not result.success
        or np.any(
            ~np.isfinite(
                probabilities
            )
        )
        or residual
        > allowed_slack + 1e-6
    ):
        probabilities = (
            slack_result[
                "fallback_probabilities"
            ]
        )

        projection_method = (
            "MINIMUM_SLACK_LP_FALLBACK"
        )

        residual = float(
            np.max(
                np.abs(
                    matrix @ probabilities
                    - targets
                )
            )
        )

    else:
        projection_method = (
            "DUAL_RELATIVE_ENTROPY"
        )

    return {
        "probabilities": probabilities,
        "minimum_slack": minimum_slack,
        "allowed_slack": allowed_slack,
        "maximum_equation_residual": (
            residual
        ),
        "projection_method": (
            projection_method
        ),
        "optimizer_success": bool(
            result.success
        ),
        "optimizer_message": str(
            result.message
        ),
    }


def build_market_model(
    constraints,
    max_goals,
):
    if not validate_constraint_subset(
        constraints
    ):
        raise ValueError(
            "Insufficient independent "
            "market structure."
        )

    prior_fit = (
        fit_dixon_coles_prior(
            constraints,
            max_goals,
        )
    )

    enriched, matrix, targets = (
        enrich_constraints(
            constraints,
            max_goals,
        )
    )

    projection = entropy_projection(
        prior_fit["probabilities"],
        matrix,
        targets,
    )

    probabilities = projection[
        "probabilities"
    ]

    effective_residuals = [
        abs(
            effective_fair_probability(
                probabilities,
                item["a_coeff"],
                item["b_coeff"],
            )
            - item["target"]
        )
        for item in enriched
    ]

    return {
        "probabilities": probabilities,
        "lambda_home": prior_fit[
            "lambda_home"
        ],
        "lambda_away": prior_fit[
            "lambda_away"
        ],
        "rho": prior_fit["rho"],
        "maximum_prior_residual": (
            prior_fit[
                "maximum_prior_residual"
            ]
        ),
        "prior_rmse": (
            prior_fit["prior_rmse"]
        ),
        "minimum_slack": projection[
            "minimum_slack"
        ],
        "allowed_slack": projection[
            "allowed_slack"
        ],
        "maximum_equation_residual": (
            projection[
                "maximum_equation_residual"
            ]
        ),
        "maximum_effective_residual": (
            max(effective_residuals)
            if effective_residuals
            else 0.0
        ),
        "projection_method": projection[
            "projection_method"
        ],
        "constraint_count": len(
            constraints
        ),
        "market_group_count": (
            constraint_group_count(
                constraints
            )
        ),
    }


# ============================================================
# 8. Score-grid selection
# ============================================================

def determine_max_goals(
    all_constraint_sets,
):
    initial = CONFIG[
        "INITIAL_MAX_GOALS"
    ]

    fitted = []

    for constraints in all_constraint_sets:
        if not validate_constraint_subset(
            constraints
        ):
            continue

        try:
            fit = fit_dixon_coles_prior(
                constraints,
                initial,
            )

            fitted.append(fit)

        except Exception:
            continue

    if not fitted:
        return initial

    maximum_lambda = max(
        max(
            item["lambda_home"],
            item["lambda_away"],
        )
        for item in fitted
    )

    quantile = poisson.ppf(
        1.0
        - CONFIG[
            "TAIL_TOLERANCE"
        ],
        maximum_lambda,
    )

    if not np.isfinite(quantile):
        return initial

    return min(
        CONFIG[
            "MAX_GOALS_SAFETY"
        ],
        max(
            initial,
            int(
                math.ceil(
                    float(quantile)
                )
            ),
        ),
    )


# ============================================================
# 9. Scenario construction
# ============================================================

def build_full_scenarios(
    data,
    constraint_sets,
    max_goals,
):
    scenarios = []
    errors = []

    for book in data["sharp_books"]:
        for method in data[
            "settings"
        ]["devig_methods"]:
            specification_key = (
                book["key"],
                method,
            )

            constraints = constraint_sets[
                specification_key
            ]

            scenario_id = (
                f"{book['key']}|"
                f"{method}|FULL"
            )

            try:
                model = build_market_model(
                    constraints,
                    max_goals,
                )

                scenarios.append({
                    "id": scenario_id,
                    "source": book["key"],
                    "source_title": (
                        book["title"]
                    ),
                    "devig_method": method,
                    "scenario_type": (
                        "FULL_MARKET"
                    ),
                    "excluded_group": None,
                    **model,
                })

            except Exception as error:
                errors.append({
                    "scenario_id": (
                        scenario_id
                    ),
                    "error": str(error),
                })

    return scenarios, errors


def target_group_present(
    constraints,
    group_key,
):
    return any(
        item["group_key"]
        == group_key
        for item in constraints
    )


def direct_target_for_candidate(
    constraints,
    candidate,
):
    key = candidate[
        "candidate_key"
    ]

    values = [
        float(item["target"])
        for item in constraints
        if item["candidate_key"] == key
    ]

    if not values:
        return None

    return float(
        np.median(values)
    )


def build_candidate_scenarios(
    data,
    candidate,
    constraint_sets,
    full_scenario_map,
    max_goals,
):
    scenarios = []
    errors = []

    target_group = candidate[
        "group_key"
    ]

    for book in data["sharp_books"]:
        for method in data[
            "settings"
        ]["devig_methods"]:
            specification_key = (
                book["key"],
                method,
            )

            constraints = constraint_sets[
                specification_key
            ]

            direct_target = (
                direct_target_for_candidate(
                    constraints,
                    candidate,
                )
            )

            group_is_present = (
                target_group_present(
                    constraints,
                    target_group,
                )
            )

            if group_is_present:
                reduced_constraints = [
                    item
                    for item in constraints
                    if item["group_key"]
                    != target_group
                ]

                scenario_id = (
                    f"{book['key']}|"
                    f"{method}|OUT|"
                    f"{target_group}"
                )

                if not validate_constraint_subset(
                    reduced_constraints
                ):
                    errors.append({
                        "scenario_id": (
                            scenario_id
                        ),
                        "source": book["key"],
                        "devig_method": method,
                        "reason": (
                            "INSUFFICIENT_MARKETS_"
                            "AFTER_TARGET_REMOVAL"
                        ),
                    })

                    continue

                try:
                    model = build_market_model(
                        reduced_constraints,
                        max_goals,
                    )

                    scenarios.append({
                        "id": scenario_id,
                        "source": book["key"],
                        "source_title": (
                            book["title"]
                        ),
                        "devig_method": method,
                        "scenario_type": (
                            "TARGET_GROUP_OUT"
                        ),
                        "excluded_group": (
                            target_group
                        ),
                        "direct_devig_target": (
                            direct_target
                        ),
                        **model,
                    })

                except Exception as error:
                    errors.append({
                        "scenario_id": (
                            scenario_id
                        ),
                        "source": book["key"],
                        "devig_method": method,
                        "reason": (
                            "TARGET_OUT_MODEL_FAILED"
                        ),
                        "error": str(error),
                    })

            else:
                full_scenario = (
                    full_scenario_map.get(
                        specification_key
                    )
                )

                scenario_id = (
                    f"{book['key']}|"
                    f"{method}|UNQUOTED"
                )

                if full_scenario is None:
                    errors.append({
                        "scenario_id": (
                            scenario_id
                        ),
                        "source": book["key"],
                        "devig_method": method,
                        "reason": (
                            "FULL_MODEL_UNAVAILABLE"
                        ),
                    })

                    continue

                scenarios.append({
                    **full_scenario,
                    "id": scenario_id,
                    "scenario_type": (
                        "UNQUOTED_LINE_"
                        "RECONSTRUCTION"
                    ),
                    "excluded_group": None,
                    "direct_devig_target": None,
                })

    return scenarios, errors


# ============================================================
# 10. Candidate evaluation
# ============================================================

def candidate_price_status(
    conservative_ev,
    median_ev,
):
    if conservative_ev is None:
        return "UNKNOWN"

    if conservative_ev >= -TOL:
        return "FAIR_OR_BETTER"

    if (
        median_ev is not None
        and median_ev >= -TOL
    ):
        return "MIXED_PRICE"

    if conservative_ev <= CONFIG[
        "SEVERE_PRICE_EV_WARNING"
    ]:
        return "SEVERELY_UNDERPAID"

    if conservative_ev <= CONFIG[
        "POOR_PRICE_EV_WARNING"
    ]:
        return "POOR_PRICE"

    return "SLIGHTLY_UNDERPAID"


def public_scenario_record(
    scenario,
):
    return {
        key: value
        for key, value
        in scenario.items()
        if key != "probabilities"
    }


def evaluate_candidate(
    data,
    candidate,
    constraint_sets,
    full_scenario_map,
    max_goals,
):
    home_scores, away_scores = (
        score_arrays(max_goals)
    )

    a_coeff, b_coeff = (
        settlement_coefficients(
            home_scores,
            away_scores,
            candidate["market"],
            candidate["selection"],
            candidate["line"],
        )
    )

    payout = (
        a_coeff * candidate["odds"]
        + b_coeff
    )

    profit = payout - 1.0

    hit_mask = (
        profit > TOL
    )

    nonloss_mask = (
        profit >= -TOL
    )

    miss_mask = (
        profit < -TOL
    )

    candidate_scenarios, errors = (
        build_candidate_scenarios(
            data=data,
            candidate=candidate,
            constraint_sets=(
                constraint_sets
            ),
            full_scenario_map=(
                full_scenario_map
            ),
            max_goals=max_goals,
        )
    )

    scenario_results = []

    for scenario in candidate_scenarios:
        metrics = candidate_metrics(
            probabilities=scenario[
                "probabilities"
            ],
            a_coeff=a_coeff,
            b_coeff=b_coeff,
            odds=candidate["odds"],
        )

        discrepancy = None

        if (
            scenario.get(
                "direct_devig_target"
            )
            is not None
        ):
            discrepancy = (
                metrics[
                    "effective_fair_probability"
                ]
                - scenario[
                    "direct_devig_target"
                ]
            )

        scenario_results.append({
            "scenario_id": scenario["id"],
            "source": scenario["source"],
            "source_title": scenario[
                "source_title"
            ],
            "devig_method": scenario[
                "devig_method"
            ],
            "scenario_type": scenario[
                "scenario_type"
            ],
            "excluded_group": scenario[
                "excluded_group"
            ],
            "direct_devig_target": (
                scenario.get(
                    "direct_devig_target"
                )
            ),
            "fair_probability_discrepancy": (
                discrepancy
            ),
            "model_diagnostics": {
                "lambda_home": scenario[
                    "lambda_home"
                ],
                "lambda_away": scenario[
                    "lambda_away"
                ],
                "rho": scenario["rho"],
                "minimum_slack": scenario[
                    "minimum_slack"
                ],
                "maximum_equation_residual": (
                    scenario[
                        "maximum_equation_residual"
                    ]
                ),
                "projection_method": (
                    scenario[
                        "projection_method"
                    ]
                ),
                "constraint_count": (
                    scenario[
                        "constraint_count"
                    ]
                ),
                "market_group_count": (
                    scenario[
                        "market_group_count"
                    ]
                ),
            },
            **metrics,
        })

    hit_summary = summary_statistics(
        item["hit_probability"]
        for item in scenario_results
    )

    nonloss_summary = summary_statistics(
        item["nonloss_probability"]
        for item in scenario_results
    )

    loss_summary = summary_statistics(
        item["loss_probability"]
        for item in scenario_results
    )

    ev_summary = summary_statistics(
        item["expected_return"]
        for item in scenario_results
    )

    fair_odds_summary = (
        summary_statistics(
            item["fair_odds"]
            for item in scenario_results
            if item["fair_odds"] is not None
        )
    )

    effective_summary = (
        summary_statistics(
            item[
                "effective_fair_probability"
            ]
            for item in scenario_results
        )
    )

    settlement_summaries = {
        field: summary_statistics(
            item[field]
            for item in scenario_results
        )
        for field in {
            "full_win",
            "half_win",
            "push",
            "half_loss",
            "full_loss",
        }
    }

    discrepancy_summary = (
        summary_statistics(
            item[
                "fair_probability_discrepancy"
            ]
            for item in scenario_results
            if item[
                "fair_probability_discrepancy"
            ] is not None
        )
    )

    primary_source = data[
        "settings"
    ]["primary_source"]

    primary_results = [
        item
        for item in scenario_results
        if item["source"] == primary_source
    ]

    primary_methods = {
        item["devig_method"]
        for item in primary_results
    }

    required_methods = set(
        data["settings"][
            "devig_methods"
        ]
    )

    primary_complete = (
        primary_methods
        == required_methods
    )

    reasons = []

    minimum_odds = data[
        "settings"
    ]["minimum_odds"]

    maximum_odds = data[
        "settings"
    ]["maximum_odds"]

    if candidate["odds"] < minimum_odds:
        reasons.append(
            "BELOW_MINIMUM_ODDS"
        )

    if (
        maximum_odds is not None
        and candidate["odds"]
        > maximum_odds
    ):
        reasons.append(
            "ABOVE_MAXIMUM_ODDS"
        )

    if not scenario_results:
        reasons.append(
            "NO_VALID_RECONSTRUCTION"
        )

    if not primary_complete:
        reasons.append(
            "PRIMARY_SOURCE_SCENARIOS_"
            "INCOMPLETE"
        )

    ev_floor = data[
        "settings"
    ]["ev_rejection_floor"]

    if (
        ev_floor is not None
        and ev_summary["minimum"]
        is not None
        and ev_summary["minimum"]
        < ev_floor - TOL
    ):
        reasons.append(
            "BELOW_OPTIONAL_EV_FLOOR"
        )

    eligible = not reasons

    price_status = candidate_price_status(
        ev_summary["minimum"],
        ev_summary["median"],
    )

    hit_signature = np.packbits(
        hit_mask.astype(np.uint8)
    ).tobytes()

    nonloss_signature = np.packbits(
        nonloss_mask.astype(np.uint8)
    ).tobytes()

    return {
        "id": candidate["id"],
        "label": candidate["label"],
        "period": candidate["period"],
        "market": candidate["market"],
        "selection": candidate[
            "selection"
        ],
        "line": candidate["line"],
        "hkjc_odds": candidate["odds"],
        "group_key": candidate[
            "group_key"
        ],
        "eligible": eligible,
        "exclusion_reasons": reasons,

        # Filled later by official selection.
        "official": False,
        "official_rank": None,
        "official_status": (
            "NOT_ASSESSED"
        ),
        "official_exclusion_reasons": [],
        "conflicts_with": [],

        "scenario_count": len(
            scenario_results
        ),
        "primary_source_complete": (
            primary_complete
        ),
        "probability": {
            "hit": hit_summary,
            "nonloss": nonloss_summary,
            "loss": loss_summary,
            **settlement_summaries,
        },
        "effective_fair_probability": (
            effective_summary
        ),
        "fair_odds": fair_odds_summary,
        "expected_return": ev_summary,
        "price_status": price_status,
        "fair_probability_discrepancy": (
            discrepancy_summary
        ),
        "scenarios": scenario_results,
        "scenario_errors": errors,

        "_a_coeff": a_coeff,
        "_b_coeff": b_coeff,
        "_payout": payout,
        "_profit": profit,
        "_hit_mask": hit_mask,
        "_nonloss_mask": nonloss_mask,
        "_miss_mask": miss_mask,
        "_hit_signature": hit_signature,
        "_nonloss_signature": (
            nonloss_signature
        ),
        "_original_index": candidate[
            "original_index"
        ],
    }


# ============================================================
# 11. Official recommendation selection
# ============================================================

def recommendation_sort_key(
    candidate,
):
    hit = candidate[
        "probability"
    ]["hit"]

    nonloss = candidate[
        "probability"
    ]["nonloss"]

    full_loss = candidate[
        "probability"
    ]["full_loss"]

    return (
        (
            hit["minimum"]
            if hit["minimum"] is not None
            else -1.0
        ),
        (
            hit["median"]
            if hit["median"] is not None
            else -1.0
        ),
        (
            nonloss["minimum"]
            if nonloss["minimum"] is not None
            else -1.0
        ),
        -(
            full_loss["maximum"]
            if full_loss["maximum"]
            is not None
            else 1.0
        ),
        -candidate[
            "_original_index"
        ],
    )


def candidates_can_both_hit(
    first,
    second,
):
    """
    Return True only if there is at least one
    score state in which both selections produce
    a positive return.

    This blocks contradictory selections across:
    - different O/U lines;
    - 1X2 versus AH;
    - opposing AH lines;
    - opposing 1X2 outcomes;
    - any other cross-market combination that
      cannot both be successful.
    """
    first_mask = np.asarray(
        first["_hit_mask"],
        dtype=bool,
    )

    second_mask = np.asarray(
        second["_hit_mask"],
        dtype=bool,
    )

    if (
        first_mask.shape
        != second_mask.shape
    ):
        raise ValueError(
            "Candidate score grids do not match."
        )

    return bool(
        np.any(
            first_mask
            & second_mask
        )
    )


def candidate_conflict_reason(
    candidate,
    selected_candidate,
):
    if (
        candidate["group_key"]
        == selected_candidate["group_key"]
    ):
        return (
            "SAME_MARKET_GROUP_AS_"
            f"{selected_candidate['id']}"
        )

    if (
        candidate["_hit_signature"]
        == selected_candidate[
            "_hit_signature"
        ]
    ):
        return (
            "SAME_HIT_EVENT_AS_"
            f"{selected_candidate['id']}"
        )

    if not candidates_can_both_hit(
        candidate,
        selected_candidate,
    ):
        return (
            "CONTRADICTS_"
            f"{selected_candidate['id']}"
        )

    return None


def choose_recommendations(
    evaluated_candidates,
    maximum_recommendations,
    minimum_hit_probability,
):
    """
    Select official recommendations.

    The requested recommendation count is only
    a maximum. It is never force-filled.

    Official rules:
    1. Base candidate must be eligible.
    2. Conservative hit probability must meet
       the configured threshold.
    3. Same market group cannot appear twice.
    4. Same positive-return event cannot appear twice.
    5. Every selected pair must have at least one
       score state in which both picks can hit.
    """
    for candidate in evaluated_candidates:
        candidate["official"] = False
        candidate["official_rank"] = None
        candidate["official_status"] = (
            "NOT_SELECTED"
        )
        candidate[
            "official_exclusion_reasons"
        ] = []
        candidate["conflicts_with"] = []

    ordered = sorted(
        evaluated_candidates,
        key=recommendation_sort_key,
        reverse=True,
    )

    selected = []

    for candidate in ordered:
        official_reasons = []

        if not candidate["eligible"]:
            official_reasons.append(
                "BASE_CANDIDATE_INELIGIBLE"
            )

        conservative_hit = (
            candidate
            .get("probability", {})
            .get("hit", {})
            .get("minimum")
        )

        if conservative_hit is None:
            official_reasons.append(
                "NO_CONSERVATIVE_HIT_PROBABILITY"
            )

        elif (
            conservative_hit
            < minimum_hit_probability - TOL
        ):
            official_reasons.append(
                "BELOW_MINIMUM_OFFICIAL_"
                "HIT_PROBABILITY"
            )

        conflict_records = []

        if not official_reasons:
            for existing in selected:
                conflict_reason = (
                    candidate_conflict_reason(
                        candidate,
                        existing,
                    )
                )

                if conflict_reason is not None:
                    conflict_records.append({
                        "selected_id": (
                            existing["id"]
                        ),
                        "selected_label": (
                            existing["label"]
                        ),
                        "reason": (
                            conflict_reason
                        ),
                    })

        if conflict_records:
            official_reasons.append(
                "CONFLICTS_WITH_HIGHER_"
                "RANKED_OFFICIAL_PICK"
            )

            candidate["conflicts_with"] = (
                conflict_records
            )

        if official_reasons:
            candidate[
                "official_exclusion_reasons"
            ] = official_reasons

            candidate["official_status"] = (
                "REFERENCE_ONLY"
            )

            continue

        if (
            len(selected)
            >= int(maximum_recommendations)
        ):
            candidate[
                "official_exclusion_reasons"
            ] = [
                "MAXIMUM_RECOMMENDATIONS_REACHED"
            ]

            candidate["official_status"] = (
                "REFERENCE_ONLY"
            )

            continue

        selected.append(candidate)

        candidate["official"] = True
        candidate["official_status"] = (
            "OFFICIAL"
        )
        candidate["official_rank"] = len(
            selected
        )

    return selected


# ============================================================
# 12. Full-market recommendation-set analysis
# ============================================================

def joint_recommendation_metrics(
    selected,
    full_scenarios,
):
    if not selected or not full_scenarios:
        return {
            "scenario_count": 0,
            "all_hit_probability": (
                summary_statistics([])
            ),
            "at_least_one_hit_probability": (
                summary_statistics([])
            ),
            "all_miss_probability": (
                summary_statistics([])
            ),
            "pair_compatibility": [],
            "scenarios": [],
        }

    scenario_records = []

    for scenario in full_scenarios:
        probabilities = scenario[
            "probabilities"
        ]

        hit_masks = [
            candidate["_hit_mask"]
            for candidate in selected
        ]

        miss_masks = [
            candidate["_miss_mask"]
            for candidate in selected
        ]

        all_hit_mask = np.logical_and.reduce(
            hit_masks
        )

        at_least_one_hit_mask = (
            np.logical_or.reduce(
                hit_masks
            )
        )

        all_miss_mask = np.logical_and.reduce(
            miss_masks
        )

        scenario_records.append({
            "scenario_id": scenario["id"],
            "all_hit_probability": float(
                probabilities
                @ all_hit_mask.astype(float)
            ),
            "at_least_one_hit_probability": (
                float(
                    probabilities
                    @ at_least_one_hit_mask.astype(
                        float
                    )
                )
            ),
            "all_miss_probability": float(
                probabilities
                @ all_miss_mask.astype(float)
            ),
        })

    pair_compatibility = []

    for first_index in range(
        len(selected)
    ):
        for second_index in range(
            first_index + 1,
            len(selected),
        ):
            first = selected[
                first_index
            ]

            second = selected[
                second_index
            ]

            pair_mask = (
                first["_hit_mask"]
                & second["_hit_mask"]
            )

            pair_probabilities = [
                float(
                    scenario["probabilities"]
                    @ pair_mask.astype(float)
                )
                for scenario
                in full_scenarios
            ]

            pair_compatibility.append({
                "first_id": first["id"],
                "first_label": first["label"],
                "second_id": second["id"],
                "second_label": second["label"],
                "can_both_hit": bool(
                    np.any(pair_mask)
                ),
                "joint_hit_probability": (
                    summary_statistics(
                        pair_probabilities
                    )
                ),
            })

    return {
        "scenario_count": len(
            scenario_records
        ),
        "all_hit_probability": (
            summary_statistics(
                item[
                    "all_hit_probability"
                ]
                for item in scenario_records
            )
        ),
        "at_least_one_hit_probability": (
            summary_statistics(
                item[
                    "at_least_one_hit_probability"
                ]
                for item in scenario_records
            )
        ),
        "all_miss_probability": (
            summary_statistics(
                item[
                    "all_miss_probability"
                ]
                for item in scenario_records
            )
        ),
        "pair_compatibility": (
            pair_compatibility
        ),
        "scenarios": scenario_records,
    }


# ============================================================
# 13. Correct-score reference
# ============================================================

def calculate_correct_scores(
    full_scenarios,
    max_goals,
    count,
):
    empty_output = {
        "recommendations": [],
        "combined_probability": (
            summary_statistics([])
        ),
        "warning": (
            "Correct scores are mutually exclusive "
            "and naturally have much lower hit "
            "probabilities than main markets."
        ),
    }

    if (
        count <= 0
        or not full_scenarios
    ):
        return empty_output

    probability_matrix = np.vstack([
        scenario["probabilities"]
        for scenario in full_scenarios
    ])

    minimum = np.min(
        probability_matrix,
        axis=0,
    )

    median = np.median(
        probability_matrix,
        axis=0,
    )

    maximum = np.max(
        probability_matrix,
        axis=0,
    )

    home_scores, away_scores = (
        score_arrays(max_goals)
    )

    records = []

    for index in range(
        len(home_scores)
    ):
        central_probability = float(
            median[index]
        )

        records.append({
            "home_goals": int(
                home_scores[index]
            ),
            "away_goals": int(
                away_scores[index]
            ),
            "score": (
                f"{int(home_scores[index])}"
                "-"
                f"{int(away_scores[index])}"
            ),
            "probability": {
                "minimum": float(
                    minimum[index]
                ),
                "median": (
                    central_probability
                ),
                "maximum": float(
                    maximum[index]
                ),
                "count": len(
                    full_scenarios
                ),
            },
            "central_fair_odds": (
                1.0 / central_probability
                if central_probability > TOL
                else None
            ),
            "section": (
                "HIGH_RISK_CORRECT_"
                "SCORE_REFERENCE"
            ),
        })

    records.sort(
        key=lambda item: (
            item["probability"]["minimum"],
            item["probability"]["median"],
        ),
        reverse=True,
    )

    selected = records[
        :int(count)
    ]

    selected_indices = [
        (
            item["home_goals"]
            * (max_goals + 1)
            + item["away_goals"]
        )
        for item in selected
    ]

    combined_probabilities = [
        float(
            np.sum(
                scenario[
                    "probabilities"
                ][selected_indices]
            )
        )
        for scenario in full_scenarios
    ]

    return {
        "recommendations": selected,
        "combined_probability": (
            summary_statistics(
                combined_probabilities
            )
        ),
        "warning": (
            "Correct scores are mutually exclusive "
            "and naturally have much lower hit "
            "probabilities than main markets."
        ),
    }


# ============================================================
# 14. Public-output cleaning
# ============================================================

def public_candidate_record(
    candidate,
):
    return {
        key: value
        for key, value
        in candidate.items()
        if not key.startswith("_")
    }


def public_full_scenario_record(
    scenario,
):
    return {
        key: value
        for key, value
        in scenario.items()
        if key != "probabilities"
    }


# ============================================================
# 15. Main engine
# ============================================================

def run_engine(input_data):
    started = datetime.now(
        timezone.utc
    )

    data = validate_input_data(
        input_data
    )

    # --------------------------------------------------------
    # Source × de-vig constraint sets.
    # --------------------------------------------------------

    constraint_sets = {}

    for book in data["sharp_books"]:
        for method in data[
            "settings"
        ]["devig_methods"]:
            constraint_sets[
                (
                    book["key"],
                    method,
                )
            ] = build_book_constraints(
                book,
                method,
            )

    max_goals = determine_max_goals(
        list(
            constraint_sets.values()
        )
    )

    # --------------------------------------------------------
    # Full-market reconstructions.
    # --------------------------------------------------------

    full_scenarios, full_errors = (
        build_full_scenarios(
            data=data,
            constraint_sets=constraint_sets,
            max_goals=max_goals,
        )
    )

    if not full_scenarios:
        raise RuntimeError(
            "No valid full-market "
            "reconstruction was produced."
        )

    full_scenario_map = {
        (
            scenario["source"],
            scenario["devig_method"],
        ): scenario
        for scenario in full_scenarios
    }

    primary_source = data[
        "settings"
    ]["primary_source"]

    primary_methods_available = {
        scenario["devig_method"]
        for scenario in full_scenarios
        if scenario["source"]
        == primary_source
    }

    required_methods = set(
        data["settings"][
            "devig_methods"
        ]
    )

    if (
        primary_methods_available
        != required_methods
    ):
        raise RuntimeError(
            "The primary sharp source did not "
            "produce every configured full-market "
            "scenario."
        )

    # --------------------------------------------------------
    # Candidate-specific line-out analysis.
    # --------------------------------------------------------

    evaluated_candidates = []

    for candidate in data[
        "hkjc_markets"
    ]:
        evaluated_candidates.append(
            evaluate_candidate(
                data=data,
                candidate=candidate,
                constraint_sets=(
                    constraint_sets
                ),
                full_scenario_map=(
                    full_scenario_map
                ),
                max_goals=max_goals,
            )
        )

    # --------------------------------------------------------
    # Official hit-threshold and contradiction filtering.
    # --------------------------------------------------------

    selected = choose_recommendations(
        evaluated_candidates=(
            evaluated_candidates
        ),
        maximum_recommendations=(
            data["settings"][
                "max_recommendations"
            ]
        ),
        minimum_hit_probability=(
            data["settings"][
                "minimum_official_hit_probability"
            ]
        ),
    )

    recommendations = []

    for candidate in selected:
        public = public_candidate_record(
            candidate
        )

        public["rank"] = candidate[
            "official_rank"
        ]

        public["ranking_basis"] = (
            "Conservative actual positive-return "
            "probability from target-line-out or "
            "unquoted-line sharp-market "
            "reconstruction."
        )

        recommendations.append(public)

    joint_metrics = (
        joint_recommendation_metrics(
            selected=selected,
            full_scenarios=(
                full_scenarios
            ),
        )
    )

    correct_scores = (
        calculate_correct_scores(
            full_scenarios=full_scenarios,
            max_goals=max_goals,
            count=data["settings"][
                "correct_score_count"
            ],
        )
    )

    finished = datetime.now(
        timezone.utc
    )

    all_candidate_records = [
        public_candidate_record(
            candidate
        )
        for candidate
        in sorted(
            evaluated_candidates,
            key=recommendation_sort_key,
            reverse=True,
        )
    ]

    output = {
        "engine": {
            "name": ENGINE_NAME,
            "version": ENGINE_VERSION,
            "generated_at_utc": (
                finished.isoformat()
            ),
        },
        "status": "COMPLETED",
        "match": data["match"],
        "settings": data["settings"],
        "methodology": {
            "historical_team_data_used": False,
            "arbitrary_model_weights_used": False,
            "ev_used_for_ranking": False,
            "kelly_used": False,
            "ranking_objective": (
                "CONSERVATIVE_ACTUAL_"
                "HIT_PROBABILITY"
            ),
            "minimum_official_hit_probability": (
                data["settings"][
                    "minimum_official_hit_probability"
                ]
            ),
            "maximum_recommendations_is_ceiling": (
                True
            ),
            "contradictory_official_picks_blocked": (
                True
            ),
            "contradiction_definition": (
                "Two selections conflict when no "
                "score state allows both selections "
                "to produce a positive return."
            ),
            "target_market_exclusion": {
                "1X2": (
                    "Remove the complete 1X2 "
                    "market."
                ),
                "AH": (
                    "Remove both sides of the "
                    "exact AH line."
                ),
                "OU": (
                    "Remove both sides of the "
                    "exact O/U line."
                ),
            },
            "dixon_coles_role": (
                "Football-shaped score prior "
                "for current sharp-market "
                "reconstruction."
            ),
            "projection_role": (
                "Reconcile the score distribution "
                "with de-vigged sharp-market "
                "constraints."
            ),
            "hit_definition": (
                "Gross payout greater than stake. "
                "Full wins and half wins are hits; "
                "pushes are not counted as hits."
            ),
            "ev_role": (
                "Price warning and optional hard "
                "rejection floor only."
            ),
            "all_lines_retained": True,
        },
        "model": {
            "max_goals_per_team": (
                max_goals
            ),
            "state_count": (
                (max_goals + 1) ** 2
            ),
            "full_scenario_count": len(
                full_scenarios
            ),
            "full_scenarios": [
                public_full_scenario_record(
                    scenario
                )
                for scenario
                in full_scenarios
            ],
            "full_scenario_errors": (
                full_errors
            ),
        },
        "official_selection": {
            "minimum_hit_probability": (
                data["settings"][
                    "minimum_official_hit_probability"
                ]
            ),
            "maximum_recommendations": (
                data["settings"][
                    "max_recommendations"
                ]
            ),
            "official_count": len(
                recommendations
            ),
            "contradiction_filter_used": True,
            "same_hit_event_filter_used": True,
        },
        "recommendations": (
            recommendations
        ),
        "recommendation_set": (
            joint_metrics
        ),
        "correct_scores": (
            correct_scores
        ),

        # Every entered line remains here, including:
        # - official picks;
        # - below-threshold lines;
        # - contradictory lines;
        # - poor-price lines;
        # - structurally excluded lines.
        "candidate_markets": (
            all_candidate_records
        ),

        "excluded_markets": [
            {
                "id": candidate["id"],
                "label": candidate["label"],
                "base_exclusion_reasons": (
                    candidate[
                        "exclusion_reasons"
                    ]
                ),
                "official_exclusion_reasons": (
                    candidate[
                        "official_exclusion_reasons"
                    ]
                ),
                "conflicts_with": (
                    candidate[
                        "conflicts_with"
                    ]
                ),
            }
            for candidate
            in evaluated_candidates
            if not candidate["official"]
        ],
        "runtime": {
            "total_seconds": (
                finished - started
            ).total_seconds(),
        },
        "input_snapshot": data,
    }

    return to_builtin(output)
