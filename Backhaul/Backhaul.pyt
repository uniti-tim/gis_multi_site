import os
import arcpy
import backhaul
from backhaul import common
from backhaul.setttings import *
from backhaul.gptools.backhaul_assets import main as create_backhaul_routes
from backhaul.gptools.create import main as generate_points_along_lines
from backhaul.gptools.locate import main as generate_NA_locations

backhaul.dev.rreload(backhaul)


class Toolbox(object):
    def __init__(self):
        self.label = u'Backhaul'
        self.alias = 'backhaul'
        self.tools = [LocateAssets, BackhaulAssets]

symbology = os.path.join(os.path.dirname(__file__), "Symbology")


class LocateAssets(object):
    def __init__(self):
        self.label = u'1. Locate Assets'
        self.description = u'Creates copies of the remote and fixed assets and adds fields that contain the ' \
                           u'network location of the features. Optionally, a polyline feature class can be converted ' \
                           u'to points to use as fixed assets.'
        self.canRunInBackground = True

    def getParameterInfo(self):

        remote = arcpy.Parameter(name='remote_assets',
                                 displayName='Remote Assets',
                                 direction='input', datatype='GPFeatureLayer',
                                 parameterType='Required', enabled=True,
                                 category=None, symbology=None, multiValue=False)

        fixed = arcpy.Parameter(name='fixed_assets',
                                displayName='Fixed Assets',
                                direction='input', datatype='GPFeatureLayer',
                                parameterType='Optional', enabled=True,
                                category=None, symbology=None, multiValue=False)

        network = arcpy.Parameter(name='in_network_dataset',
                                  displayName='Input Analysis Network',
                                  direction='input', datatype='GPNetworkDatasetLayer',
                                  parameterType='Required', enabled=True,
                                  category=None, symbology=None, multiValue=False)

        folder = arcpy.Parameter(name='output_folder',
                                 displayName='Output Folder',
                                 direction='Input', datatype='DEWorkspace',
                                 parameterType='Required', enabled=True,
                                 category=None, symbology=None, multiValue=False)

        create = arcpy.Parameter(name='create',
                                 displayName='Create Fixed Assets',
                                 direction='input', datatype='GPBoolean',
                                 parameterType='Optional', enabled=True,
                                 category=None, symbology=None, multiValue=False)

        backbone = arcpy.Parameter(name='backbone',
                                   displayName='Backbone',
                                   direction='input', datatype='GPFeatureLayer',
                                   parameterType='Optional', enabled=True,
                                   category=None, symbology=None, multiValue=False)

        dist = arcpy.Parameter(name='distance_between_points',
                               displayName='Distance Between Points',
                               direction='input', datatype='GPLinearunit',
                               parameterType='Optional', enabled=True,
                               category=None, symbology=None, multiValue=False)

        output_fixed = arcpy.Parameter(name='fixed_result',
                                       displayName='Result Fixed Assets',
                                       direction='Output', datatype='GPFeatureLayer',
                                       parameterType='Derived', enabled=True,
                                       category=None, symbology=os.path.join(symbology, "FixedAssets.lyr"),
                                       multiValue=False)

        output_remote = arcpy.Parameter(name='remote_result',
                                        displayName='Result Remote Assets',
                                        direction='Output', datatype='GPFeatureLayer',
                                        parameterType='Derived', enabled=True,
                                        category=None, symbology=os.path.join(symbology, "RemoteAssets.lyr"),
                                        multiValue=False)

        output_near = arcpy.Parameter(name='near_result',
                                      displayName='Result Near Table',
                                      direction='Output', datatype='DETable',
                                      parameterType='Derived', enabled=True,
                                      category=None, symbology=None, multiValue=False)

        remote.filter.list = fixed.filter.list = ["POINT"]
        backbone.filter.list = ["POLYLINE"]
        folder.filter.list = ["File System"]
        create.value = False
        backbone.enabled = dist.enabled = False

        return [remote, fixed, network, folder, create, backbone, dist, output_fixed, output_remote, output_near]

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        remote, fixed, network, folder, create, backbone, dist = parameters[:-3]
        if create.value:
            backbone.enabled = dist.enabled = True
            fixed.enabled = False
        else:
            backbone.enabled = dist.enabled = False
            fixed.enabled = True

    def updateMessages(self, parameters):
        remote, fixed, network, folder, create, backbone, dist = parameters[:-3]
        if create.value:
            if not backbone.value:
                backbone.setIDMessage("ERROR", 735, backbone.displayName)
            if not dist.value:
                dist.setIDMessage("ERROR", 735, dist.displayName)
        else:
            if not fixed.value:
                fixed.setIDMessage("ERROR", 735, fixed.displayName)

    def execute(self, parameters, messages):
        remote, fixed, network, folder, create, backbone, dist = [p.valueAsText for p in parameters[:-3]]

        if create.upper() == "TRUE":
            fixed = generate_points_along_lines(Input_Features=backbone,
                                                Output_Feature_Class=common.unique_name('in_memory/points'),
                                                Distance=dist,
                                                Include_End_Points=True)

        res = generate_NA_locations(remote_assets=remote,
                                    fixed_assets=fixed,
                                    network_dataset=network,
                                    folder=folder)

        arcpy.SetParameterAsText(7, res[0])
        arcpy.SetParameterAsText(8, res[1])
        arcpy.SetParameterAsText(9, res[2])


class BackhaulAssets(object):
    def __init__(self):
        self.label = u'2. Backhaul Assets'
        self.description = u'Iteratively adds the assets to the closest facility layer and solves the route. ' \
                           u'Once a remote asset has been routed, it is not included in further solve operations.'
        self.canRunInBackground = True

    def getParameterInfo(self):
        remote = arcpy.Parameter(name='remote_assets',
                                 displayName='Remote Assets',
                                 direction='input', datatype='GPFeatureLayer',
                                 parameterType='Required', enabled=True,
                                 category=None, symbology=None, multiValue=False)

        fixed = arcpy.Parameter(name='fixed_assets',
                                displayName='Fixed Assets',
                                direction='input', datatype='GPFeatureLayer',
                                parameterType='Required', enabled=True,
                                category=None, symbology=None, multiValue=False)

        near = arcpy.Parameter(name='near_table',
                               displayName='Near Table',
                               direction='input', datatype='GPTableView',
                               parameterType='Required', enabled=True,
                               category=None, symbology=None, multiValue=False)

        closest = arcpy.Parameter(name='closest_facility',
                                  displayName='Closest Facility',
                                  direction='input', datatype='GPNALayer',
                                  parameterType='Required', enabled=True,
                                  category=None, symbology=None, multiValue=False)

        search = arcpy.Parameter(name='max_assets',
                                 displayName='Maximum Number of Assets to Search',
                                 direction='input', datatype='GPLong',
                                 parameterType='Optional', enabled=True,
                                 category="Route Modifiers", symbology=None, multiValue=False)

        daisy = arcpy.Parameter(name='daisy_chain',
                                displayName='Maximum Remote Assets to Daisy Chain',
                                direction='input', datatype='GPLong',
                                parameterType='Optional', enabled=True,
                                category="Route Modifiers", symbology=None, multiValue=False)

        extend = arcpy.Parameter(name='extend',
                                 displayName='Extend Route to Assets',
                                 direction='input', datatype='GPBoolean',
                                 parameterType='Optional', enabled=True,
                                 category="Route Modifiers", symbology=None, multiValue=False)

        folder = arcpy.Parameter(name='folder',
                                 displayName='Output Folder',
                                 direction='Input', datatype='DEWorkspace',
                                 parameterType='Required', enabled=True,
                                 category=None, symbology=None, multiValue=False)

        output_routes = arcpy.Parameter(name='routes_result',
                                        displayName='Routes',
                                        direction='Output', datatype='GPFeatureLayer',
                                        parameterType='Derived', enabled=True,
                                        category=None, symbology=os.path.join(symbology, "Routes.lyr"),
                                        multiValue=False)

        output_remote = arcpy.Parameter(name='remote_result',
                                        displayName='Remote',
                                        direction='Output', datatype='GPFeatureLayer',
                                        parameterType='Derived', enabled=True,
                                        category=None, symbology=os.path.join(symbology, "RemoteAssets.lyr"),
                                        multiValue=False)

        output_fixed = arcpy.Parameter(name='fixed_result',
                                       displayName='Fixed',
                                       direction='Output', datatype='GPFeatureLayer',
                                       parameterType='Derived', enabled=True,
                                       category=None, symbology=os.path.join(symbology, "FixedAssets.lyr"),
                                       multiValue=False)

        search.filter.type = "RANGE"
        search.filter.list = [1, MAX_SEARCH]
        search.value = MAX_SEARCH
        daisy.filter.type = "RANGE"
        daisy.filter.list = [0, MAX_DAISY]
        daisy.value = MAX_DAISY
        extend.value = False
        remote.filter.list = fixed.filter.list = ["POINT"]
        folder.filter.list = ["File System"]

        return [remote, fixed, near, closest, folder, search, daisy, extend, output_routes, output_fixed, output_remote]

    def isLicensed(self):
        try:
            if arcpy.CheckExtension("Network") != "Available":
                raise Exception
        except Exception:
            return False  # tool cannot be executed

        return True  # tool can be executed

    def updateParameters(self, parameters):
        return

    def updateMessages(self, parameters):
        return

    def execute(self, parameters, messages):
        remote, fixed, near, closest, folder, search, daisy, extend = [p.valueAsText for p in parameters[:-3]]

        results = create_backhaul_routes(remote_assets=remote,
                                         fixed_assets=fixed,
                                         near_table=near,
                                         closest_facility=closest,
                                         folder=folder,
                                         search_threshold=int(search),
                                         daisy_threshold=int(daisy),
                                         extend_route=True if extend.upper() == "TRUE" else False)

        arcpy.SetParameterAsText(8, results[0])
        if results[1]:
            arcpy.SetParameterAsText(9, results[1])
        if results[2]:
            arcpy.SetParameterAsText(10, results[2])
