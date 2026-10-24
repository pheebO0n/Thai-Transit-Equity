# Transit Equity Thailand - Milestone 1

Data foundation for a transit-equity decision-support tool: provincial GPP
per capita across multiple vintages, route existence, and route frequency
(including a first-class 'unknown' state).

Status: Milestone 1 complete (human gate before Milestone 2)

## 1. Architecture & design decisions

- Vintage registry as the only source of truth: config/data_vintages.yaml
 resolves every data_year / report_year / source / data_status tuple and
 carries all tunables (weights, percentile method, coverage thresholds).
 No Python module hardcodes a year or a threshold.
- Provincial GPP is stored in long format, one row per (province, data_year).
 2566/2567 rows are data_status='actual'; 2568 rows are data_status='estimate'.
 The two can never collapse into a single column, so there is no accidental
 actual-vs-estimate blend.
- Vintage guard (src/vintage_guard.py) is the single choke point:
 tag_vintage() stamps rows; assemble_frame() refuses to combine actuals
 with estimates unless the caller passes allow_mixed=True plus a reason.
- Frequency view (route_frequency_summary) is a left join on the 77-province
 roster. Provinces with no known-frequency routes get NaN aggregates
 (instead of 0) and an explicit unknown_frequency_route_count.
- Geospatial CRS are configured in the registry: EPSG:4326 (WGS 84) for
 storage and API payloads, EPSG:32647 (UTM 47N) by default for buffer or
 area operations, EPSG:32648 (UTM 48N) for provinces east of 102E
 (Province.utm_zone exposes the choice).

## 2. Implementation

Tree:

- config/data_vintages.yaml vintage registry + gap / weight config
- data/raw/.csv source extracts (GPP, routes, frequency)
- data/processed/.parquet build output (profiles, routes, view)
- src/config.py registry loader + validation
- src/vintage_guard.py tagging + mixed-vintage tripwire
- src/provinces.py 77-province roster (Lon / Lat in EPSG:4326)
- src/thai_names.py Thai provincial names (ASCII-safe source)
- src/data_layer.py builders + completeness validation
- scripts/build_tables.py one-shot Parquet build
- tests/test_milestone1.py 11 tests

Tables produced (current extract):

- provincial_profiles: 231 rows (77 provinces x 3 data years)
 columns: province_code, province_name_en/th, region, lat, lon,
 gpp_per_capita, gpp_rank, gpp_percentile, vintage_label,
 data_year, report_year, source, data_status
- interprovincial_routes: 131 rows
 columns: route_id, origin_province, destination_province, route_category,
 operator, distance_km, daily_trips, frequency_status, frequency_data_year,
 data_year, report_year, source, data_status
- route_frequency_summary: 77 rows
 columns: province_code, province_name_en, region,
 avg_daily_trips_per_route, total_daily_trips_departing, operator_count,
 operator_diversity_index, known_frequency_route_count,
 unknown_frequency_route_count, frequency_coverage_ratio, + vintage columns

Run:

 python -X utf8 -c "import sys; sys.path.insert(0,'.'); exec(open('scripts/build_tables.py', encoding='utf-8').read())"
 python -m pytest tests -q
---
config/data_vintages.yaml      vintage registry + gap / weight config
data/raw/*.csv                 source extracts (GPP, routes, frequency)
data/processed/*.parquet       build output (profiles, routes, view)
src/config.py               registry loader + validation
src/vintage_guard.py        tagging + mixed-vintage tripwire
src/provinces.py            77-province roster (Lon / Lat in EPSG:4326)
src/thai_names.py          Thai provincial names (ASCII-safe source)
src/data_layer.py           builders + completeness validation
scripts/build_tables.py      one-shot Parquet build
tests/test_milestone1.py     11 tests
---

Tables produced:

Table                     Grain                Rows    Key columns
provincial_profiles       province x data_year   231    gpp_per_capita, gpp_rank, gpp_percentile, vintage_label
interprovincial_routes   route                 131    origin / destination / category / operator / daily_trips / distance_km / frequency_status
route_frequency_summary  province               77     avg_daily_trips_per_route / total_daily_trips_departing / operator_diversity_index / known + unknown counts / frequency_coverage_ratio

Run:

    python -X utf8 -c "import sys; sys.path.insert(0,'.'); exec(open('scripts/build_tables.py', encoding='utf-8').read())"
    python -m pytest tests -q
## 3. Edge cases (especially vintage mismatch)

- **Actual vs estimate mixing.** 2568 is an estimate. Any join that would
  combine it with 2566/2567 raises VintageMergeError unless the caller
  opts in. Tested: test_guard_rejects_mixed_vintages,
  test_guard_allows_mixed_with_opt_in, test_tag_vintage_refuses_retag.
- **Re-tagging.** A 2567 frame cannot be relabelled as 2568; tag_vintage
  detects the existing data_year and raises.
- **Unknown vintage.** Requesting a year that is not in the registry
  (e.g. 2570) fails loudly with the list of registered years.
- **Missing frequency.** Routes with no timetable keep daily_trips = NaN and
  frequency_status = 'unknown'. They are counted in unknown_frequency_route_count
  and excluded from means via skipna, never zero-filled. Dropping the
  timetable is tested to keep the same rowe count.
- **Frequency coverage.** Only 59 of 627 Category-3 routes are covered by the
  BorKorSor timetable. frequency_coverage_ratio is exposed so any consumer
  can see the denominator behind an average.
- **Province count guard.** The builder raises if any data_year does not produce
  exactly 77 rows.

## 4. Testing strategy

- 11 pytest tests in tests/test_milestone1.py, all passing:
  - vintage merge guard (4), NULL frequency (3), view completeness (2),
    roster completeness (1), config rejection (1).
- Tests run against the shipped raw CSV and the real registry -- no mocks
  for the data path.
- Run command: python -m pytest tests -q

## 5. Deployment notes

- For the API (Milestone 3), the registry path is served from the
  repository root; keep config/data_vintages.yaml in the image and do
  not let it be overridden at runtime without an audit log line.
- Parquet files in data/processed/are build artefacts; regenerate them from
  the raw CSVs in the build pipeline rather than editing by hand.
- Python 3.12 (matches Streamlit Cloud default); dependencies pinned in
  requirements.txt.
