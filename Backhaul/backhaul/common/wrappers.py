import arcpy


class ClosestFacilityHelper(object):
    """Helper class to handle Closest Facility layers"""
    def __init__(self, layer):
        self.__desc = None
        if isinstance(layer, arcpy._mapping.Layer):
            # Layer object
            self.__layer = layer
        elif isinstance(layer, arcpy.arcobjects.Result):
            # result object from a GP tool
            self.__layer = layer.getOutput(0)
        elif isinstance(layer, basestring):
            # String referencing an already existing layer, such as from parameters[x].valueAsText
            # String referencing a .lyr file on disk
            self.__layer = arcpy.mapping.Layer(layer)
            self.__desc = arcpy.Describe(layer)
        else:
            raise ValueError("{} is not a layer".format(layer))

        # For .lyr files, arcpy.Describe() returns the description of the layerfile, not the contents.
        # The NALayer object is accessed via arcpy.Describe("my layer.lyr").layer
        if self.__desc is None:
            self.__desc = arcpy.Describe(self.__layer)
        self.__desc = getattr(self.__desc, "layer", self.__desc)

        if not self.__layer.isNetworkAnalystLayer:
            raise ValueError("{} is not a NetworkAnalystLayer".format(layer))
        if self.__desc.solverName.upper() != 'CLOSEST FACILITY SOLVER':
            raise ValueError("{} is not a Closest Facility layer".format(layer))

        self.__classNames = arcpy.na.GetNAClassNames(self.__layer)
        self.__children = {c.name: c for c in self.__layer}

    @property
    def na_layer(self):
        return self.__layer

    @property
    def describe(self):
        return self.__desc

    @property
    def barriers(self):
        return self.__children[self.__classNames['Barriers']]

    @property
    def routes(self):
        return self.__children[self.__classNames['CFRoutes']]

    @property
    def facilities(self):
        return self.__children[self.__classNames['Facilities']]

    @property
    def incidents(self):
        return self.__children[self.__classNames['Incidents']]

    @property
    def polygon_barriers(self):
        return self.__children[self.__classNames['PolygonBarriers']]

    @property
    def polyline_barriers(self):
        return self.__children[self.__classNames['PolylineBarriers']]


def memoize(f):
    """ Memoization decorator for functions taking one or more arguments.
    https://wiki.python.org/moin/PythonDecoratorLibrary/#Alternate_memoize_as_dict_subclass
    # Modified to support unhashable args
    """

    class memodict(dict):
        def __init__(self, f):
            self.f = f

        def __call__(self, *args):
            try:
                return self[args]
            except TypeError:
                return self.f(*args)

        def __missing__(self, key):
            ret = self[key] = self.f(*key)
            return ret

    return memodict(f)
