"""Central, transparent configuration for the repeated-routes pipeline (Phase 1).

Every threshold used anywhere in ``repeated_routes`` lives here, as a dataclass
field with an explicit default. Nothing is hardcoded downstream. Defaults are
an initial, documented starting point (see ``reports/repeated_routes_phase1.md``
for the sensitivity analysis that motivates the ``recommended`` values) -- they
are not presented as scientifically final.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

import yaml


@dataclasses.dataclass
class RepeatedRoutesConfig:
    name: str = "recommended"

    # --- Coordinate reference systems -------------------------------------------------
    # UTM 32N: standard metric CRS for the Bologna area (44-45N, 11-12E), used for every
    # distance/area/bearing computation. WGS84 (EPSG:4326) is kept for interoperable output.
    crs_metric_epsg: int = 32632
    crs_geographic_epsg: int = 4326

    # --- Campaign validity mask (documents the QC-column correspondence used here) ----
    # A point is usable for geometry if it is flagged for route mapping by the QC
    # "recommended" profile (use_for_route_mapping = ~(qc_gps_freeze | qc_gps_jump))
    # AND has non-missing coordinates. use_for_route_mapping alone does not exclude
    # qc_coord_missing rows in the current QC code (documented gap, see
    # reports/targeted_qc_audit.md section C.8) -- that exclusion is applied here,
    # at the repeated_routes layer, without modifying gps_qc.py.
    require_qc_route_mapping: bool = True
    exclude_missing_coordinates: bool = True

    # --- Campaign continuity: splitting a campaign into campaign_part_id -------------
    # A new part starts when the gap between two consecutive *valid* points exceeds
    # this many seconds (distinct from, and larger than, the QC row-level qc_time_gap
    # flag at 2.0s -- that flag marks single missed pings; this threshold marks gaps
    # long enough that straight-line interpolation across them would be misleading,
    # e.g. Bluetooth dropouts).
    part_split_time_gap_s: float = 120.0
    # A new part also starts when the implied speed between two consecutive valid
    # points exceeds this bound at a short time delta -- catches GPS jumps that only
    # become visible after already-flagged rows have been removed.
    part_split_max_speed_kmh: float = 150.0
    part_split_jump_dt_s: float = 5.0
    # Minimum number of valid points for a part to be kept at all.
    min_part_points: int = 2

    # --- Resampling --------------------------------------------------------------------
    resampling_distance_m: float = 10.0

    # --- Pairwise matching ---------------------------------------------------------------
    matching_tolerance_m: float = 20.0
    minimum_shared_length_m: float = 250.0
    minimum_overlap_fraction: float = 0.70
    maximum_internal_gap_m: float = 40.0
    minimum_consecutive_matches: int = 15
    # Below this |Spearman correlation| between along-A and projected-along-B position,
    # a run is treated as geometric coincidence rather than a coherent shared traversal.
    direction_correlation_threshold: float = 0.5
    # A run found from A's points is only accepted if an independently-detected run
    # from B's own points (matched against A) covers at least this fraction of A's
    # span (section 8, step 6: "verificare reciprocamente anche B rispetto ad A").
    reciprocal_overlap_min_fraction: float = 0.5
    # Circular bearing difference thresholds (degrees) used as a secondary,
    # corroborating signal for direction classification.
    bearing_same_direction_max_deg: float = 45.0
    bearing_opposite_direction_min_deg: float = 135.0

    # --- Candidate pair prefilter -------------------------------------------------------
    # Buffer radius (in the metric CRS) used to build candidate polygons for the
    # spatial-index prefilter; matches the matching tolerance by default.
    candidate_buffer_m: float = 20.0

    # --- Segment consolidation (section 10) --------------------------------------------
    # Legacy configuration field retained for compatibility, no longer used.
    # Corridor identity uses complete geometric compatibility and connected
    # pairwise evidence (see corridors.py), never overlap percentage alone.
    consolidation_same_track_overlap_fraction: float = 0.70

    # --- Campaign-level quality classification (transparent, documented thresholds) ---
    # A campaign is "excluded" outright (kept in the inventory, skipped from matching)
    # if it is too short/sparse to represent a meaningful trajectory.
    min_campaign_duration_minutes_excluded: float = 1.0
    min_campaign_valid_points_excluded: int = 20
    # Otherwise classified high/medium/low from valid_fraction, gap_ratio and
    # freeze_fraction (all computed in campaign_inventory.py).
    quality_valid_fraction_high: float = 0.90
    quality_valid_fraction_medium: float = 0.75
    quality_gap_ratio_high: float = 0.05
    quality_gap_ratio_medium: float = 0.20
    quality_freeze_fraction_high: float = 0.05
    quality_freeze_fraction_medium: float = 0.15
    # A raw sampling gap larger than this counts toward gap_ratio / has_timestamp_gaps
    # (distinct from, and coarser than, the 2.0s QC row-level qc_time_gap flag).
    inventory_gap_threshold_s: float = 5.0

    # --- Passage / segment matching-quality classification -----------------------------
    segment_quality_distance_high_m: float = 8.0
    segment_quality_distance_medium_m: float = 15.0

    # --- Local time-of-day bins (Europe/Rome local time, configurable, not solar) ------
    time_bin_boundaries: dict[str, float] = dataclasses.field(
        default_factory=lambda: {
            "night": 0.0,
            "early_morning": 5.0,
            "morning": 7.5,
            "midday": 10.5,
            "afternoon": 13.5,
            "late_afternoon": 16.5,
            "evening": 19.0,
        }
    )

    # --- comparison_potential_score weights (must sum to 1.0; validated in __post_init__) --
    score_weights: dict[str, float] = dataclasses.field(
        default_factory=lambda: {
            "date_diversity": 0.25,
            "passage_count": 0.15,
            "time_bin_diversity": 0.15,
            "segment_length": 0.10,
            "geometric_quality": 0.15,
            "qc_quality": 0.10,
            "direction_diversity": 0.10,
        }
    )
    # Normalization caps used inside the score sub-terms (see scoring.py).
    score_norm_n_dates: float = 5.0
    score_norm_n_passages: float = 8.0
    score_norm_n_time_bins: float = 4.0
    score_norm_segment_length_m: float = 1000.0
    score_class_excellent: float = 75.0
    score_class_good: float = 50.0
    score_class_limited: float = 25.0

    def __post_init__(self) -> None:
        weight_sum = sum(self.score_weights.values())
        if abs(weight_sum - 1.0) > 1e-6:
            raise ValueError(f"score_weights must sum to 1.0, got {weight_sum}")

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RepeatedRoutesConfig":
        known = {f.name for f in dataclasses.fields(cls)}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)

    @classmethod
    def from_yaml(cls, path: str | Path) -> "RepeatedRoutesConfig":
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        return cls.from_dict(data)

    def to_yaml(self, path: str | Path) -> None:
        Path(path).write_text(
            yaml.safe_dump(self.to_dict(), sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )


def load_config(name_or_path: str) -> RepeatedRoutesConfig:
    """Resolve a repeated-routes configuration by preset name or file path.

    Preset names map to ``config/repeated_routes_<name>.yaml``. Anything else is
    treated as a direct path to a YAML file.
    """
    path = Path(name_or_path)
    if path.is_file():
        return RepeatedRoutesConfig.from_yaml(path)
    if path.name == name_or_path and "/" not in name_or_path and "\\" not in name_or_path:
        from ..config_resources import read_preset
        return RepeatedRoutesConfig.from_dict(read_preset(f"repeated_routes_{name_or_path}.yaml"))
    raise FileNotFoundError(
        f"No repeated-routes configuration file found: {name_or_path}"
    )
