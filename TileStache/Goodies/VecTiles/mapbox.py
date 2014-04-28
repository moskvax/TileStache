import types
from Mapbox import vector_tile_pb2
from Mapbox.GeomEncoder import GeomEncoder
from shapely.wkb import loads

from TileStache.Core import KnownUnknown
import re
import logging
import struct

# coordindates are scaled to this range within tile
extents = 4096

def decode(file):
    ''' Stub function to decode a mapbox vector tile file into a list of features.
    
        Not currently implemented, modeled on geojson.decode().
    '''
    raise NotImplementedError('mapbox.decode() not yet written')

def encode(file, features, coord, layer_name):
        tile = VectorTile(extents)

        tile.addFeatures(features, coord, extents, layer_name)

        data = tile.tile.SerializeToString()
        file.write(struct.pack(">I", len(data)))
        file.write(data)

def merge(file, feature_layers, coord):
    ''' Retrieve a list of GeoJSON tile responses and merge them into one.
    
        get_tiles() retrieves data and performs basic integrity checks.
    '''
    tile = VectorTile(extents)

    for layer in feature_layers:
        tile.addFeatures(layer['features'], coord, extents, layer['name'])

    data = tile.tile.SerializeToString()
    file.write(struct.pack(">I", len(data)))
    file.write(data)

class VectorTile:
    """
    """
    def __init__(self, extents, layer_name=""):
        self.geomencoder   = GeomEncoder(extents)

        self.tile          = vector_tile_pb2.tile()       
        self.feature_count = 0
        self.keys   = []
        self.values = []
        self.pixels = []


    def addFeatures(self, features, coord, extents, layer_name=""):
        self.layer         = self.tile.layers.add()
        self.layer.name    = layer_name
        self.layer.version = 2
        self.layer.extent  = extents
        for feature in features:
            self.addFeature(feature, coord)

    def addFeature(self, feature, coord):
        geom = self.geomencoder
        
        f = self.layer.features.add()
        self.feature_count += 1
        f.id = self.feature_count
        
        self._handle_attr(self.layer, f, feature[1])

        geom.parseGeometry(feature[0])

        if geom.isPoint:
            f.type = self.tile.Point
        else:
            # # empty geometry
            # if len(geom.index) == 0:
            #     logging.debug('empty geom: %s %s' % feature[1])
            #     return

            if geom.isPoly:
                f.type = self.tile.Polygon
            else:
                f.type = self.tile.LineString

            # add coordinate index list (coordinates per geometry)
            # feature.indices.extend(geom.index)

            # add indice count (number of geometries)
            # if len(feature.indices) > 1:
            #     feature.num_indices = len(feature.indices)

        # add coordinates
        for coordinate in geom.coordinates:
            if coordinate <= 4096 and coordinate > 0:
                f.geometry.append(coordinate)

    def _handle_attr(self, layer, feature, props):
        for k,v in props.items():
            if k not in self.keys:
                layer.keys.append(k)
                self.keys.append(k)
                idx = self.keys.index(k)
                feature.tags.append(idx)
            else:
                idx = self.keys.index(k)
                feature.tags.append(idx)
            if v not in self.values:
                if (isinstance(v,bool)):
                    val = layer.values.add()
                    val.bool_value = v
                elif (isinstance(v,str)) or (isinstance(v,unicode)):
                    val = layer.values.add()
                    val.string_value = v
                elif (isinstance(v,int)):
                    val = layer.values.add()
                    val.int_value = v
                elif (isinstance(v,float)):
                    val = layer.values.add()
                    val.double_value = v
                # else:
                    # raise Exception("Unknown value type: '%s'" % type(v))
            self.values.append(v)
            feature.tags.append(self.values.index(v))
