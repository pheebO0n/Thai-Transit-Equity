"""Vintage-merge guard - the single choke point for actual/estimate mixing.

Design decision
---------------
All multi-source frames are assembled by :func:`assemble_frame`, which

1) resolves the vintage of each contributing block from the registry,
2) tags every row with data_year / report_year / source / data_status,
3) refuses (or loudly warns) when actuals and estimates would end up in the
   same analytical frame without an explicit opt-in.

The gap engine only reads frames produced here, so the guard cannot be
bypassed by accident.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable, Literal

import pandas as pd

from src.config import VintageRegistry

logger = logging.getLogger(__name__)

VINTAGE_COLUMNS: tuple[str, ...] = ("data_year", "report_year", "source", "data_status")


class VintageMergeError(RuntimeError):
    """Raised when actual and estimate vintages would be silently merged."""


@dataclass(frozen=True)
class MergeReport:
    """Outcome of a guard check, surfaced to API/dashboard footers.

    Attributes:
        allowed: Whether the frame may be used downstream.
        statuses: data_status values present in the merged frame.
        data_years: data_year values present in the merged frame.
        mixed: True when more than one data_status is present.
        message: Human-readable explanation for the warning/error field.
    """

    allowed: bool
    statuses: frozenset[str]
    data_years: frozenset[int]
    mixed: bool
    message: str


def tag_vintage(
    df: pd.DataFrame,
    registry: VintageRegistry,
    dataset: str,
    data_year: int,
    *,
    copy: bool = True,
) -> pd.DataFrame:
    """Stamp registry-resolved vintage columns onto `df`.

    Args:
        df: Frame to tag. Must not already contain the vintage columns.
        registry: Loaded vintage registry.
        dataset: Dataset key in the registry (e.g. "gpp").
        data_year: Buddhist-era data year to resolve.
        copy: Copy the frame before tagging.

    Returns:
        The tagged frame.

    Raises:
        VintageMergeError: If the frame already carries vintage columns with a
            different data_year.
    """
    meta = registry.meta_for(dataset, data_year)
    out = df.copy() if copy else df

    if "data_year" in out.columns:
        existing = set(pd.to_numeric(out["data_year"], errors="coerce").dropna().astype(int))
        if existing and existing != {meta.data_year}:
            raise VintageMergeError(
                f"Frame already tagged with data_year {sorted(existing)}; "
                f"refusing to re-tag as {meta.data_year}."
            )

    out["data_year"] = meta.data_year
    out["report_year"] = meta.report_year
    out["source"] = meta.source
    out["data_status"] = meta.data_status
    return out


def check_merge(
    frames: Iterable[pd.DataFrame],
    registry: VintageRegistry,
    *,
    allow_mixed: bool = False,
    reason: str = "",
) -> MergeReport:
    """Inspect frames about to be concatenated for vintage mixing.

    Args:
        frames: Tagged frames (output of :tag_vintage).
        registry: Registry providing strict_vintage policy.
        allow_mixed: Explicit opt-in to combine actuals with estimates.
        reason: Audit trail text recorded when allow_mixed is used.

    Returns:
        A :class:`MergeReport`.

    Raises:
        VintageMergeError: If statuses are mixed, allow_mixed is False and
            defaults.strict_vintage is True.
    """
    statuses: set[str] = set()
    years: set[int] = set()
    for frame in frames:
        missing = [c for c in VINTAGE_COLUMNS if c not in frame.columns]
        if missing:
            raise VintageMergeError(
                f"Untagged frame passed to check_merge (missing {missing}). "
                f"Route it through tag_vintage() first."
            )
        statuses.update(frame["data_status"].dropna().unique().tolist())
        years.update(int(y) for y in frame["data_year"].dropna().unique())

    mixed = len(statuses) > 1
    if mixed and not allow_mixed and registry.strict_vintage:
        raise VintageMergeError(
            f"Refusing to merge mixed vintages {sorted(statuses)} "
            f"across data_years {sorted(years)}. Pass allow_mixed=True with a "
            f"reason if this is intentional (e.g. a sensitivity view)."
        )
    if mixed and allow_mixed:
        logger.warning("Mixed-vintage merge explicitly allowed: %s", reason or "<no reason>")

    message = (
        f"Mixed vintages {sorted(statuses)} over data_years {sorted(years)}."
        if mixed
        else f"Single vintage {next(iter(statuses), 'none')} over data_years {sorted(years)}."
    )
    return MergeReport(
        allowed=(not mixed) or allow_mixed or not registry.strict_vintage,
        statuses=frozenset(statuses),
        data_years=frozenset(years),
        mixed=mixed,
        message=message,
    )


def assemble_frame(
    blocks: Iterable[tuple[pd.DataFrame, str, int]],
    registry: VintageRegistry,
    *,
    allow_mixed: bool = False,
    reason: str = "",
) -> tuple[pd.DataFrame, MergeReport]:
    """Tag, check and concatenate several (frame, dataset, data_year) blocks.

    Args:
        blocks: Iterable of (frame, dataset, data_year) triples.
        registry: Loaded vintage registry.
        allow_mixed: See :func:`check_merge`.
        reason: See :func:`check_merge`.

    Returns:
        (merged_frame, report). The frame is empty-but-typed when
        blocks is empty, so downstream schemas stay stable.
    """
    tagged = [tag_vintage(df, registry, dataset, year) for df, dataset, year in blocks]
    if not tagged:
        empty = pd.DataFrame(columns=list(VINTAGE_COLUMNS))
        return empty, MergeReport(
            allowed=True, statuses=frozenset(), data_years=frozenset(),
            mixed=False, message="No blocks supplied.",
        )

    report = check_merge(tagged, registry, allow_mixed=allow_mixed, reason=reason)
    merged = pd.concat(tagged, ignore_index=True, sort=False)
    merged["data_status"] = pd.Categorical(
        merged["data_status"], categories=["actual", "estimate", "stale"], ordered=True
    )
    return merged, report


def assert_single_vintage(
    df: pd.DataFrame,
    expected_year: int,
    *,
    status: Literal["actual", "estimate", "stale"] | None = None,
) -> None:
    """Assert a frame contains exactly one data year (and optionally status).

    Used at API boundaries so that a caller cannot receive a response that
    silently blends years.

    Args:
        df: Frame to check.
        expected_year: The only permitted data_year.
        status: If given, the only permitted data_status.

    Raises:
        VintageMergeError: On any mismatch.
    """
    years = set(pd.to_numeric(df["data_year"], errors="coerce").dropna().astype(int))
    if years != {expected_year}:
        raise VintageMergeError(
            f"Expected data_year={expected_year} exclusively, found {sorted(years)}."
        )
    if status is not None:
        statuses = set(df["data_status"].astype(str).dropna().unique())
        if statuses != {status}:
            raise VintageMergeError(
                f"Expected data_status={status!r} exclusively, found {sorted(statuses)}."
            )
