"""Vintage registry loader.

The single place where data_year / report_year / source /
data_status tuples are resolved. No module may invent its own vintage
metadata: everything goes through :func:`load_vintage_registry`.

Typical use::

    registry = load_vintage_registry()
    meta = registry.meta_for("gpp", 2567)      # -> VintageMeta(data_status='actual')
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

DataStatus = Literal["actual", "estimate", "stale"]

VALID_STATUSES: frozenset[str] = frozenset({"actual", "estimate", "stale"})

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = _REPO_ROOT / "config" / "data_vintages.yaml"


class VintageConfigError(RuntimeError):
    """Raised when the vintage registry is missing, malformed or inconsistent."""


@dataclass(frozen=True)
class VintageMeta:
    """Immutable vintage descriptor for one (dataset, data_year) pair.

    Attributes:
        dataset: Logical dataset name, e.g. `"gpp"`.
        data_year: Buddhist-era data year (2566, 2567, 2568, ...).
        report_year: Buddhist-era year in which the figure was published.
        source: Human-readable provenance string.
        data_status: One of `actual`, `estimate`, `stale`.
        extra: Any additional keys from the YAML block (e.g. `scope`).
    """

    dataset: str
    data_year: int
    report_year: int
    source: str
    data_status: DataStatus
    extra: dict[str, Any] = field(default_factory=dict, compare=False)

    @property
    def is_actual(self) -> bool:
        """True when the figure is a realised, non-estimated observation."""
        return self.data_status == "actual"

    def label(self) -> str:
        """Compact vintage label suitable for chart axes and API payloads."""
        return f"{self.dataset}@{self.data_year}/{self.report_year} ({self.data_status})"


@dataclass(frozen=True)
class VintageRegistry:
    """Parsed, validated view over `config/data_vintages.yaml` """

    raw: dict[str, Any]

    def meta_for(self, dataset: str, data_year: int) -> VintageMeta:
        """Return vintage metadata for `dataset` at `data_year`.

        Args:
            dataset: Key under `vintages:` in the YAML file.
            data_year: Buddhist-era data year, e.g. `2567`.

        Returns:
            A :class:`VintageMeta`.

        Raises:
            VintageConfigError: If the dataset or year is not registered.
        """
        try:
            block = self.raw["vintages"][dataset][int(data_year)]
        except KeyError as exc:
            known = sorted(self.raw.get("vintages", {}).get(dataset, {}))
            raise VintageConfigError(
                f"Unknown vintage: dataset={dataset!r} data_year={data_year!r}. "
                f"Registered years for this dataset: {known}"
            ) from exc
        return VintageMeta(
            dataset=dataset,
            data_year=int(data_year),
            report_year=int(block["report_year"]),
            source=str(block["source"]),
            data_status=block["data_status"],
            extra={k: v for k, v in block.items()
                   if k not in {"report_year", "source", "data_status"}},
        )

    def years(self, dataset: str) -> list[int]:
        """Return all registered data years for `dataset`, ascending."""
        return sorted(int(y) for y in self.raw["vintages"].get(dataset, {}))

    def actual_years(self, dataset: str) -> list[int]:
        """Return only `data_status == 'actual'` years for `dataset`."""
        return [y for y in self.years(dataset) if self.meta_for(dataset, y).is_actual]

    @property
    def primary_data_year(self) -> int:
        """Default data year used when an API caller omits `data_year`."""
        return int(self.raw["defaults"]["primary_data_year"])

    @property
    def strict_vintage(self) -> bool:
        """Whether actual/estimate mixing must raise instead of warn."""
        return bool(self.raw["defaults"]["strict_vintage"])

    @property
    def gap_weights(self) -> dict[str, float]:
        """Default existence/intensity weights for TGI_v2."""
        return {
            "existence": float(self.raw["gap_engine"]["weights"]["existence"]),
            "intensity": float(self.raw["gap_engine"]["weights"]["intensity"]),
        }

    def gap_component_weights(self, family: Literal["existence", "intensity"]) -> dict[str, float]:
        """Return the sub-component weights for one gap family."""
        key = f"{family}_components"
        return {k: float(v) for k, v in self.raw["gap_engine"][key].items()}

    @property
    def geo(self) -> dict[str, str]:
        """CRS configuration (storage CRS + UTM analysis CRS)."""
        return {k: str(v) for k, v in self.raw["geo"].items()}


def _validate(raw: dict[str, Any]) -> None:
    """Validate registry structure. Raises VintageConfigError."""
    if "vintages" not in raw or "defaults" not in raw:
        raise VintageConfigError("Registry must define top-level 'defaults' and 'vintages'.")

    for dataset, years in raw["vintages"].items():
        if not isinstance(years, dict) or not years:
            raise VintageConfigError(f"vintages.{dataset} must be a non-empty mapping.")
        for data_year, block in years.items():
            for required in ("report_year", "source", "data_status"):
                if required not in block:
                    raise VintageConfigError(
                        f"vintages.{dataset}.{data_year} is missing '{required}'."
                    )
            if block["data_status"] not in VALID_STATUSES:
                raise VintageConfigError(
                    f"vintages.{dataset}.{data_year}: data_status "
                    f"{block['data_status']!r} not in {sorted(VALID_STATUSES)}."
                )
            if int(block["report_year"]) < int(data_year):
                raise VintageConfigError(
                    f"vintages.{dataset}.{data_year}: report_year "
                    f"{0} precedes data_year.".format(block["report_year"])
                )

    weights = raw.get("gap_engine", {}).get("weights", {})
    total = sum(float(v) for v in weights.values())
    if abs(total - 1.0) > 1e-9:
        raise VintageConfigError(f"gap_engine.weights must sum to 1.0 (got {total}).")

    for family in ("existence", "intensity"):
        comp = raw.get("gap_engine", {}).get(f"{family}_components", {})
        if comp and abs(sum(float(v) for v in comp.values()) - 1.0) > 1e-9:
            raise VintageConfigError(
                f"gap_engine.{family}_components must sum to 1.0."
            )


def load_vintage_registry(path: Path | str | None = None) -> VintageRegistry:
    """Load and validate the vintage registry.

    Args:
        path: Optional override path to the YAML file. Defaults to
            `config/data_vintages.yaml` at the repository root.

    Returns:
        A validated :Registry.

    Raises:
        VintageConfigError: If the file is absent, unparseable or invalid.
    """
    cfg_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    if not cfg_path.is_file():
        raise VintageConfigError(f"Vintage registry not found at {cfg}")
    with cfg_path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    if not isinstance(raw, dict):
        raise VintageConfigError(f"{cfg} did not parse to a mapping.")
    _validate(raw)
    return VintageRegistry(raw=raw)
