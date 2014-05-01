import types
from Mapbox import vector_tile_pb2
from Mapbox.GeomEncoder import GeomEncoder
from shapely.wkb import loads

from math import floor, fabs

from TileStache.Core import KnownUnknown
import re
import logging
import struct

# coordindates are scaled to this range within tile
extents = 4096
cmd_bits = 3
path_multiplier = 16
tolerance = 0

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

    def addFeatures(self, features, coord, extents, layer_name=""):
        self.layer         = self.tile.layers.add()
        self.layer.name    = layer_name
        self.layer.version = 2
        self.layer.extent  = extents
        self.feature_count = 0
        self.keys   = []
        self.values = []
        self.pixels = []
        for feature in features:
            self.addFeature(feature, coord)

    def addFeature(self, feature, coord):
        geom = self.geomencoder
        x_ = coord.column
        y_ = coord.row
        cmd= 1
        skipped_last = False

        f = self.layer.features.add()
        self.feature_count += 1
        f.id = self.feature_count
        f.type = self.tile.Point if geom.isPoint else (self.tile.Polygon if geom.isPoly else self.tile.LineString)

        self._handle_attr(self.layer, f, feature[1])

        geom.parseGeometry(feature[0])
        coordinates = []
        for coords in self._chunker(geom.coordinates,2):
            coordinates.append((coords[0], coords[1]))
        length = geom.num_points

        f.geometry.append(self._encode_cmd_length(1, length))

        it = 0
        cmd= 1 if geom.isPoint else 2 # TODO: figure out if cmd can change within a feature geom

        for coordinate in coordinates:
            x,y = coordinate[0],coordinate[1]

            cur_x = int(floor((x * path_multiplier) + 0.5))
            cur_y = int(floor((y * path_multiplier) + 0.5))

            if skipped_last and cmd == 1:
                self._handle_skipped_last(f, cur_x, cur_y, x_, y_)

            dx = cur_x - x
            dy = cur_y - y

            sharp_turn_ahead = False

            if (it+2 <= len(coordinates)):
                next_coord = coordinates[it+1]
                next_x, next_y = next_coord[0], next_coord[1]
                next_dx = fabs(cur_x - int(floor((next_x * path_multiplier) + 0.5)))
                next_dy = fabs(cur_y - int(floor((next_y * path_multiplier) + 0.5)))
                if ((next_dx == 0 and next_dy >= tolerance) or (next_dy == 0 and next_dx >= tolerance)):
                    sharp_turn_ahead = True


            if (sharp_turn_ahead or fabs(dx) >= tolerance or fabs(dy) >= tolerance):
                f.geometry.append((dx << 1) ^ (dx >> 31))
                f.geometry.append((dy << 1) ^ (dy >> 31))
                x_ = cur_x
                y_ = cur_y
                skipped_last = False
            else:
                skipped_last = True
            it = it+1

        f.geometry.append(self._encode_cmd_length(7, length))

    def _encode_cmd_length(self, cmd, length):
        # cmd: 1 (MOVE_TO)
        # cmd: 2 (LINE_TO)
        # cmd: 7 (CLOSE_PATH)
        return (length << cmd_bits) | (cmd & ((1 << cmd_bits) - 1))

    def _chunker(self, seq, size):
        return (seq[pos:pos + size] for pos in xrange(0, len(seq), size))

    def _handle_skipped_last(self, f, cur_x, cur_y, x_, y_):
        # TODO
        return True

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
