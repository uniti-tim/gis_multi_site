# coding: utf-8
"""
Source Name:   generatepointsfromlines.py
Version:       ArcGIS 10.4/Pro 1.2
Author:        Environmental Systems Research Institute Inc.
Description:   Source for Generate Points From Line geoprocessing tool.
"""

import arcpy
import os
from collections import namedtuple


unit_conversion = dict(CENTIMETERS=0.01, DECIMETERS=0.1, FEET=0.3048,
                       INCHES=0.0254, KILOMETERS=1000.0, METERS=1.0,
                       MILES=1609.347218694438, MILLIMETERS=0.001,
                       NAUTICALMILES=1852.0, POINTS=0.000352777778,
                       UNKNOWN=1.0, YARDS=0.9144)

point_placement = dict(DISTANCE=False, PERCENTAGE=True)


def create_points_from_lines(input_fc, output_fc, spatial_ref, percent=False,
                             dist=True, add_end_points=False):
    """Convert line features to feature class of points

    :param input_fc: Input line features
    :param output_fc: Output point feature class
    :param spatial_ref: The spatial reference of the input
    :param percent: If creating points by percentage (or distance)
    :param dist: The distance used to create points (if percentage == False).
    The distance should be in units of the input (see convert_units)
    :param add_end_points: If True, an extra point will be added from start
    and end point of each line feature
    :return: None
    """

    if percent:
        is_percentage = True
    else:
        is_percentage = False

    # Create output feature class
    arcpy.CreateFeatureclass_management(
        os.path.dirname(output_fc),
        os.path.basename(output_fc),
        geometry_type="POINT",
        spatial_reference=spatial_ref)

    # Add a field to transfer FID from input
    fid_name = 'ORIG_FID'
    arcpy.AddField_management(output_fc, fid_name, 'LONG')

    # Create new points based on input lines
    in_fields = ['SHAPE@', 'OID@']
    out_fields = ['SHAPE@', fid_name]

    rows = int(arcpy.GetCount_management(input_fc)[0])
    arcpy.SetProgressor("step", "Generating Points...", 0, rows)
    with arcpy.da.SearchCursor(input_fc, in_fields) as search_cursor:
        with arcpy.da.InsertCursor(output_fc, out_fields) as insert_cursor:
            for i, row in enumerate(search_cursor, 1):
                arcpy.SetProgressorPosition(i)
                line = row[0]

                if line:  # if null geometry--skip
                    if add_end_points:
                        insert_cursor.insertRow([line.firstPoint, row[1]])

                    increment = (percent or dist)
                    cur_length = increment

                    if is_percentage:
                        max_position = 1.0
                    else:
                        max_position = line.length

                    while cur_length < max_position:
                        new_point = line.positionAlongLine(cur_length,
                                                           is_percentage)
                        insert_cursor.insertRow([new_point, row[1]])
                        cur_length += increment

                    if add_end_points:
                        end_point = line.positionAlongLine(1, True)
                        insert_cursor.insertRow([end_point, row[1]])

    return


def convert_units(dist, param_units, spatial_info):
    """Base unit conversion

    :param dist: Distance
    :param param_units: The units as supplied from tool parameter
    :param spatial_info: arcpy.SpatialReference object
    :return: Distance after converted to new units
    """

    param_units = param_units.upper()

    if param_units in ['', None, 'UNKNOWN']:
        return dist
    else:
        if param_units != 'DECIMALDEGREES':
            p_conversion = unit_conversion[param_units]
        else:
            p_conversion = 111319.8

        try:
            sr_conversion = spatial_info.spatialReference.metersPerUnit
        except AttributeError:
            try:
                input_extent = spatial_info.extent

                centroid = input_extent.polygon.centroid
                point1 = centroid.Y, centroid.X - 0.5
                point2 = centroid.Y, centroid.X + 0.5
                sr_conversion = haversine(point1, point2) * 1000
            except Exception as err:
                # Fallback
                sr_conversion = 111319.8

        return dist * (p_conversion / sr_conversion)


def get_distance_and_units(dist):
    """ Pull distance and units from a linear unit. If units are not
    specified, return UNKNOWN.

    :param dist: Linear units
    :return: Tuple of distance (float) and units (string)
    """
    try:
        dist, units = dist.split(' ', 1)
    except ValueError:
        # ValueError occurs if units are not specified, use 'UNKNOWN'
        units = 'UNKNOWN'

    dist = dist.replace(',', '.')

    return float(dist), units


def haversine(point1, point2):
    """ Calculate the distance between two points on the Earth surface around its curvature.
    Does not account for changes in elevation (datum)

    :param point1 Tuple - Tuple of (Lat, Long) for the first point
    :param point2 Tuple - Tuple of (Lat, Long) for the second point
    :return Float - The distance between the two points about the surface of the globe in kilometers.
    """
    from math import radians, sin, cos, asin, sqrt
    radius_of_earth_km = 6371
    lat1, lng1, lat2, lng2 = list(map(radians, list(point1 + point2)))
    d = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lng2 - lng1) / 2) ** 2
    return 2 * radius_of_earth_km * asin(sqrt(d))


def main(Input_Features, Output_Feature_Class, Point_Placement="DISTANCE",
         Distance=None, Percentage=None, Include_End_Points=False):

    in_features = Input_Features  # String
    out_fc = Output_Feature_Class  # String
    use_percent = point_placement[Point_Placement]  # Str -> Bool
    end_points = Include_End_Points  # Boolean

    describe = arcpy.Describe(in_features)
    spatial_info = namedtuple('spatial_info', 'spatialReference extent')
    sp_info = spatial_info(spatialReference=describe.spatialReference,
                           extent=describe.extent)

    if use_percent:
        percentage = Percentage / 100  # Float
        create_points_from_lines(in_features, out_fc, sp_info.spatialReference,
                                 percent=percentage, add_end_points=end_points)
    else:
        distance = Distance  # String
        distance, param_linear_units = get_distance_and_units(distance)
        distance = convert_units(distance, param_linear_units,
                                 sp_info)

        create_points_from_lines(in_features, out_fc, sp_info.spatialReference,
                                 dist=distance, add_end_points=end_points)

    try:
        arcpy.AddSpatialIndex_management(out_fc)
    except arcpy.ExecuteError:
        pass

    return out_fc


if __name__ == '__main__':
    in_features = arcpy.GetParameterAsText(0)  # String
    out_fc = arcpy.GetParameterAsText(1)  # String
    use_percent = point_placement[arcpy.GetParameter(2)]  # Str -> Bool
    end_points = arcpy.GetParameter(5)  # Boolean

    describe = arcpy.Describe(in_features)
    spatial_info = namedtuple('spatial_info', 'spatialReference extent')
    sp_info = spatial_info(spatialReference=describe.spatialReference,
                           extent=describe.extent)

    if use_percent:
        percentage = arcpy.GetParameter(4) / 100  # Float
        create_points_from_lines(in_features, out_fc, sp_info.spatialReference,
                                 percent=percentage, add_end_points=end_points)
    else:
        distance = arcpy.GetParameterAsText(3)  # String
        distance, param_linear_units = get_distance_and_units(distance)
        distance = convert_units(distance, param_linear_units,
                                 sp_info)

        create_points_from_lines(in_features, out_fc, sp_info.spatialReference,
                                 dist=distance, add_end_points=end_points)

    try:
        arcpy.AddSpatialIndex_management(out_fc)
    except arcpy.ExecuteError:
        pass
