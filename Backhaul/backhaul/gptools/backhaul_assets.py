import os
import time
import numpy as np
import arcpy
from .. import common
from ..setttings import *


def extend_line(line, start, end):
    """
    Extends a line at start/end to new points
    line - arcpy.Polyline() object
    start - arcpy.Point() object - the start of the line will be extended to this
    end - arcpy.Point() object - the end of the line will be extended to this

    returns a new arcpy.Polyline() object
    """

    points = line.getPart(0)

    # Only extend if not already "snapped".
    if not line.firstPoint.equals(start):
        points.insert(0, start)
    if not line.lastPoint.equals(end):
        points.append(end)

    return arcpy.Polyline(points, line.spatialReference)


class Backhaul(object):
    def __init__(self, remote_assets, fixed_assets, near_table, closest_facility, folder, search_threshold=MAX_SEARCH,
                 daisy_threshold=MAX_DAISY, extend_route=False):

        self.remote = remote_assets
        self.fixed = fixed_assets
        self.near = near_table
        self.CF = common.wrappers.ClosestFacilityHelper(closest_facility)
        self.search = search_threshold
        self.daisy = daisy_threshold
        self.extend = extend_route
        self.gdb = arcpy.CreateUniqueName(FINAL_GDB, folder)
        self.field_map = arcpy.na.NAClassFieldMappings(network_analyst_layer=self.CF.na_layer,
                                                       sub_layer_name=self.CF.facilities.name,
                                                       use_location_fields=True,
                                                       list_candidate_fields=arcpy.ListFields(self.remote))
        self.result = None
        self.route_fields = None
        self.near_array = None
        self.point_dict = None
        self.fixed_assets = []

    def add_locations(self, sublayer, features, append):
        """helper function for arcpy.na.AddLocations"""
        return arcpy.na.AddLocations(in_network_analysis_layer=self.CF.na_layer,
                                     sub_layer=sublayer,
                                     in_table=features,
                                     field_mappings=self.field_map,
                                     search_tolerance=self.CF.describe.searchTolerance,
                                     sort_field=None,
                                     search_criteria=None,
                                     match_type="MATCH_TO_CLOSEST",
                                     append=append,
                                     snap_to_position_along_network="NO_SNAP",
                                     snap_offset=None,
                                     exclude_restricted_elements="EXCLUDE",
                                     search_query=None)

    def create_relationship(self, destination, PK, label):
        """helper function for arcpy.management.CreateRelationshipClass"""
        class_name = os.path.join(self.gdb, "Routes_{}_{}".format(*label.split(" ")))
        return arcpy.CreateRelationshipClass_management(origin_table=os.path.join(self.gdb, ROUTES),
                                                        destination_table=destination,
                                                        out_relationship_class=class_name,
                                                        relationship_type="SIMPLE",
                                                        forward_label="Routes",
                                                        backward_label=label,
                                                        message_direction="NONE",
                                                        cardinality="ONE_TO_ONE",
                                                        attributed="NONE",
                                                        origin_primary_key=PK,
                                                        origin_foreign_key="Name",
                                                        destination_primary_key=None,
                                                        destination_foreign_key=None)

    def pre_process(self):

        # Create feature class from CF\Routes and add extra fields to store relationship information
        route_desc = arcpy.Describe(self.CF.routes)
        self.result = arcpy.CreateFeatureclass_management('in_memory', common.unique_name('output'), "POLYLINE",
                                                          template=self.CF.routes,
                                                          has_m="DISABLED", has_z="DISABLED",
                                                          spatial_reference=route_desc.spatialReference)[0]

        arcpy.AddField_management(self.result, "startID", "LONG")
        arcpy.AddField_management(self.result, "endID", "LONG")
        arcpy.AddField_management(self.result, "startAsset", "SHORT")
        arcpy.AddField_management(self.result, "endAsset", "SHORT")
        arcpy.AddField_management(self.result, "startName", "TEXT")
        arcpy.AddField_management(self.result, "endName", "TEXT")

        # A numpy array of remote asset OIDs, starting with those furthest removed from the fixed assets.
        # During the previous script to Add NA Locations, this layer was sorted.
        # This array is used to:
        #   store remote asset IDs (ID)
        #   flag already routed remote assets (visited)
        #   increment daisy counter on remote assets (daisy)
        #   list fixed assets from near table (fixed)
        def array_generator():
            remote_id = [row[0] for row in arcpy.da.SearchCursor(self.remote, "OID@")]
            table = arcpy.da.TableToNumPyArray(self.near, ["IN_FID", "NEAR_FID"])
            for rID in remote_id:
                yield rID, False, 0, table[table["IN_FID"] == rID]["NEAR_FID"][:self.search]

        arcpy.AddMessage("\t{} Converting near table to numpy array".format(common.timestamp()))
        self.near_array = np.array(list(array_generator()), dtype=[("ID", np.int32),
                                                                   ("visited", np.bool_),
                                                                   ("daisy", np.int32),
                                                                   ("fixed", np.ndarray)])

        # This dictionary stores the geometry of all assets. It will be used to
        # access the point location when extending the final route.
        if self.extend:
            sr = arcpy.Describe(self.CF.routes).spatialReference
            self.point_dict = dict()
            self.point_dict["Remote"] = {a: b.firstPoint for a, b in arcpy.da.SearchCursor(self.remote,
                                                                                           ["OID@", "SHAPE@"],
                                                                                           spatial_reference=sr)}
            self.point_dict["Fixed"] = {a: b.firstPoint for a, b in arcpy.da.SearchCursor(self.fixed,
                                                                                          ["OID@", "SHAPE@"],
                                                                                          spatial_reference=sr)}

    def transform_route(self):
        """
        Copy the route created from arcpy.na.Solve to the output layer, capturing information and changing the shape
        """
        name_id = self.route_fields.index("Name")
        shape_id = self.route_fields.index("SHAPE@")

        with arcpy.da.SearchCursor(self.CF.routes, self.route_fields) as sCursor:
            for row in sCursor:
                row = list(row)

                # Get the Incident and Facility IDs of the final route.
                # These value are stored in the Name field and follow the form
                # {'Remote'/'Fixed'} {Incident ID} - {'Remote'/'Fixed'} {Facility ID}"
                incident, facility = row[name_id].split(" - ")
                start_flag, start = incident.split(" ")
                end_flag, end = facility.split(" ")
                start = int(start)
                end = int(end)
                # Only remote assets will have their daisy counter incremented
                # keep running list of all fixed assets that have been routed to
                if start_flag == "Remote":
                    start_id = 1
                    self.near_array[np.where(self.near_array["ID"] == start)[0][0]]["daisy"] += 1
                else:
                    start_id = 0
                    self.fixed_assets.append(start)
                if end_flag == "Remote":
                    end_id = 1
                    self.near_array[np.where(self.near_array["ID"] == end)[0][0]]["daisy"] += 1
                else:
                    end_id = 0
                    self.fixed_assets.append(end)

                # If the mode is TRAVEL_TO, that means start is always the remote asset
                # Give a more descriptive name
                new_name = start if self.CF.describe.solverProperties.travelDirection == "TRAVEL_TO" else end
                row[name_id] = "Route {}".format(new_name)

                # Sometimes the solver returns a null geometry
                if self.extend and row[shape_id] is not None:
                    row[shape_id] = extend_line(line=row[shape_id],
                                                start=self.point_dict[start_flag][start],
                                                end=self.point_dict[end_flag][end])

                yield row + [start, end, start_id, end_id, incident, facility]

    def post_process(self):
        remote = fixed = None
        arcpy.SetProgressorLabel("Saving data...")
        arcpy.AddMessage("\t{} Writing results to disk".format(common.timestamp()))
        self.gdb = arcpy.CreateFileGDB_management(*os.path.split(self.gdb))[0]
        routes = arcpy.CopyFeatures_management(self.result, os.path.join(self.gdb, ROUTES))[0]

        if COPY_ASSETS:
            dom_name = "isRemote"
            arcpy.CreateDomain_management(self.gdb, dom_name, "Remote or Fixed Asset", "SHORT", "CODED")
            arcpy.AddCodedValueToDomain_management(self.gdb, dom_name, "0", "FIXED")
            arcpy.AddCodedValueToDomain_management(self.gdb, dom_name, "1", "REMOTE")
            arcpy.AssignDomainToField_management(routes, "startAsset", dom_name)
            arcpy.AssignDomainToField_management(routes, "endAsset", dom_name)

            remote = arcpy.CopyFeatures_management(self.remote, os.path.join(self.gdb, REMOTE))[0]

            if self.fixed_assets:
                query = common.create_sql(self.fixed, "OID@", self.fixed_assets)
                fixed = arcpy.FeatureClassToFeatureClass_conversion(in_features=self.fixed,
                                                                    out_path=self.gdb,
                                                                    out_name=FIXED,
                                                                    where_clause=query)[0]
            else:
                sr = arcpy.Describe(self.fixed).spatialReference
                fixed = arcpy.CreateFeatureclass_management(self.gdb, FIXED, "POINT", template=self.fixed,
                                                            has_m="SAME_AS_TEMPLATE", has_z="SAME_AS_TEMPLATE",
                                                            spatial_reference=sr)[0]

            if CREATE_RELATIONSHIPS:
                arcpy.SetProgressorLabel("Creating relationship classes...")
                self.create_relationship(destination=fixed, PK="startName", label="Fixed Start")
                self.create_relationship(destination=fixed, PK="endName", label="Fixed End")
                self.create_relationship(destination=remote, PK="startName", label="Remote Start")
                self.create_relationship(destination=remote, PK="endName", label="Remote End")

        return routes, remote, fixed

    def execute(self):

        self.pre_process()

        incidents_layer = arcpy.MakeFeatureLayer_management(self.remote, common.unique_name("incidents"))[0]
        remote_layer = arcpy.MakeFeatureLayer_management(self.remote, common.unique_name("remote"))[0]
        fixed_layer = arcpy.MakeFeatureLayer_management(self.fixed, common.unique_name("fixed"))[0]

        # Get a list of all fields in the CF\Routes and results, ensuring that shape is first
        self.route_fields = ["SHAPE@"] + [f.name for f in arcpy.Describe(self.CF.routes).fields if
                                          f.type.upper() not in ("OID", "GEOMETRY")]
        result_fields = ["SHAPE@"] + [f.name for f in arcpy.Describe(self.result).fields if
                                      f.type.upper() not in ("OID", "GEOMETRY")]

        arcpy.AddMessage("\t{} Beginning backhaul process".format(common.timestamp()))
        with arcpy.da.InsertCursor(self.result, result_fields) as iCursor:
            arcpy.SetProgressor("step", "Solving routes...", 0, self.near_array.size)

            for i, record in enumerate(self.near_array, 1):

                # Select the current asset and mark it visited.
                incidents_layer.definitionQuery = common.create_sql(incidents_layer, "OID@", record["ID"])
                record["visited"] = True
                self.add_locations(sublayer=self.CF.incidents.name, features=incidents_layer, append="CLEAR")

                # If the current remote asset is above the daisy threshold, only route to fixed assets
                if record["daisy"] >= self.daisy:
                    remote_siblings = np.array([])
                else:
                    # Only add those remote assets that:
                    #   have NOT been routed from (i.e., have not been the current asset) -OR-
                    #   are under the daisy threshold
                    remote_siblings = self.near_array[~self.near_array["visited"] &
                                                      (self.near_array["daisy"] < self.daisy)]["ID"][:self.search]
                if remote_siblings.size:
                    # If there are remote siblings to add, then the fixed siblings will be appended
                    append = "APPEND"
                    remote_layer.definitionQuery = common.create_sql(remote_layer, "OID@", remote_siblings.tolist())
                    self.add_locations(sublayer=self.CF.facilities.name, features=remote_layer, append="CLEAR")
                else:
                    append = "CLEAR"

                fixed_layer.definitionQuery = common.create_sql(fixed_layer, "OID@", record["fixed"].tolist())
                self.add_locations(sublayer=self.CF.facilities.name, features=fixed_layer, append=append)

                solve = arcpy.na.Solve(self.CF.na_layer, "SKIP", "CONTINUE")

                # The solve result tuple is (closest facility layer, solve succeeded)
                if solve.getOutput(1) == 'true':
                    for row in self.transform_route():
                        iCursor.insertRow(row)
                else:
                    arcpy.AddMessage("\tNo route found for {}".format(record["ID"]))
                    arcpy.AddWarning(solve.getMessages())

                arcpy.SetProgressorPosition(i)

        for tempData in [incidents_layer, remote_layer, fixed_layer]:
            common.delete(tempData)

        arcpy.ResetProgressor()
        return self.post_process()


def main(remote_assets, fixed_assets, near_table, closest_facility, folder, search_threshold=MAX_SEARCH,
         daisy_threshold=MAX_DAISY, extend_route=False):
    backhauler = Backhaul(remote_assets, fixed_assets, near_table, closest_facility,
                          folder, search_threshold, daisy_threshold, extend_route)
    return backhauler.execute()
