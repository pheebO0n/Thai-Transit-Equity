"""Unit tests for Milestone 1 (run: python -m pytest -q).

These guard the three Milestone 1 rules that are easy to break silently:
  1. actuals and estimates must not merge without an explicit opt-in,
  2. routes without frequency data are flagged and never zero-filled,
  3. the frequency view always returns 77 provinces.
"""

from __future__ import annotations

import pytest

from src.config import VintageConfigError, load_vintage_registry
from src.data_layer import (
    build_interprovincial_routes,
    build_provincial_profiles,
    build_route_frequency_summary,
    frequency_null_report,
    load_raw,
    validate_provincial_profiles,
)
from src.provinces import PROVINCES, assert_catalogue_complete
from src.vintage_guard import (
    VintageMergeError,
    assemble_frame,
    assert_single_vintage,
    tag_vintage,
)

@pytest.fixture(scope="module")
def registry():
    """Load the shipped vintage registry once per module."""
    return load_vintage_registry()

@pytest.fixture(scope="module")
def raw():
    """Raw CSV extracts as shipped in data/raw."""
    return {
        "gpp": load_raw("provincial_gpp_raw.csv"),
        "routes": load_raw("interprovincial_routes_raw.csv"),
        "freq": load_raw("route_frequency_raw.csv"),
    }

@pytest.fixture(scope="module")
def profiles(raw, registry):
    """Provincial profiles for all registered gpp years."""
    return build_provincial_profiles(raw["gpp"], registry)

@pytest.fixture(scope="module")
def routes(raw, registry):
    """Interprovincial routes with frequency joined."""
    return build_interprovincial_routes(raw["routes"], raw["freq"], registry)
def test_profiles_have_77_provinces_per_year(profiles):
    """Definition of done: all 77 provinces present for every data year."""
    assert_catalogue_complete()
    counts = profiles.groupby("data_year").size()
    assert set(counts.tolist()) == {77}
    assert set(profiles["province_code"]) == {p.code for p in PROVINCES}
    report = validate_provincial_profiles(profiles)
    assert report["ok"], report["errors"]


def test_vintage_flags_per_year(profiles):
    """2568 is estimate; 2566/2567 must remain actual and not leak."""
    status = profiles["data_status"].astype(str)
    actual_years = set(profiles.loc[status == "actual", "data_year"])
    estimate_years = set(profiles.loc[status == "estimate", "data_year"])
    assert actual_years == {2566, 2567}
    assert estimate_years == {2568}


def test_guard_rejects_mixed_vintages(profiles, registry):
    """Assembling 2567 actual + 2568 estimate must raise by default."""
    actual = profiles[profiles.data_year == 2567]
    estimate = profiles[profiles.data_year == 2568]
    with pytest.raises(VintageMergeError):
        assemble_frame([(actual, "gpp", 2567), (estimate, "gpp", 2568)], registry)


def test_guard_allows_mixed_with_opt_in(profiles, registry):
    """Explicit opt-in is permitted and reported as mixed."""
    actual = profiles[profiles.data_year == 2567]
    estimate = profiles[profiles.data_year == 2568]
    merged, report = assemble_frame(
        [(actual, "gpp", 2567), (estimate, "gpp", 2568)],
        registry,
        allow_mixed=True,
        reason="sensitivity view",
    )
    assert report.mixed
    assert set(report.statuses) == {"actual", "estimate"}
    assert len(merged) == len(actual) + len(estimate)


def test_tag_vintage_refuses_retag(profiles, registry):
    """Re-tagging a 2567 frame as 2568 must fail."""
    actual = profiles[profiles.data_year == 2567]
    with pytest.raises(VintageMergeError):
        tag_vintage(actual, registry, "gpp", 2568)


def test_assert_single_vintage(profiles):
    """API boundary check rejects a multi-year frame."""
    with pytest.raises(VintageMergeError):
        assert_single_vintage(profiles, 2567)
    slice_ = profiles[profiles.data_year == 2568]
    assert_single_vintage(slice_, 2568, status="estimate")


def test_unknown_frequency_is_flagged_not_imputed(routes):
    """Routes without timetables keep NaN and are counted, not dropped."""
    unknown = routes[routes.frequency_status == "unknown"]
    assert len(unknown) > 0
    assert unknown["daily_trips"].isna().all()
    reported = routes[routes.frequency_status == "reported"]
    assert reported["daily_trips"].notna().all()
    assert len(routes) == len(unknown) + len(reported)


def test_routes_keep_existence_without_frequency(raw):
    """Dropping the timetable must not remove route rows."""
    registry = load_vintage_registry()
    with_freq = build_interprovincial_routes(raw["routes"], raw["freq"], registry)
    all_unknown = build_interprovincial_routes(raw["routes"], None, registry)
    assert len(all_unknown) == len(with_freq)
    assert (all_unknown.frequency_status == "unknown").all()
    assert all_unknown["daily_trips"].isna().all()


def test_summary_covers_all_77_provinces(routes, profiles, registry):
    """The view is a left join on the roster, so no province can vanish."""
    slice_ = profiles[profiles.data_year == 2567]
    summary = build_route_frequency_summary(routes, slice_, registry)
    assert len(summary) == 77
    no_freq = summary["known_frequency_route_count"] == 0
    assert summary.loc[no_freq, "avg_daily_trips_per_route"].isna().all()


def test_null_report_matches_routes(routes):
    """Reported + unknown counts must equal total routes per province."""
    report = frequency_null_report(routes)
    assert report["routes"].sum() == len(routes)
    assert report["unknown_frequency_routes"].sum() == (
        routes.frequency_status == "unknown"
    ).sum()


def test_unknown_vintage_is_rejected(registry):
    """Requesting an unregistered year fails loudly."""
    with pytest.raises(VintageConfigError):
        registry.meta_for("gpp", 2570)
