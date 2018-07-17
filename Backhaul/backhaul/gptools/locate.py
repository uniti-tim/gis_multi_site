import os
import arcpy
from .. import common
from ..setttings import *


def copy_features(in_fc, out_fc):
    sr = arcpy.Describe(in_fc).spatialReference
    path, name = os.path.split(out_fc)
    arcpy.CreateFeatureclass_management(path, name, "POINT", spatial_reference=sr)

    arcpy.AddField_management(out_fc, "ORIG_FID", "LONG")

    with arcpy.da.SearchCursor(in_fc, ("OID@", "SHAPE@")) as sCursor, \
            arcpy.da.InsertCursor(out_fc, ("ORIG_FID", "SHAPE@")) as iCursor:
        for row in sCursor:
            iCursor.insertRow(row)

    return out_fc


class LocateAssets(object):
    def __init__(self, remote_assets, fixed_assets, network_dataset, output_gdb):
        self.remote = remote_assets
        self.fixed = fixed_assets
        self.network = network_dataset
        self.gdb = arcpy.CreateUniqueName(TEMP_GDB, output_gdb)

        # Find the default cost
        impedance = filter(lambda f: f.usageType == "Cost" and f.useByDefault,
                           arcpy.Describe(self.network).attributes)[0].name
        cf = arcpy.na.MakeClosestFacilityLayer(self.network, common.unique_name("tempNA"), impedance)[0]
        desc = arcpy.Describe(cf)
        # Get the default locator information to build search_criteria
        self.criteria = [[getattr(desc.locators, "source{}".format(i)),
                          getattr(desc.locators, "snapType{}".format(i))] for i in range(desc.locatorCount)]
        self.tolerance = desc.searchTolerance
        common.delete(cf)

    def calc_update(self, fc, asset_type):
        arcpy.AddMessage("\t{} Calculating network locations on {} Assets...".format(common.timestamp(), asset_type))
        arcpy.na.CalculateLocations(in_point_features=fc, in_network_dataset=self.network,
                                    search_tolerance=self.tolerance, search_criteria=self.criteria)
        arcpy.AddField_management(fc, "Name", "Text")

        with arcpy.da.UpdateCursor(fc, ("OID@", "Name")) as uCursor:
            for oid, name in uCursor:
                uCursor.updateRow((oid, "{} {}".format(asset_type, oid)))

    def execute(self):
        # Create output GDB and add domain for asset type
        self.gdb = arcpy.CreateFileGDB_management(*os.path.split(self.gdb))[0]

        # Since NA.solve uses OID for start/end points, the OID of the feature classes being copied should
        # be maintained so that the attribute information can be linked back, if desired
        remote_temp = copy_features(self.remote, common.unique_name("in_memory/remoteTemp"))
        fixed_temp = copy_features(self.fixed, common.unique_name("in_memory/fixedTemp"))

        # The information that Near creates is not needed (distance to nearest feature and feature ID), so delete it.
        # Sorting the features by descending distance ensures that the furthest assets are backhauled first.
        arcpy.Near_analysis(remote_temp, fixed_temp)
        sort_temp = arcpy.Sort_management(remote_temp, common.unique_name("in_memory/sort"),
                                          [["NEAR_DIST", "DESCENDING"]])[0]
        common.delete(remote_temp)
        arcpy.DeleteField_management(sort_temp, ("NEAR_DIST", "NEAR_FID"))

        # For each remote asset, find the surrounding nearest fixed assets. This Near Table will be used
        # during backhaul to only load particular assets into the Facilities sublayer. Because this table is sorted
        # where the nearest features are first (NEAR_DIST and NEAR_RANK are ascending), an arbitrarily defined number of
        # fixed assets can be loaded into the Closest Facility via list slicing.

        # In practice, set closest_count to a reasonable number (such as 100). If closest_count=None, then the resultant
        # Near Table will have (nrows in remote * nrows in fixed) rows. This quickly gets very large (17m+ during dev).
        count = arcpy.GetCount_management(sort_temp)
        arcpy.AddMessage("\t{} Processing {} features...".format(common.timestamp(), count))
        method = "GEODESIC" if arcpy.Describe(sort_temp).spatialReference.type == "Geographic" else "PLANAR"
        near_temp = arcpy.GenerateNearTable_analysis(sort_temp, fixed_temp, common.unique_name("in_memory/near"),
                                                     closest="ALL", closest_count=NEAR_TABLE_SIZE, method=method)[0]
        arcpy.AddMessage("\t{} Saving Near Table...".format(common.timestamp()))
        arcpy.DeleteField_management(near_temp, ["NEAR_DIST", "NEAR_RANK"])
        near_out = arcpy.CopyRows_management(near_temp, os.path.join(self.gdb, NEAR_TABLE))[0]
        common.delete(near_temp)

        arcpy.ResetProgressor()
        self.calc_update(sort_temp, "Remote")
        self.calc_update(fixed_temp, "Fixed")
        remote_out = arcpy.CopyFeatures_management(sort_temp, os.path.join(self.gdb, REMOTE))[0]
        fixed_out = arcpy.CopyFeatures_management(fixed_temp, os.path.join(self.gdb, FIXED))[0]
        common.delete([sort_temp, fixed_temp])

        return remote_out, fixed_out, near_out


def main(remote_assets, fixed_assets, network_dataset, folder):
    locate = LocateAssets(remote_assets, fixed_assets, network_dataset, folder)
    return locate.execute()
