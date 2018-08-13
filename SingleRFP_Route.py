import arcpy
import os

##--- Function to grab the unique group names from the input sites field ---##
def unique_values(table , field):
    with arcpy.da.SearchCursor(table, [field]) as cursor:
        return sorted({row[0] for row in cursor})

#Parameters
inputRFPSites = arcpy.GetParameterAsText(0)
inputNameField = arcpy.GetParameterAsText(1)
userFacilities = arcpy.GetParameterAsText(2) #optional
inputNetwork = arcpy.GetParameterAsText(3)
outputLocation = arcpy.GetParameterAsText(4)

#Variables
arcpy.env.workspace = outputLocation
scriptLocation = os.path.split(os.path.realpath(__file__))[0]
tempLocateOuput = 'BackhaulAssets.gdb'
tempBackhaulOutput = 'BackhaulResults.gdb'

locFixedAssets = tempLocateOuput + os.sep + 'FixedAssets'
locRemoteAssets = tempLocateOuput + os.sep + 'RemoteAssets'
locNearTable = tempLocateOuput + os.sep + 'NearTable'

backFixedAssets = tempBackhaulOutput + os.sep + 'FixedAssets'
backRemoteAssets = tempBackhaulOutput + os.sep + 'RemoteAssets'
backRoutes = tempBackhaulOutput + os.sep + 'Routes'

rfpParentList = unique_values(inputRFPSites,inputNameField)

mxd = arcpy.mapping.MapDocument("CURRENT")
dataFrame = arcpy.mapping.ListDataFrames(mxd,"*")[0]

arcpy.AddMessage('**********************************')

if userFacilities:
    ##-- User has provided a facilities layer to route to rather than a hub --##
    arcpy.AddMessage('User Facility layer has been provided...')
    arcpy.MakeFeatureLayer_management(userFacilities,'hubSites')

    hubNum = arcpy.GetCount_management('hubSites')    
    arcpy.AddMessage('Found ' + str(hubNum) + ' user facilities.')
else:
    ##--- Select hub site ---##
    arcpy.MakeFeatureLayer_management(inputRFPSites,'hubSites')
    arcpy.SelectLayerByAttribute_management('hubSites','NEW_SELECTION','"Hub" = 1')

    hubNum = arcpy.GetCount_management('hubSites')    
    arcpy.AddMessage('Found ' + str(hubNum) + ' Hub Site')

##--- Locate Assets to hub site against the network ---##
arcpy.ImportToolbox(scriptLocation + os.sep + 'Backhaul' + os.sep + 'Backhaul.pyt')
arcpy.AddMessage('Beginning Locate Assets...')

arcpy.LocateAssets_backhaul(inputRFPSites,'hubSites',inputNetwork,outputLocation)
arcpy.AddMessage('- Locate Assets completed successfully')

##--- Backhaul Optimization ---##
arcpy.AddMessage('Creating Closest Facility layer...')
backClosestFacility = arcpy.na.MakeClosestFacilityLayer(inputNetwork,"ClosestFacility","LENGTH",
                                                   "","","","","",
                                                   "","","",
                                                   "TRUE_LINES_WITH_MEASURES","","")
arcpy.AddMessage('- Closest Facility layer created successfully')

#Importing the toolbox again because it seems to forget that it was already imported
arcpy.ImportToolbox(scriptLocation + os.sep + 'Backhaul' + os.sep + 'Backhaul.pyt')

arcpy.AddMessage('Beginning Backhaul Optimization...')
arcpy.BackhaulAssets_backhaul(locRemoteAssets,locFixedAssets,locNearTable,backClosestFacility,outputLocation,"50","10","TRUE")
arcpy.AddMessage('- Backhaul Optimization completed successfully')

##--- Cleanup the output ---##
arcpy.AddMessage('Cleaning up the output...')
arcpy.Intersect_analysis(backRoutes,'routes_intersected.shp','ALL','','INPUT')
arcpy.AddMessage('- Routes intersected.')

arcpy.Erase_analysis(backRoutes,'routes_intersected.shp','routes_erased.shp','')
arcpy.AddMessage('- Overlapping routes erased.')

arcpy.Merge_management(['routes_intersected.shp','routes_erased.shp'],'routes_cleaned.shp')
arcpy.AddMessage('- Completed cleaning routes.')

arcpy.DeleteIdentical_management('routes_cleaned.shp','Shape','','')
arcpy.AddMessage('- Duplicate features removed.')

##--- Add data to map ---##
cleanRoutes = arcpy.mapping.Layer('routes_cleaned.shp')
arcpy.mapping.AddLayer(dataFrame,cleanRoutes,'TOP')

arcpy.AddMessage('**********************************')
