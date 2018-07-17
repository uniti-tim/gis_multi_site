import os
import uuid
import datetime
import arcpy
from . import wrappers


def delete(datasets):
    """attempts to delete datasets"""
    if not isinstance(datasets, (list, tuple)):
        datasets = [datasets]
    for dataset in datasets:
        try:
            arcpy.Delete_management(dataset)
        except:
            pass


def unique_name(dataset, unique=uuid.uuid4().hex):
    """adds unique string to name of dataset"""
    name, ext = os.path.splitext(dataset)
    return os.path.normpath("{name}_{unique}{ext}".format(name=name, unique=unique, ext=ext))


def timestamp(format="%H:%M:%S"):
    return datetime.datetime.now().strftime(format)


def create_sql(dataset, field, values):
    """creates an SQL query against input featureClass of the form 'field IN (values)' or field = value """
    # memoize the field type and delimited field names
    field_type, field_delim = __inner(dataset, field)

    if isinstance(values, (list, tuple, set)):
        if not values:
            raise ValueError("{} is empty".format(values))
        query = '{} IN ({})'
        # Remove duplicates and sort for indexed fields
        values = sorted(set(values))
    else:
        query = '{} = {}'
        values = [values]

    # Wrap values in text-like fields so that expression is 'field op ("x", "y", "z")'
    vals = ("'{}'".format(v) for v in values) if field_type in ("STRING", "GUID") else map(str, values)
    return query.format(field_delim, ",".join(vals))


@wrappers.memoize
def __inner(dataset, field):
    d = arcpy.Describe(dataset)
    remap = {"OID@": d.oidFieldName,
             "SHAPE@": d.shapeFieldName,
             "SHAPE@LENGTH": d.lengthFieldName,
             "SHAPE@AREA": d.areaFieldName}
    field = remap.get(field, field)
    try:
        field_type = {f.name: f.type for f in d.fields}[field].upper()
    except KeyError:
        raise ValueError("'{}' does not exist in '{}'".format(field, dataset))
    return field_type, arcpy.AddFieldDelimiters(dataset, field)
