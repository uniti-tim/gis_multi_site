import arcpy
import os
import csv
import shutil
import glob

#Parameters
inputRFPSites = arcpy.GetParameterAsText(0)
inputNameField = arcpy.GetParameterAsText(1)
siteNameField = arcpy.GetParameterAsText(2)
userFacilities = arcpy.GetParameterAsText(3) #optional
inputNetwork = arcpy.GetParameterAsText(4)
outputLocation = arcpy.GetParameterAsText(5)
displayAdd = arcpy.GetParameterAsText(6)

#Settings
arcpy.env.overwriteOutput = True

#Variables
scriptLocation = os.path.split(os.path.realpath(__file__))[0]
tempLocateOuput = outputLocation + os.sep + 'BackhaulAssets.gdb'
tempBackhaulOutput = outputLocation + os.sep + 'BackhaulResults.gdb'
tempMXD = scriptLocation + os.sep + "routeMap.mxd"

locFixedAssets = tempLocateOuput + os.sep + 'FixedAssets'
locRemoteAssets = tempLocateOuput + os.sep + 'RemoteAssets'
locNearTable = tempLocateOuput + os.sep + 'NearTable'

backFixedAssets = tempBackhaulOutput + os.sep + 'FixedAssets'
backRemoteAssets = tempBackhaulOutput + os.sep + 'RemoteAssets'
backRoutes = tempBackhaulOutput + os.sep + 'Routes'

arcpy.env.workspace = os.path.split(inputNetwork)[0]
fiberCable = os.path.split(inputNetwork)[0] + os.sep + arcpy.ListFeatureClasses("FIBERCABLE*")[0]
arcpy.MakeFeatureLayer_management(fiberCable,'fiber')

##--- Function to grab the unique group names from the input sites field ---##
def unique_values(table , field):
    with arcpy.da.SearchCursor(table, [field]) as cursor:
        return sorted({row[0] for row in cursor})

##--- Function for deleting/cleaning up the temporary data that was created ---##
def cleanup():
    rfpGroup = arcpy.SelectLayerByAttribute_management("rfpSites","CLEAR_SELECTION")

    arcpy.Delete_management('routes_erased')
    arcpy.Delete_management('routes_intersected')
    arcpy.Delete_management('routes_cleaned')
    arcpy.Delete_management('routes_identity')

    arcpy.env.workspace = outputLocation

    arcpy.Delete_management(tempLocateOuput)
    arcpy.Delete_management(tempBackhaulOutput)

    os.remove(outputLocation + os.sep + siteName + ".mxd")

##--- Function to output an attribute table as a CSV file ---##
def tableToCSV(input_tbl, csv_filepath):
    fld_names = ['FID_Routes', 'Status','Site_Name','Type','Length_mi','Route_Name','FolderPath']
    with open(csv_filepath, 'wb') as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(fld_names)
        with arcpy.da.SearchCursor(input_tbl, fld_names) as cursor:
            for row in cursor:
                writer.writerow(row)
        arcpy.AddMessage('- CSV generated for route.')
    csv_file.close()

##--- Function for making an MXD and converting to KML ---##
def makeKML():
    arcpy.AddMessage('Converting to KML...')
    shutil.copy(tempMXD,outputLocation + os.sep + siteName + ".mxd")
    
    resultMXD = arcpy.mapping.MapDocument(outputLocation + os.sep + siteName + ".mxd")
    arcpy.AddMessage('- Template MXD created.')

    layers = arcpy.mapping.ListLayers(resultMXD)
    layers[0].replaceDataSource(outputLocation + os.sep + siteName + ".gdb","FILEGDB_WORKSPACE","parent_sites_"+siteName)
    layers[1].replaceDataSource(outputLocation + os.sep + siteName + ".gdb","FILEGDB_WORKSPACE","hubs_"+siteName)
    layers[2].replaceDataSource(outputLocation + os.sep + siteName + ".gdb","FILEGDB_WORKSPACE","routes_"+siteName)
    resultMXD.save()
    arcpy.AddMessage('- Data Sources reconnected.')

    layers = ""
    resultMXD = ""

    arcpy.MapToKML_conversion(outputLocation + os.sep + siteName + ".mxd", "Layers" ,outputLocation + os.sep + siteName + ".kmz")
    arcpy.AddMessage('- KMZ file created.')

##--- If the Add to Display checkbox is checked, this is where it's added to ArcMap---##
def addResults():
    if displayAdd == "true":
        mxd = arcpy.mapping.MapDocument("CURRENT")
        dataFrame = arcpy.mapping.ListDataFrames(mxd,"*")[0]

        arcpy.AddMessage('Adding Data to ArcMap...')
        sites = arcpy.mapping.Layer('parent_sites_'+siteName)
        hubs = arcpy.mapping.Layer('hubs_'+siteName)
        routes = arcpy.mapping.Layer('routes_'+siteName)            
        
        arcpy.mapping.AddLayer(dataFrame,routes,'TOP')
        arcpy.mapping.AddLayer(dataFrame,hubs,'TOP')
        arcpy.mapping.AddLayer(dataFrame,sites,'TOP')

        dataFrame.zoomToSelectedFeatures()

##--- Function to read through each CSV file and summarize the lengths by route type ---##
def summaryCSV(siteName,routes,siteNum):
    ## Existing Routes
    arcpy.SelectLayerByAttribute_management(routes,'NEW_SELECTION','"Status" = \'E\'')
    length = 0
    with arcpy.da.SearchCursor(routes,'Length_mi') as cursor:
	for row in cursor:
		length = length + row[0]
		
    with open(outputLocation + os.sep + '_SUMMARY_.csv', 'ab') as summaryFile:
        writer = csv.writer(summaryFile)
        writer.writerow([siteName,'E',length,siteNum])
    summaryFile.close()

    ## New Routes
    arcpy.SelectLayerByAttribute_management(routes,'NEW_SELECTION','"Status" = \'N\'')
    length = 0
    with arcpy.da.SearchCursor(routes,'Length_mi') as cursor:
	for row in cursor:
		length = length + row[0]
		
    with open(outputLocation + os.sep + '_SUMMARY_.csv', 'ab') as summaryFile:
        writer = csv.writer(summaryFile)
        writer.writerow([siteName,'N',length,siteNum])
    summaryFile.close()

##--- Function to perform the routing work ---##
def rfpRoute(inputRFPSites):    
    if userFacilities:
        ##-- User has provided a facilities layer to route to rather than a hub --##
        arcpy.AddMessage('User Facility layer has been provided...')
        arcpy.MakeFeatureLayer_management(userFacilities,'hubSites')

        hubNum = int(arcpy.GetCount_management('hubSites').getOutput(0))    
        arcpy.AddMessage('Found ' + str(hubNum) + ' user facilities.')
    else:
        ##--- Select hub site ---##
        arcpy.MakeFeatureLayer_management(inputRFPSites,'hubSites')
        arcpy.SelectLayerByAttribute_management('hubSites','NEW_SELECTION','"Hub" = 1')

        hubNum = int(arcpy.GetCount_management('hubSites').getOutput(0))
        arcpy.AddMessage('Found ' + str(hubNum) + ' Hub Site')

        if hubNum < 1:
            return "noHub"

    ##--- Locate Assets to hub site against the network ---##
    arcpy.ImportToolbox(scriptLocation + os.sep + 'Backhaul' + os.sep + 'Backhaul.pyt')
    arcpy.AddMessage('Beginning Locate Assets...')

    arcpy.LocateAssets_backhaul(inputRFPSites,'hubSites',inputNetwork,outputLocation)
    arcpy.AddMessage('- Locate Assets completed successfully')

    ##--- Backhaul Optimization ---##
    arcpy.AddMessage('Creating Closest Facility layer...')
    backClosestFacility = arcpy.na.MakeClosestFacilityLayer(inputNetwork,"ClosestFacility","LENGTH","TRAVEL_TO","","","","ALLOW_UTURNS","","NO_HIERARCHY","","TRUE_LINES_WITH_MEASURES","","")
    arcpy.AddMessage('- Closest Facility layer created successfully')

    arcpy.ImportToolbox(scriptLocation + os.sep + 'Backhaul' + os.sep + 'Backhaul.pyt')
    arcpy.AddMessage('Beginning Backhaul Optimization...')
    arcpy.BackhaulAssets_backhaul(locRemoteAssets, locFixedAssets, locNearTable, backClosestFacility, outputLocation,"50","10","TRUE")
    arcpy.AddMessage('- Backhaul Optimization completed successfully')

    ##--- Cleanup the routes ---##
    arcpy.AddMessage('Cleaning up the routes...')
    arcpy.Intersect_analysis(backRoutes,'routes_intersected','ALL','','INPUT')
    arcpy.AddMessage('- Routes intersected.')

    arcpy.Erase_analysis(backRoutes,'routes_intersected','routes_erased','')
    arcpy.AddMessage('- Overlapping routes erased.')

    arcpy.Merge_management(['routes_intersected','routes_erased'],'routes_cleaned')
    arcpy.AddMessage('- Completed cleaning routes.')

    arcpy.DeleteIdentical_management('routes_cleaned','Shape','','')
    arcpy.AddMessage('- Duplicate features removed.')

    ##--- Determine which routes are new versus existing ---##
    arcpy.AddMessage('Determining New versus Existing routes...')
    arcpy.Identity_analysis('routes_cleaned','fiber','routes_identity','ONLY_FID')
    arcpy.MakeFeatureLayer_management('routes_identity','ident')
    selection = "\"FID_FIBERCABLE_forMultimodal\" <> -1"
    arcpy.SelectLayerByAttribute_management('ident',"NEW_SELECTION",selection)
    
    arcpy.AddField_management('ident','Status','Text',field_length=5)
    arcpy.CalculateField_management('ident','Status',"'E'",'PYTHON')
    arcpy.SelectLayerByAttribute_management('ident','CLEAR_SELECTION')

    selection = "\"FID_FIBERCABLE_forMultimodal\" = -1"
    arcpy.SelectLayerByAttribute_management('ident',"NEW_SELECTION",selection)
    arcpy.CalculateField_management('ident','Status',"'N'",'PYTHON')
    arcpy.SelectLayerByAttribute_management('ident','CLEAR_SELECTION')
    
    arcpy.Dissolve_management('ident','routes_dissolve',['FID_routes_cleaned','Status'])
    arcpy.MakeFeatureLayer_management('routes_dissolve','routes')
    arcpy.AddMessage('- Delineated existing routes from new routes.')

    #arcpy.DeleteField_management('routes',['FacilityID','FacilityRank','Name','IncidentCurbApproach','FacilityCurbApproach','IncidentID','Total_Length','startID','endID','startAsset','endAsset','startName','endName','FID_routes_cleaned','FID_FIBERCABLE_forMultimodal'])
    arcpy.DeleteField_management('routes',['FacilityID','FacilityRank','Name','IncidentCurbApproach','FacilityCurbApproach','IncidentID','Total_Length','startID','endID','startAsset','endAsset','startName','endName'])
    arcpy.AddMessage('- Removed unnecessary fields.')

    ##--- Copy the sites and facilities to the output gdb ---##
    arcpy.AddMessage('Finalizing output data...')
    arcpy.CopyFeatures_management(rfpGroup,'parent_sites_'+siteName)
    arcpy.AddMessage('- Copied RFP Sites.')
    arcpy.SelectLayerByLocation_management('hubSites','INTERSECT','routes')
    arcpy.CopyFeatures_management('hubSites','hubs_'+siteName)
    arcpy.AddMessage('- Copied CO Facilities.')

    ##--- Populate SiteName attribute for the Lateral Segments ---##
    arcpy.AddMessage('Calculating route attributes...')
    arcpy.AddField_management('routes','Site_Name','Text',field_length=255)
    arcpy.AddField_management('routes','Type','Text',field_length=5)
    arcpy.AddField_management('routes','Length_mi','FLOAT',field_scale=4)
    arcpy.AddField_management('routes','Route_Name','Text',field_length=255)
    arcpy.AddField_management('routes','FolderPath','Text',field_length=255)
    arcpy.AlterField_management('routes','FID_routes_cleaned','FID_Routes','FID_Routes')
    arcpy.MakeFeatureLayer_management('parent_sites_'+siteName,'sites')
    
    siteNum = int(arcpy.GetCount_management('sites').getOutput(0))
    cursor = arcpy.SearchCursor('sites')
    for row in cursor:
        if isinstance(row.getValue(siteNameField),basestring):
            singleSiteName = "'" + row.getValue(siteNameField) + "'"            
        else:
            singleSiteName = str(int(row.getValue(siteNameField)))
            
        selection = "\"" + siteNameField + "\" = " + singleSiteName
        arcpy.SelectLayerByAttribute_management('sites',"NEW_SELECTION",selection)
        arcpy.SelectLayerByLocation_management('routes','INTERSECT','sites')
        arcpy.CalculateField_management('routes','Site_Name',singleSiteName,'PYTHON')
        arcpy.CalculateField_management('routes','Type',"'L'",'PYTHON')
        arcpy.SelectLayerByAttribute_management('sites','CLEAR_SELECTION')
        arcpy.SelectLayerByAttribute_management('routes','CLEAR_SELECTION')

    selection = "\"Type\" Is NULL"
    arcpy.SelectLayerByAttribute_management('routes',"NEW_SELECTION",selection)
    arcpy.CalculateField_management('routes','Type',"'SL'",'PYTHON')
    arcpy.AddMessage('- Calculated Site Information and Lateral Type.')
    arcpy.SelectLayerByAttribute_management('routes','CLEAR_SELECTION')

    arcpy.CalculateField_management('routes','Length_mi',"round(!shape.length@miles!,4)","PYTHON_9.3")
    arcpy.AddMessage('- Calculated Route Segment Length.')

    arcpy.CalculateField_management("routes_dissolve","Route_Name","[FID_Routes]&\"^\" & [Type]&\"^\"& [Status]&\"^\"&[Length_mi]&\"^\"& [Site_Name]","VB")
    arcpy.AddMessage('- Calculated Route Name.')

    calcVal = "\"Fiber/"+siteName+"/\"& [Route_Name]"
    arcpy.CalculateField_management("routes_dissolve","FolderPath",calcVal,"VB")
    arcpy.AddMessage('- Calculated Folder Path.')

    ##--- Select by route type and total the length by type ---##    
    summaryCSV(siteName,'routes',siteNum)

    outputRoute = 'routes_'+siteName
    arcpy.Rename_management('routes_dissolve',outputRoute)

    return outputRoute

arcpy.AddMessage('**********************************')

rfpParentList = unique_values(inputRFPSites,inputNameField)

if len(rfpParentList) < 2:
    arcpy.AddMessage('Single RFP Route')
    os.chdir(outputLocation)

    if isinstance(rfpParentList[0],basestring):
        siteName = str(rfpParentList[0]).replace(" ","_")
    else:
        siteName = str(int(rfpParentList[0]))

    arcpy.CreateFileGDB_management(outputLocation,siteName + '.gdb')
    arcpy.env.workspace = siteName + '.gdb'
    
    arcpy.MakeFeatureLayer_management(inputRFPSites,'rfpSites')
    rfpGroup = 'rfpSites'

    outputRoute = rfpRoute(rfpGroup)
    tableToCSV(outputRoute,outputLocation + os.sep + siteName + '.csv')

    makeKML()

    addResults()

    cleanup()
    
else:
    arcpy.AddMessage('Batch RFP Routing')
    ##--- Iterate through list to route each one ---##    
    os.chdir(outputLocation)

    ##--- Create summary CSV file with the headers ---##
    with open(outputLocation + os.sep + '_SUMMARY_.csv', 'ab') as summaryFile:
        writer = csv.writer(summaryFile)
        writer.writerow(['Group','Status','Subtotaled Mileage','Number of Sites'])
    summaryFile.close()
    
    for RFP in rfpParentList:
        arcpy.AddMessage('----------------------------------')
        arcpy.AddMessage(RFP)

        if isinstance(RFP,basestring):
            siteName = RFP.replace(" ","_")
            selection = "\"" + inputNameField + "\" = '" + RFP + "'"
        else:
            siteName = str(int(RFP))
            selection = "\"" + inputNameField + "\" = " + str(int(RFP))
        arcpy.CreateFileGDB_management(outputLocation,siteName + '.gdb')
        arcpy.env.workspace = siteName + '.gdb'        
        
        arcpy.MakeFeatureLayer_management(inputRFPSites,'rfpSites')

        rfpGroup = arcpy.SelectLayerByAttribute_management("rfpSites","NEW_SELECTION",selection)
        
        outputRoute = rfpRoute(rfpGroup)
        if outputRoute == "noHub":
            arcpy.AddMessage('*** No Hubs Provided. Cannot complete for ' + siteName + '. ***')
        else:
            tableToCSV(outputRoute,outputLocation + os.sep + siteName + '.csv')
            makeKML()
            addResults()
            cleanup()

arcpy.AddMessage('**********************************')
