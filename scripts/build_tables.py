import logging
import pathlib

from src.config import load_vintage_registry
from src.data_layer import (
    build_interprovincial_routes,
    build_provincial_profiles,
    build_route_frequency_summary,
    frequency_null_report,
    load_raw,
    validate_provincial_profiles,
    write_processed_tables,
)

logging.basicConfig(level=logging.INFO)

registry = load_vintage_registry()
gpp = load_raw("provincial_gpp_raw.csv")
routes_raw = load_raw("interprovincial_routes_raw.csv")
freq_raw = load_raw("route_frequency_raw.csv")

profiles = build_provincial_profiles(gpp, registry)
routes = build_interprovincial_routes(routes_raw, freq_raw, registry)
slice_primary = profiles[profiles["data_year"] == registry.primary_data_year]
summary = build_route_frequency_summary(routes, slice_primary, registry)

report = validate_provincial_profiles(profiles)
print("validation", report["ok"], report["years"])
print("profiles", profiles.shape, "routes", routes.shape, "summary", summary.shape)
print("frequency", routes["frequency_status"].value_counts().to_dict())
nulls = frequency_null_report(routes)
print("unknown routes", int(nulls["unknown_frequency_routes"].sum()), "of", len(routes))

written = write_processed_tables(profiles, routes, summary)
for name, path in written.items():
    print(name, pathlib.Path(path).stat().st_size, "bytes")
