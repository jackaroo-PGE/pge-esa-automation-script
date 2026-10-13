#Created By Swapna Deshpande
#Date: 12/12/2025
#Purpose: to Find out missing coodinates based on combination of Postmile, Route information and county info
#Utilization- This scrip will be converted to arc pro tool and executes by Permitting team
#ESA data is planned to be processed under APD sript
#PGE POC - Julein Hall and Kim Hoang



# -------------------------------------------------------------------
# USER INPUTS = Variables
# -------------------------------------------------------------------
csv_path = r"O:\GIS_TEAM\PGE_EVM\External_Received\ESA\D10_ESA.csv"          # CSV with fields: X, Y, GIS_R, GIS_P
ref_fc = r"O:\GIS_TEAM\PGE_EVM\Data\Library\Library\HWY_SHN_Postmiles_Tenth.gdb\HWY_SHN_Postmiles_Tenth_with_WGS84_coordinates"  # reference FC with: R, P, Latitude, Longitude
output_folder = r"O:\GIS_TEAM\ERM_GIS\Analysis\ESA"
gdb_name = "ESA.gdb"
output_fc_name = "District_10_ESA_xypopulated"

###WARNING
####Find Final populated values in Featurecall called 'District_10_ESA_Buffer_0_05mi'
#### Remove spaces from inputname before running
#### Make Sure Field Names in given Table match code Line 154

import arcpy
import os


wgs84 = arcpy.SpatialReference(4326)
# -------------------------------------------------------------------

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
# 2. IMPORT CSV AS GDB TABLE (AVOIDS 000732 PROBLEMS)
# -------------------------------------------------------------------
print("Importing CSV to table...")

tbl = os.path.join(gdb_path, "Input_Table")
arcpy.TableToTable_conversion(csv_path, gdb_path, "Input_Table")

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
# 3. CONVERT CLEAN TABLE → POINT FC
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
# Use geodesic buffers since points are in a geographic coordinate system (WGS84)
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
