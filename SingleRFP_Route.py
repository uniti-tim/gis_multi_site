import arcpy
import os

#Parameters
inputRFPSites = arcpy.GetParameterAsText(0)
inputNetwork = arcpy.GetParameterAsText(1)
outputLocation = arcpy.GetParameterAsText(2)

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

mxd = arcpy.mapping.MapDocument("CURRENT")
dataFrame = arcpy.mapping.ListDataFrames(mxd,"*")[0]

##--- Select hub site ---##
arcpy.MakeFeatureLayer_management(inputRFPSites,'hubSite')
arcpy.SelectLayerByAttribute_management('hubSite','NEW_SELECTION','"Hub" = 1')

hubNum = arcpy.GetCount_management('hubSite')
arcpy.AddMessage('**********************************')
arcpy.AddMessage('Found ' + str(hubNum) + ' Hub Site')

##--- Locate Assets to hub site against the network ---##
arcpy.ImportToolbox(scriptLocation + os.sep + 'Backhaul' + os.sep + 'Backhaul.pyt')
arcpy.AddMessage('Beginning Locate Assets...')

arcpy.LocateAssets_backhaul(inputRFPSites,'hubSite',inputNetwork,outputLocation)
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
arcpy.Intersect_analysis(backRoutes,'routes_intersected.shp')
arcpy.AddMessage('- Routes intersected.')

arcpy.Erase_analysis(backRoutes,'routes_intersected.shp','routes_erased.shp')
arcpy.AddMessage('- Overlapping routes erased.')

arcpy.Merge_management(['routes_intersected.shp','routes_erased.shp'],'routes_cleaned.shp')
arcpy.AddMessage('- Completed cleaning routes.')

##--- Add data to map ---##
cleanRoutes = arcpy.mapping.Layer('routes_cleaned.shp')
arcpy.mapping.AddLayer(dataFrame,cleanRoutes,'TOP')

arcpy.AddMessage('**********************************')
