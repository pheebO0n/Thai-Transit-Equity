"""Milestone 1 data layer.

Every builder delegates vintage stamping to src.vintage_guard, so
data_year / report_year / source / data_status can never be forgotten.
Long format keeps 2568 estimates in separate rows from 2566/2567 actuals.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from src.provinces import PROVINCES, PROVINCE_BY_NAME
from src.vintage_guard import tag_vintage

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = _ROOT / "data" / "raw"
PROCESSED_DIR = _ROOT / "data" / "processed"

GPP_COLUMN_BY_YEAR = {2566: "gpp_per_capita_2566", 2567: "gpp_per_capita_2567", 2568: "gpp_per_capita_2568"}
VALID_ROUTE_CATEGORIES = frozenset({2, 3, 4})
FREQUENCY_STATUSES = ("reported", "unknown")


class DataLayerError(RuntimeError):
    """Raised when raw data violates the Milestone 1 contract."""


def load_raw(filename: str, raw_dir: Path | None = None) -> pd.DataFrame:
    """Read a raw CSV without transforming it.

    Args:
        filename: File name inside the raw directory.
        raw_dir: Override for the raw directory (used by tests).

    Returns:
        The unmodified frame.

    Raises:
        DataLayerError: If the file does not exist.
    """
    path = (raw_dir or RAW_DIR) / filename
    if not path.is_file():
        raise DataLayerError(f"Raw file not found: {path}")
    return pd.read_csv(path, encoding="utf-8-sig")

def _require_columns(df, required, where: str) -> None:
    """Raise DataLayerError if any required column is missing."""
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise DataLayerError(f"{where}: missing columns {missing}")


def _normalise_province(value: object) -> str:
    """Map an English or Thai province label to the canonical English name.

    Args:
        value: Raw cell value from a CSV.

    Returns:
        Canonical English province name.

    Raises:
        DataLayerError: If the label is not in the 77-province catalogue.
    """
    text = str(value).strip()
    if text in PROVINCE_BY_NAME:
        return text
    for prov in PROVINCES:
        if prov.name_th == text:
            return prov.name_en
    raise DataLayerError(f"Unknown province label {value!r}.")

def build_provincial_profiles(gpp_raw, registry, years=None):
    """Build provincial_profiles in long format, one row per (province, data_year).

    Each year is stamped with its own vintage, so 2568 rows remain estimates
    and 2566/2567 rows remain actuals.

    Args:
        gpp_raw: NESDC extract with province_name and one GPP column per year.
        registry: Loaded vintage registry.
        years: Data years to include.

    Returns:
        Frame with province identity, gpp_per_capita, gpp_rank, gpp_percentile
        and the four vintage columns.

    Raises:
        DataLayerError: On missing columns or wrong row count.
    """
    _require_columns(gpp_raw, ["province_name"], "profiles")
    selected = list(years) if years is not None else registry.years("gpp")
    frames = []
    for year in selected:
        col = GPP_COLUMN_BY_YEAR.get(year)
        if col is None:
            raise DataLayerError(f"No GPP column for data_year={year}.")
        _require_columns(gpp_raw, [col], f"profiles {year}")

        block = pd.DataFrame(
            {
                "province_name_en": gpp_raw["province_name"].map(_normalise_province),
                "gpp_per_capita": pd.to_numeric(gpp_raw[col], errors="coerce"),
            }
        )
        if block["gpp_per_capita"].isna().any():
            raise DataLayerError(f"Missing GPP for data_year={year}.")
        block["gpp_rank"] = block["gpp_per_capita"].rank(ascending=False, method="min").astype(int)
        block["gpp_percentile"] = block["gpp_per_capita"].rank(
            ascending=True,
            pct=True,
            method=registry.raw["gap_engine"]["percentile_method"],
        )
        block = tag_vintage(block, registry, "gpp", year)
        block["vintage_label"] = (
            block["data_year"].astype(str) + "/" + block["report_year"].astype(str)
            + " (" + block["data_status"].astype(str) + ")"
        )
        frames.append(block)

    profiles = pd.concat(frames, ignore_index=True, sort=False)
    ref = pd.DataFrame(
        [
            {
                "province_code": p.code,
                "province_name_en": p.name_en,
                "province_name_th": p.name_th,
                "region": p.region,
                "lat": p.lat,
                "lon": p.lon,
            }
            for p in PROVINCES
        ]
    )
    profiles = ref.merge(profiles, on="province_name_en", how="inner", validate="one_to_many")
    for year in selected:
        n = int((profiles["data_year"] == year).sum())
        if n != len(PROVINCES):
            raise DataLayerError(f"data_year={year} produced {n} rows.")
    return profiles.sort_values(["data_year", "gpp_rank"]).reset_index(drop=True)

def build_interprovincial_routes(
    routes_raw,
    freq_raw,
    registry,
    route_data_year=None,
    freq_data_year=None,
):
    """Build interprovincial_routes via a LEFT join on frequency.

    Existence is known from the licensing register even without a timetable.
    Missing timetables become daily_trips = NaN and frequency_status =
    'unknown' -- never zero-filled, never dropped.

    Args:
        routes_raw: Licensing register CSV extract.
        freq_raw: Optional BorKorSor timetable.
        registry: Loaded vintage registry.
        route_data_year: Override catalogue year.
        freq_data_year: Override frequency year.

    Returns:
        Routes frame with frequency_status.

    Raises:
        DataLayerError: On invalid categories or duplicate ids.
    """
    _require_columns(
        routes_raw,
        ["route_id", "origin_province", "destination_province",
         "route_category", "operator", "distance_km"],
        "routes",
    )

    has_freq = freq_raw is not None and not freq_raw.empty
    ryears = registry.years("route_catalogue")
    fyears = registry.years("route_frequency")
    r_year = route_data_year or (max(ryears) if ryears else registry.primary_data_year)
    f_year = freq_data_year or (max(fyears) if fyears else r_year)
    routes = pd.DataFrame(
        {
            "route_id": routes_raw["route_id"].astype(str).str.strip(),
            "origin_province": routes_raw["origin_province"].map(_normalise_province),
            "destination_province": routes_raw["destination_province"].map(_normalise_province),
            "route_category": pd.to_numeric(routes_raw["route_category"], errors="coerce"),
            "operator": routes_raw["operator"].astype(str).str.strip(),
            "distance_km": pd.to_numeric(routes_raw["distance_km"], errors="coerce"),
        }
    )

    if routes["route_id"].duplicated().any():
        raise DataLayerError("Duplicate route_id in register.")
    bad_cat = ~routes["route_category"].isin(list(VALID_ROUTE_CATEGORIES))
    if bad_cat.any():
        raise DataLayerError("Invalid route_category values.")
    routes["route_category"] = routes["route_category"].astype(int)
    if (routes["distance_km"] <= 0).any():
        raise DataLayerError("distance_km must be positive.")
    if has_freq:
        _require_columns(freq_raw, ["route_id", "daily_trips"], "freq")
        freq = pd.DataFrame(
            {
                "route_id": freq_raw["route_id"].astype(str).str.strip(),
                "daily_trips": pd.to_numeric(freq_raw["daily_trips"], errors="coerce"),
            }
        )
        if freq["route_id"].duplicated().any():
            raise DataLayerError("Duplicate route_id in timetable.")
        if (freq["daily_trips"] < 0).any():
            raise DataLayerError("daily_trips must be >= 0.")
        routes = routes.merge(freq, on="route_id", how="left", validate="one_to_one")

    else:
        logger.warning("No timetable: all routes unknown frequency.")
        routes["daily_trips"] = np.nan
    routes["frequency_status"] = pd.Categorical(
        np.where(routes["daily_trips"].notna(), "reported", "unknown"),
        categories=list(FREQUENCY_STATUSES),
        ordered=True,
    )
    routes = tag_vintage(routes, registry, "route_catalogue", r_year)
    routes["frequency_data_year"] = f_year if has_freq else pd.NA
    return routes.sort_values(["origin_province", "route_category", "route_id"]).reset_index(drop=True)

def build_route_frequency_summary(routes, profiles, registry):
    """Aggregate departure-side frequency per province.

    Known-frequency routes drive the means; unknown routes are counted
    separately and never enter the numerator. A province with no known
    routes gets NaN aggregates, not zeros.

    Args:
        routes: Output of build_interprovincial_routes.
        profiles: Single-year profiles slice.
        registry: Loaded fintage registry.

    Returns:
        One row per province with avg, total, operator entropy and coverage.
    """
    if profiles["data_year"].nunique() != 1:
        raise DataLayerError("Expected a single-year profiles slice.")
    known = routes[routes["frequency_status"] == "reported"].copy()
    agg = known.groupby("origin_province", observed=True).agg(
        avg_daily_trips_per_route=("daily_trips", "mean"),
        total_daily_trips_departing=("daily_trips", "sum"),
        known_frequency_route_count=("route_id", "count"),
        operator_count=("operator", "nunique"),
    ).reset_index()

    def _shannon(group):
        """Shannon entropy of daily trips across operators, in nats."""
        trips = group.groupby("operator", observed=True)["daily_trips"].sum()
        total = trips.sum()
        if total <= 0 or len(trips) == 0:
            return 0.0
        p = trips / total
        p = p[p > 0]
        return float(-(p * np.log(p)).sum())

    entropy = known.groupby("origin_province", observed=True).apply(
        _shannon, include_groups=False
    ).rename("operator_diversity_index").reset_index()
    agg = agg.merge(entropy, on="origin_province", how="left")
    unknown = (
        routes[routes["frequency_status"] == "unknown"]
        .groupby("origin_province", observed=True)
        .size()
        .rename("unknown_frequency_route_count")
        .reset_index()
    )

    base = profiles[["province_code", "province_name_en", "region"]].copy()
    summary = base.merge(
        agg.drop(columns=["operator_count"]),
        left_on="province_name_en",
        right_on="origin_province",
        how="left",
    )
    summary = summary.merge(
        unknown,
        left_on="province_name_en",
        right_on="origin_province",
        how="left",
    ).drop(columns=["origin_province"], errors="ignore")
    summary["known_frequency_route_count"] = summary["known_frequency_route_count"].fillna(0).astype(int)
    summary["unknown_frequency_route_count"] = summary["unknown_frequency_route_count"].fillna(0).astype(int)
    no_known = summary["known_frequency_route_count"] == 0
    for col in ("avg_daily_trips_per_route", "total_daily_trips_departing", "operator_diversity_index"):
        summary.loc[no_known, col] = np.nan
    total = summary["known_frequency_route_count"] + summary["unknown_frequency_route_count"]
    summary["frequency_coverage_ratio"] = np.where(
        total > 0, summary["known_frequency_route_count"] / total, np.nan
    )

    summary = summary.merge(
        profiles[
            ["province_name_en", "data_year", "report_year", "source", "data_status"]
        ],
        on="province_name_en",
        how="left",
        validate="one_to_one",
    )
    fyears = registry.years("route_frequency")
    summary["frequency_data_year"] = pd.array(
        [max(fyears) if fyears else None] * len(summary), dtype="Int64"
    )
    return summary.sort_values("province_code").reset_index(drop=True)


def validate_provincial_profiles(profiles):
    """Check Milestone 1 definition-of-done invariants.

    Args:
        profiles: Long-format provincial_profiles frame.

    Returns:
        Report dict with ok, expected_provinces, years and errors.
    """
    errors = []
    per_year = {}
    for year, block in profiles.groupby("data_year"):
        year = int(year)
        statuses = sorted(block["data_status"].astype(str).unique())
        per_year[year] = {"rows": len(block), "data_status": statuses}
        if len(block) != len(PROVINCES):
            errors.append(f"data_year={year}: {len(block)} rows")
        if len(statuses) != 1:
            errors.append(f"data_year={year}: mixed status {statuses}")
    return {"ok": not errors, "expected_provinces": len(PROVINCES), "years": per_year, "errors": errors}

def write_processed_tables(profiles, routes, summary, out_dir=None):
    """Persist the three Milestone 1 tables as Parquet.

    Args:
        profiles: provincial_profiles.
        routes: interprovincial_routes.
        summary: route_frequency_summary.
        out_dir: Override output directory.

    Returns:
        Mapping of table name to written path.
    """
    target = out_dir or PROCESSED_DIR
    target.mkdir(parents=True, exist_ok=True)
    written = {}
    for name, frame in (
        ("provincial_profiles", profiles),
        ("interprovincial_routes", routes),
        ("route_frequency_summary", summary),
    ):
        path = target / f"{name}.parquet"
        out = frame.copy()
        if "frequency_status" in out.columns:
            out["frequency_status"] = out["frequency_status"].astype("object")
        out.to_parquet(path, index=False)
        written[name] = path
    return written

def frequency_null_report(routes):
    """Summarise, per province, how many routes lack frequency data.

    This is the artefact the dashboard shows next to any average, so a user
    can see the denominator. It never mutates the routes frame.

    Args:
        routes: Output of build_interprovincial_routes.

    Returns:
        Frame with origin_province, routes, reported, unknown and unknown_share.
    """
    grouped = (
        routes.groupby("origin_province", observed=True)["frequency_status"]
        .value_counts().unstack(fill_value=0).reset_index()
    )
    for col in ("reported", "unknown"):
        if col not in grouped.columns:
            grouped[col] = 0
    grouped["routes"] = grouped["reported"] + grouped["unknown"]
    grouped["unknown_share"] = np.where(
        grouped["routes"] > 0,
        grouped["unknown"] / grouped["routes"],
        np.nan,
    )
    return grouped.rename(
        columns={
            "reported": "reported_frequency_routes",
            "unknown": "unknown_frequency_routes",
        }
    )
