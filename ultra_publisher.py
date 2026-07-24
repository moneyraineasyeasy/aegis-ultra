from __future__ import annotations

import hashlib
import math
import re
from typing import Any, Dict, Iterable, List, Optional

import requests


# ============================================================
# AEGIS ULTRA → CLIENT PORTAL PUBLISHER
# ============================================================

PUBLISH_TIMEOUT_SECONDS = 30

VALID_TIERS = {
    "OFFICIAL",
    "ALTERNATIVE",
    "CORRECT_SCORE",
}


# ============================================================
# 1. Generic helpers
# ============================================================

def clean_text(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip()


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


def safe_int(
    value: Any,
    default: int = 0,
) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def nested_value(
    record: Dict[str, Any],
    *keys: str,
    default=None,
):
    current: Any = record

    for key in keys:
        if not isinstance(current, dict):
            return default

        current = current.get(key)

        if current is None:
            return default

    return current


def slugify(value: Any) -> str:
    text = clean_text(value).lower()

    text = re.sub(
        r"[^a-z0-9\u4e00-\u9fff]+",
        "_",
        text,
    )

    text = text.strip("_")

    return text or "item"


def stable_hash(
    value: str,
    length: int = 14,
) -> str:
    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()[:length]


def format_line(value: Any) -> str:
    number = safe_float(value)

    if number is None:
        return ""

    return f"{number:+g}"


# ============================================================
# 2. Stable IDs
# ============================================================

def make_match_id(
    output: Dict[str, Any],
) -> str:
    match = output.get(
        "match",
        {},
    )

    home = clean_text(
        match.get("home")
    )

    away = clean_text(
        match.get("away")
    )

    kickoff = clean_text(
        match.get("kickoff")
    )

    competition = clean_text(
        match.get("competition")
    )

    identity = "|".join([
        home.casefold(),
        away.casefold(),
        kickoff,
        competition.casefold(),
    ])

    readable = (
        f"{slugify(home)}_"
        f"{slugify(away)}"
    )[:45]

    return (
        f"match_{readable}_"
        f"{stable_hash(identity)}"
    )


def make_candidate_rec_id(
    match_id: str,
    candidate: Dict[str, Any],
) -> str:
    candidate_id = clean_text(
        candidate.get("id")
    )

    identity = "|".join([
        match_id,
        candidate_id,
        clean_text(
            candidate.get("market")
        ),
        clean_text(
            candidate.get("selection")
        ),
        clean_text(
            candidate.get("line")
        ),
        clean_text(
            candidate.get("label")
        ),
    ])

    return (
        f"rec_{stable_hash(identity)}"
    )


def make_score_rec_id(
    match_id: str,
    score: str,
) -> str:
    identity = (
        f"{match_id}|CORRECT_SCORE|"
        f"{clean_text(score)}"
    )

    return (
        f"score_{stable_hash(identity)}"
    )


# ============================================================
# 3. Match summary
# ============================================================

def extract_top_scores(
    output: Dict[str, Any],
) -> List[Dict[str, Any]]:
    correct_scores = output.get(
        "correct_scores",
        {},
    )

    if not isinstance(
        correct_scores,
        dict,
    ):
        return []

    scores = correct_scores.get(
        "recommendations",
        [],
    )

    if not isinstance(scores, list):
        return []

    return scores


def top_scores_text(
    output: Dict[str, Any],
) -> str:
    parts = []

    for score in extract_top_scores(
        output
    ):
        score_name = clean_text(
            score.get("score")
        )

        probability = safe_float(
            nested_value(
                score,
                "probability",
                "minimum",
            )
        )

        if not score_name:
            continue

        if probability is None:
            parts.append(score_name)
        else:
            parts.append(
                f"{score_name} "
                f"({probability * 100:.1f}%)"
            )

    return " / ".join(parts)


def model_direction_text(
    output: Dict[str, Any],
) -> str:
    recommendations = output.get(
        "recommendations",
        [],
    )

    labels = [
        clean_text(item.get("label"))
        for item in recommendations
        if clean_text(item.get("label"))
    ]

    if labels:
        return "；".join(labels[:3])

    candidates = output.get(
        "candidate_markets",
        [],
    )

    ranked = sorted(
        candidates,
        key=lambda item: (
            safe_float(
                nested_value(
                    item,
                    "probability",
                    "hit",
                    "minimum",
                ),
                -1.0,
            )
        ),
        reverse=True,
    )

    fallback_labels = [
        clean_text(item.get("label"))
        for item in ranked
        if clean_text(item.get("label"))
    ]

    return "；".join(
        fallback_labels[:2]
    )


def model_summary_text(
    output: Dict[str, Any],
) -> str:
    recommendations = output.get(
        "recommendations",
        [],
    )

    candidate_count = len(
        output.get(
            "candidate_markets",
            [],
        )
    )

    official_count = len(
        recommendations
    )

    if recommendations:
        highest_hit = max(
            (
                safe_float(
                    nested_value(
                        item,
                        "probability",
                        "hit",
                        "minimum",
                    ),
                    0.0,
                )
                for item in recommendations
            ),
            default=0.0,
        )

        return (
            f"{official_count} 項官方推薦；"
            f"最高保守命中概率 "
            f"{highest_hit * 100:.1f}%；"
            f"共分析 {candidate_count} 條盤口。"
        )

    return (
        "本場未有盤口通過官方推薦門檻；"
        f"共分析 {candidate_count} 條盤口。"
    )


def build_match_record(
    output: Dict[str, Any],
    *,
    status: str = "published",
    model_direction: Optional[str] = None,
    model_summary: Optional[str] = None,
) -> Dict[str, Any]:
    match = output.get(
        "match",
        {},
    )

    match_id = make_match_id(output)

    home = clean_text(
        match.get("home")
    )

    away = clean_text(
        match.get("away")
    )

    match_name = clean_text(
        match.get("name")
    )

    if not match_name:
        match_name = (
            f"{home} vs {away}"
        )

    return {
        "match_id": match_id,
        "match_name": match_name,
        "home_team": home,
        "away_team": away,
        "competition": clean_text(
            match.get("competition")
        ),
        "kickoff": clean_text(
            match.get("kickoff")
        ),
        "status": clean_text(
            status
        ).lower() or "published",
        "model_direction": (
            clean_text(model_direction)
            if model_direction is not None
            else model_direction_text(output)
        ),
        "model_summary": (
            clean_text(model_summary)
            if model_summary is not None
            else model_summary_text(output)
        ),
        "top_scores": top_scores_text(
            output
        ),
        "final_score": "",
    }


# ============================================================
# 4. Candidate catalogue
# ============================================================

def candidate_default_tier(
    candidate: Dict[str, Any],
) -> str:
    if candidate.get("official"):
        return "OFFICIAL"

    return "ALTERNATIVE"


def candidate_catalogue(
    output: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Build rows for Streamlit's publication editor.

    All Ultra candidates appear here. The admin can
    choose which ones to publish and assign their tier.
    """
    rows = []

    candidates = output.get(
        "candidate_markets",
        [],
    )

    for index, candidate in enumerate(
        candidates,
        start=1,
    ):
        conservative_hit = safe_float(
            nested_value(
                candidate,
                "probability",
                "hit",
                "minimum",
            )
        )

        median_hit = safe_float(
            nested_value(
                candidate,
                "probability",
                "hit",
                "median",
            )
        )

        rows.append({
            "publish": bool(
                candidate.get("official")
            ),
            "source_type": "CANDIDATE",
            "source_id": clean_text(
                candidate.get("id")
            ),
            "tier": candidate_default_tier(
                candidate
            ),
            "rank": (
                safe_int(
                    candidate.get(
                        "official_rank"
                    ),
                    index,
                )
            ),
            "title": clean_text(
                candidate.get("label")
            ),
            "market": clean_text(
                candidate.get("market")
            ),
            "odds": safe_float(
                candidate.get(
                    "hkjc_odds"
                )
            ),
            "conservative_hit": (
                conservative_hit
            ),
            "median_hit": median_hit,
            "stars": (
                5
                if (
                    conservative_hit
                    is not None
                    and conservative_hit
                    >= 0.65
                )
                else 4
                if (
                    conservative_hit
                    is not None
                    and conservative_hit
                    >= 0.55
                )
                else 3
            ),
            "is_heavy": False,
            "commentary": "",
            "status": clean_text(
                candidate.get(
                    "official_status"
                )
            ),
        })

    return rows


def correct_score_catalogue(
    output: Dict[str, Any],
) -> List[Dict[str, Any]]:
    rows = []

    for index, score in enumerate(
        extract_top_scores(output),
        start=1,
    ):
        probability = safe_float(
            nested_value(
                score,
                "probability",
                "minimum",
            )
        )

        rows.append({
            "publish": True,
            "source_type": (
                "CORRECT_SCORE"
            ),
            "source_id": clean_text(
                score.get("score")
            ),
            "tier": "CORRECT_SCORE",
            "rank": index,
            "title": (
                "波膽 "
                + clean_text(
                    score.get("score")
                )
            ),
            "market": "CORRECT_SCORE",
            "odds": None,
            "conservative_hit": (
                probability
            ),
            "median_hit": safe_float(
                nested_value(
                    score,
                    "probability",
                    "median",
                )
            ),
            "stars": 2,
            "is_heavy": False,
            "commentary": (
                "高風險波膽參考，"
                "不屬於官方主推盤口。"
            ),
            "status": "REFERENCE",
        })

    return rows


def publication_catalogue(
    output: Dict[str, Any],
) -> List[Dict[str, Any]]:
    return (
        candidate_catalogue(output)
        + correct_score_catalogue(output)
    )


# ============================================================
# 5. Portal recommendation conversion
# ============================================================

def find_candidate(
    output: Dict[str, Any],
    candidate_id: str,
) -> Optional[Dict[str, Any]]:
    for candidate in output.get(
        "candidate_markets",
        [],
    ):
        if (
            clean_text(
                candidate.get("id")
            )
            == clean_text(candidate_id)
        ):
            return candidate

    return None


def find_score(
    output: Dict[str, Any],
    score_name: str,
) -> Optional[Dict[str, Any]]:
    for score in extract_top_scores(
        output
    ):
        if (
            clean_text(
                score.get("score")
            )
            == clean_text(score_name)
        ):
            return score

    return None


def conflict_ids_text(
    candidate: Dict[str, Any],
) -> str:
    conflict_ids = []

    for conflict in candidate.get(
        "conflicts_with",
        [],
    ):
        conflict_id = clean_text(
            conflict.get("selected_id")
        )

        if conflict_id:
            conflict_ids.append(
                conflict_id
            )

    return ",".join(conflict_ids)


def candidate_to_portal_record(
    match_id: str,
    candidate: Dict[str, Any],
    editor_row: Dict[str, Any],
) -> Dict[str, Any]:
    tier = clean_text(
        editor_row.get("tier")
    ).upper()

    if tier not in VALID_TIERS:
        tier = candidate_default_tier(
            candidate
        )

    return {
        "rec_id": make_candidate_rec_id(
            match_id,
            candidate,
        ),
        "match_id": match_id,
        "tier": tier,
        "rank": safe_int(
            editor_row.get("rank"),
            0,
        ),
        "rec_title": (
            clean_text(
                editor_row.get("title")
            )
            or clean_text(
                candidate.get("label")
            )
        ),
        "market": clean_text(
            candidate.get("market")
        ),
        "selection": clean_text(
            candidate.get("selection")
        ),
        "line": (
            ""
            if candidate.get("line")
            is None
            else candidate.get("line")
        ),
        "odds": safe_float(
            candidate.get("hkjc_odds")
        ),
        "conservative_hit": safe_float(
            nested_value(
                candidate,
                "probability",
                "hit",
                "minimum",
            )
        ),
        "median_hit": safe_float(
            nested_value(
                candidate,
                "probability",
                "hit",
                "median",
            )
        ),
        "nonloss_probability": safe_float(
            nested_value(
                candidate,
                "probability",
                "nonloss",
                "minimum",
            )
        ),
        "full_loss_probability": safe_float(
            nested_value(
                candidate,
                "probability",
                "full_loss",
                "maximum",
            )
        ),
        "fair_odds": safe_float(
            nested_value(
                candidate,
                "fair_odds",
                "maximum",
            )
        ),
        "price_status": clean_text(
            candidate.get("price_status")
        ),
        "commentary": clean_text(
            editor_row.get("commentary")
        ),
        "stars": max(
            1,
            min(
                5,
                safe_int(
                    editor_row.get("stars"),
                    3,
                ),
            ),
        ),
        "is_heavy": bool(
            editor_row.get("is_heavy")
        ),
        "compatibility_group": clean_text(
            candidate.get("group_key")
        ),
        "conflict_ids": conflict_ids_text(
            candidate
        ),
        "result": "pending",
        "status": "published",
    }


def score_to_portal_record(
    match_id: str,
    score: Dict[str, Any],
    editor_row: Dict[str, Any],
) -> Dict[str, Any]:
    score_name = clean_text(
        score.get("score")
    )

    return {
        "rec_id": make_score_rec_id(
            match_id,
            score_name,
        ),
        "match_id": match_id,
        "tier": "CORRECT_SCORE",
        "rank": safe_int(
            editor_row.get("rank"),
            0,
        ),
        "rec_title": (
            clean_text(
                editor_row.get("title")
            )
            or f"波膽 {score_name}"
        ),
        "market": "CORRECT_SCORE",
        "selection": score_name,
        "line": "",
        "odds": "",
        "conservative_hit": safe_float(
            nested_value(
                score,
                "probability",
                "minimum",
            )
        ),
        "median_hit": safe_float(
            nested_value(
                score,
                "probability",
                "median",
            )
        ),
        "nonloss_probability": "",
        "full_loss_probability": "",
        "fair_odds": safe_float(
            score.get(
                "central_fair_odds"
            )
        ),
        "price_status": (
            "HIGH_RISK_REFERENCE"
        ),
        "commentary": clean_text(
            editor_row.get("commentary")
        ),
        "stars": max(
            1,
            min(
                5,
                safe_int(
                    editor_row.get("stars"),
                    2,
                ),
            ),
        ),
        "is_heavy": False,
        "compatibility_group": (
            "CORRECT_SCORE"
        ),
        "conflict_ids": "",
        "result": "pending",
        "status": "published",
    }


# ============================================================
# 6. Build and publish bundle
# ============================================================

def build_publish_bundle(
    output: Dict[str, Any],
    editor_rows: Iterable[
        Dict[str, Any]
    ],
    *,
    match_status: str = "published",
    model_direction: Optional[str] = None,
    model_summary: Optional[str] = None,
) -> Dict[str, Any]:
    match_record = build_match_record(
        output,
        status=match_status,
        model_direction=model_direction,
        model_summary=model_summary,
    )

    match_id = match_record[
        "match_id"
    ]

    recommendation_records = []

    for row in editor_rows:
        if not bool(
            row.get("publish")
        ):
            continue

        source_type = clean_text(
            row.get("source_type")
        ).upper()

        source_id = clean_text(
            row.get("source_id")
        )

        if source_type == "CANDIDATE":
            candidate = find_candidate(
                output,
                source_id,
            )

            if candidate is None:
                raise ValueError(
                    "Candidate not found: "
                    f"{source_id}"
                )

            recommendation_records.append(
                candidate_to_portal_record(
                    match_id,
                    candidate,
                    row,
                )
            )

        elif source_type == "CORRECT_SCORE":
            score = find_score(
                output,
                source_id,
            )

            if score is None:
                raise ValueError(
                    "Correct score not found: "
                    f"{source_id}"
                )

            recommendation_records.append(
                score_to_portal_record(
                    match_id,
                    score,
                    row,
                )
            )

        else:
            raise ValueError(
                "Unsupported publication type: "
                f"{source_type}"
            )

    if not recommendation_records:
        raise ValueError(
            "Select at least one item to publish."
        )

    return {
        "action": "publish_bundle",
        "match": match_record,
        "recommendations": (
            recommendation_records
        ),
    }


def publish_bundle(
    *,
    api_url: str,
    api_token: str,
    bundle: Dict[str, Any],
) -> Dict[str, Any]:
    api_url = clean_text(api_url)
    api_token = clean_text(api_token)

    if not api_url:
        raise ValueError(
            "Portal API URL is missing."
        )

    if not api_token:
        raise ValueError(
            "Portal API token is missing."
        )

    payload = dict(bundle)
    payload["token"] = api_token

    response = requests.post(
        api_url,
        json=payload,
        timeout=PUBLISH_TIMEOUT_SECONDS,
    )

    response.raise_for_status()

    try:
        result = response.json()
    except ValueError as error:
        raise RuntimeError(
            "Portal API returned invalid JSON."
        ) from error

    if not result.get("ok"):
        raise RuntimeError(
            "Portal API rejected publication: "
            f"{result}"
        )

    return result
