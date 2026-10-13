# Created By Swapna Deshpande
# Date: 12/12/2025
# Purpose: Find missing coordinates using Postmile, Route, and County.
# Utilization: ArcGIS Pro tool / notebook used by the Permitting team.
# ESA data is planned to be processed under the APD script.
# PGE POC - Julein Hall and Kim Hoang
# Updated 10/13/2026: Read the current user's OneDrive-synced SharePoint
# workbook instead of the hardcoded D10_ESA.csv input.

import arcpy
import os

# -------------------------------------------------------------------
# USER INPUTS = Variables
# -------------------------------------------------------------------
# Relative to each user's business OneDrive folder; no username is fixed.
sharepoint_relative_path = os.path.join(
    "VM Permitting - Central Valley and Central Coast",
    "D10 ESA.xlsx"
)

# Leave blank to import the FIRST worksheet. Set an exact tab name if needed.
excel_sheet = ""
excel_header_row = 1

ref_fc = r"O:\GIS_TEAM\PGE_EVM\Data\Library\Library\HWY_SHN_Postmiles_Tenth.gdb\HWY_SHN_Postmiles_Tenth_with_WGS84_coordinates"
output_folder = r"O:\GIS_TEAM\ERM_GIS\Analysis\ESA"
gdb_name = "ESA.gdb"
output_fc_name = "District_10_ESA_xypopulated"

# Final buffers: District_10_ESA_xypopulated_Buffer_0_05mi
# Spaces in the workbook filename are supported.
# OneDrive must sync this SharePoint folder for the Windows account running
# the script. Every execution imports the current local workbook again.

# -------------------------------------------------------------------
# RESOLVE THE CURRENT USER'S SHAREPOINT / ONEDRIVE INPUT
# -------------------------------------------------------------------
def resolve_sharepoint_workbook(relative_path):
    """Find this workbook in the current Windows user's OneDrive folders."""
    user_profile = os.environ.get("USERPROFILE") or os.path.expanduser("~")

    # Business OneDrive can be located outside the default profile folder.
    # The profile fallback reproduces the supplied path for each user.
    candidate_roots = [
        os.environ.get("OneDriveCommercial"),
        os.path.join(user_profile, "OneDrive - PGE"),
        os.environ.get("OneDrive"),
    ]

    checked_paths = []
    seen_paths = set()
    for root in candidate_roots:
        if not root:
            continue

        candidate = os.path.normpath(os.path.join(root, relative_path))
        path_key = os.path.normcase(candidate)
        if path_key in seen_paths:
            continue
        seen_paths.add(path_key)
        checked_paths.append(candidate)

        if os.path.isfile(candidate):
            return candidate

    raise FileNotFoundError(
        "The SharePoint-synced D10 ESA.xlsx workbook was not found for "
        "the Windows account running this script. Sync the SharePoint "
        "folder through OneDrive on this computer.\nChecked paths:\n - "
        + "\n - ".join(checked_paths)
    )


def require_fields(dataset, required_fields, label):
    """Stop early if an input is missing fields used by the existing code."""
    available_fields = [field.name for field in arcpy.ListFields(dataset)]
    available_lower = {name.lower() for name in available_fields}
    missing_fields = [
        name for name in required_fields if name.lower() not in available_lower
    ]
    if missing_fields:
        raise ValueError(
            f"{label} is missing required fields: {', '.join(missing_fields)}.\n"
            f"Available fields: {', '.join(available_fields)}.\n"
            "For the workbook, check excel_sheet, excel_header_row, and "
            "the column headings."
        )


# Retain the original variable name so all input connections use csv_path.
# This now points to an XLSX workbook, not a CSV file.
csv_path = resolve_sharepoint_workbook(sharepoint_relative_path)

# -------------------------------------------------------------------
# VALIDATE CONNECTIONS BEFORE PROCESSING
# -------------------------------------------------------------------
print("Checking input and output connections...")
print(f"SharePoint-synced workbook (csv_path): {csv_path}")
print(f"Excel worksheet: {excel_sheet or '(first worksheet)'}")
print(f"Header row: {excel_header_row}")
print(f"Reference feature class: {ref_fc}")
print(f"Output folder: {output_folder}")

# Opening the file confirms it can be read and lets OneDrive hydrate an
# online-only file when the OneDrive client is available.
try:
    with open(csv_path, "rb") as workbook_file:
        if not workbook_file.read(1):
            raise ValueError(f"The input workbook is empty: {csv_path}")
except OSError as exc:
    raise OSError(
        f"Cannot read the synced workbook: {csv_path}. "
        "Confirm OneDrive has synced it and the running Windows account "
        "can open the file."
    ) from exc

if not arcpy.Exists(ref_fc):
    raise FileNotFoundError(
        f"Reference feature class not found: {ref_fc}. "
        "Confirm the O: drive is mapped for the Windows account running "
        "this script."
    )

if not os.path.isdir(output_folder):
    raise FileNotFoundError(
        f"Output folder not found: {output_folder}. "
        "Confirm the O: drive mapping and folder access."
    )

require_fields(
    ref_fc,
    ["Route", "PMc", "County", "Latitude", "Longitude"],
    "Reference feature class"
)

wgs84 = arcpy.SpatialReference(4326)
arcpy.env.overwriteOutput = True

# -------------------------------------------------------------------
# 1. CREATE GDB & SET WORKSPACE
# -------------------------------------------------------------------
gdb_path = os.path.join(output_folder, gdb_name)

if not arcpy.Exists(gdb_path):
    print("Creating GDB...")
    arcpy.CreateFileGDB_management(output_folder, gdb_name)

arcpy.env.workspace = gdb_path

# -------------------------------------------------------------------
# 2. IMPORT THE CURRENT EXCEL WORKBOOK AS A GDB TABLE
# -------------------------------------------------------------------
print("Importing the current SharePoint-synced Excel workbook to table...")

tbl = os.path.join(gdb_path, "Input_Table")

# Refresh the intermediate input table on every run.
if arcpy.Exists(tbl):
    arcpy.management.Delete(tbl)

try:
    arcpy.conversion.ExcelToTable(
        csv_path,
        tbl,
        excel_sheet,
        excel_header_row
    )
except arcpy.ExecuteError as exc:
    raise RuntimeError(
        f"Excel import failed for: {csv_path}.\n"
        "Confirm the workbook is synced, the worksheet/header settings "
        "are correct, and ArcGIS Pro can read this Excel file.\n"
        f"ArcPy details: {arcpy.GetMessages(2)}"
    ) from exc

require_fields(
    tbl,
    [
        "SRC_Rx_X6_Longitude",
        "SRC_Rx_Y6_Latitude",
        "GIS_Route",
        "GIS_PM_c",
        "County_1",
    ],
    "Imported Excel table"
)

input_count = int(arcpy.management.GetCount(tbl)[0])
if input_count == 0:
    raise ValueError(
        "The selected Excel worksheet imported zero records. "
        "Check excel_sheet and excel_header_row."
    )
print(f"Imported input records: {input_count}")
print("Input/reference connections and required fields validated.")

# Ensure numeric X and Y fields exist
for f in ["X_num", "Y_num"]:
    if f not in [fld.name for fld in arcpy.ListFields(tbl)]:
        arcpy.AddField_management(tbl, f, "DOUBLE")

# Convert X and Y into numeric fields (ignores nulls safely)
with arcpy.da.UpdateCursor(tbl, ["SRC_Rx_X6_Longitude", "SRC_Rx_Y6_Latitude", "X_num", "Y_num"]) as cur:
    for x, y, xn, yn in cur:
        try:
            xn = float(x) if x not in (None, "") else None
        except:
            xn = None
        try:
            yn = float(y) if y not in (None, "") else None
        except:
            yn = None
        cur.updateRow([x, y, xn, yn])

# -------------------------------------------------------------------
# 3. CONVERT CLEAN TABLE -> POINT FC
# -------------------------------------------------------------------
print("Creating points from cleaned numeric fields...")

points_fc = os.path.join(gdb_path, "Input_Points")

arcpy.management.XYTableToPoint(
    tbl,
    points_fc,
    "X_num",
    "Y_num",
    coordinate_system=wgs84
)

# -------------------------------------------------------------------
# Helper: treat any whole-number P as a float with .0
# -------------------------------------------------------------------
def as_float_if_whole_number(p):
    """
    Convert P to float with .0 if it represents a whole number.
    - '33' -> 33.0
    - 33 -> 33.0
    - '033' -> 33.0
    - '33.0' -> 33.0
    - '33.000' -> 33.0
    - '33.5' -> 33.5 (unchanged)
    Non-parsable values returned as-is.
    """
    if p is None:
        return None
    try:
        val = float(str(p).strip())
        if val.is_integer():
            return float(int(val))  # ensures 33.0
        else:
            return val
    except:
        return p

# -------------------------------------------------------------------
# 4. BUILD REFERENCE DICTIONARY (R, P, County) AND IGNORE DUPLICATES
# -------------------------------------------------------------------
print("Reading reference layer...")

ref_dict = {}          # maps (Ro, Pc, County) -> (lat, lon)
dup_ref_keys = 0       # count duplicates ignored

# NOTE: No normalization of County or R; only P is coerced to number.0 if whole
with arcpy.da.SearchCursor(ref_fc, ["Route", "PMc", "County", "Latitude", "Longitude"]) as cursor:
    for r, p, county, lat, lon in cursor:
        # Skip incomplete keys / missing coords
        if r in (None, "") or p in (None, "") or county in (None, ""):
            continue
        if lat in (None, "") or lon in (None, ""):
            continue

        # Treat whole-number P as float with .0 to standardize keys
        p_key = as_float_if_whole_number(p)

        key = (r, p_key, county)

        # Ignore duplicates (keep the first)
        if key in ref_dict:
            dup_ref_keys += 1
            continue

        # Store a single (lat, lon) tuple
        try:
            ref_dict[key] = (float(lat), float(lon))
        except:
            # If lat/lon can't be cast to float, skip
            continue

print(f"Reference keys loaded: {len(ref_dict)}; duplicates ignored: {dup_ref_keys}")

# -------------------------------------------------------------------
# 5. FIX MISSING X/Y USING GIS_R + GIS_P + County
# -------------------------------------------------------------------
print("Fixing missing coordinates...")

missing_after_update = []
warnings = []

with arcpy.da.UpdateCursor(points_fc, ["OID@", "GIS_Route", "GIS_PM_c", "County_1", "X_num", "Y_num"]) as cursor:
    for oid, r, p, county, x, y in cursor:

        # If missing or null
        if x in (None, "") or y in (None, ""):

            # Treat whole-number P from the input as number.0 for key matching
            p_key = as_float_if_whole_number(p)

            key = (r, p_key, county)

            if key in ref_dict:
                # Unpack single (lat, lon) tuple
                lat, lon = ref_dict[key]

                # Update X_num (lon) and Y_num (lat)
                cursor.updateRow([oid, r, p, county, lon, lat])
            else:
                missing_after_update.append((oid, r, p, county))

print("Updating point geometry from new X/Y fields...")

with arcpy.da.UpdateCursor(points_fc, ["SHAPE@", "X_num", "Y_num"]) as cur:
    for shape, x, y in cur:
        if x not in (None, "") and y not in (None, ""):
            # assign new geometry in WGS84 (X=lon, Y=lat)
            new_point = arcpy.Point(float(x), float(y))
            cur.updateRow([arcpy.PointGeometry(new_point, wgs84), x, y])

# -------------------------------------------------------------------
# 6. OUTPUT FINAL FEATURE CLASS
# -------------------------------------------------------------------
output_fc = os.path.join(gdb_path, output_fc_name)
arcpy.CopyFeatures_management(points_fc, output_fc)

# -------------------------------------------------------------------
# 7. CREATE 0.05-MILE BUFFERS AROUND OUTPUT POINTS (GEODESIC)
# -------------------------------------------------------------------
print("Creating 0.05-mile buffers around points...")

buffers_fc = os.path.join(gdb_path, f"{output_fc_name}_Buffer_0_05mi")
# Use geodesic buffers since points are in WGS84.
arcpy.analysis.Buffer(
    in_features=output_fc,
    out_feature_class=buffers_fc,
    buffer_distance_or_field="0.05 Miles",
    line_side="FULL",
    line_end_type="ROUND",
    dissolve_option="NONE",
    dissolve_field=None,
    method="GEODESIC"
)

# -------------------------------------------------------------------
# REPORT RESULTS
# -------------------------------------------------------------------
print("\n---- COMPLETE ----")
print(f"Reference duplicates ignored: {dup_ref_keys}")

if warnings:
    print("\nWARNINGS:")
    for w in warnings:
        print(" -", w)

if missing_after_update:
    print("\nRECORDS STILL MISSING X/Y AFTER UPDATE:")
    for oid, r, p, county in missing_after_update:
        print(f" - OID {oid} (GIS_R={r}, GIS_P={p}, County={county})")
else:
    print("\nAll missing X/Y coordinates successfully filled.")

print("\nFinal output points:\n", output_fc)
print("Buffers created:\n", buffers_fc)

