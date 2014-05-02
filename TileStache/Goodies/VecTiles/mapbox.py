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

CMD_MOVE_TO = 1
CMD_LINE_TO = 2
CMD_SEG_END = 7

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
        cmd= -1
        cmd_idx = -1
        vtx_cmd = -1
        prev_cmd= -1
        
        skipped_index = -1
        skipped_last = False
        cur_x = 0
        cur_y = 0

        f = self.layer.features.add()
        self.feature_count += 1
        f.id = self.feature_count
        f.type = self.tile.Point if geom.isPoint else (self.tile.Polygon if geom.isPoly else self.tile.LineString)

        self._handle_attr(self.layer, f, feature[1])

        geom.parseGeometry(feature[0])
        coordinates = []
        points = self._chunker(geom.coordinates,2) # x,y corodinates grouped as one point. 
        for i, coords in enumerate(points):
            coordinates.append({
                'x': coords[0], 
                'y': coords[1],
                'cmd': self._get_cmd_type(f.type, i, len(points))})
        
        it = 0
        length = 0
        
        while (True):
            if it >= len(coordinates):
                break;
            
            x,y,vtx_cmd = coordinates[it]['x'],coordinates[it]['y'],coordinates[it]['cmd']
            
            if vtx_cmd != cmd:
                if (cmd_idx >= 0):
                    f.geometry.__setitem__(cmd_idx, self._encode_cmd_length(cmd, length))

                cmd = vtx_cmd
                length = 0
                cmd_idx = len(f.geometry)
                f.geometry.append(0) #placeholder added in first pass

            if (vtx_cmd == CMD_MOVE_TO or vtx_cmd == CMD_LINE_TO):
                if cmd == CMD_MOVE_TO and skipped_last and skipped_index >1:
                    self._handle_skipped_last(f, skipped_index, cur_x, cur_y, x_, y_)
                
                # Compute delta to the previous coordinate.
                cur_x = int(floor((x * path_multiplier) + 0.5))
                cur_y = int(floor((y * path_multiplier) + 0.5))

                dx = cur_x - x_
                dy = cur_y - y_
                
                sharp_turn_ahead = False

                if (it+2 <= len(coordinates)):
                    next_coord = coordinates[it+1]
                    if next_coord['cmd'] == CMD_LINE_TO:
                        next_x, next_y = next_coord['x'], next_coord['y']
                        next_dx = fabs(cur_x - int(floor((next_x * path_multiplier) + 0.5)))
                        next_dy = fabs(cur_y - int(floor((next_y * path_multiplier) + 0.5)))
                        if ((next_dx == 0 and next_dy >= tolerance) or (next_dy == 0 and next_dx >= tolerance)):
                            sharp_turn_ahead = True

                # Keep all move_to commands, but omit other movements that are
                # not >= the tolerance threshold and should be considered no-ops.
                # NOTE: length == 0 indicates the command has changed and will
                # preserve any non duplicate move_to or line_to
                if length == 0 or sharp_turn_ahead or fabs(dx) >= tolerance or fabs(dy) >= tolerance:
                    # Manual zigzag encoding.
                    f.geometry.append((dx << 1) ^ (dx >> 31))
                    f.geometry.append((dy << 1) ^ (dy >> 31))
                    x_ = cur_x
                    y_ = cur_y
                    skipped_last = False
                    length = length + 1
                else:
                    skipped_last = True
                    skipped_index = len(f.geometry)
            elif vtx_cmd == CMD_SEG_END:
                if prev_cmd != CMD_SEG_END:
                    length = length + 1
                    break;
            else:
                raise Exception("Unknown command type: '%s'" % vtx_cmd)
            
            it = it + 1
            prev_cmd = cmd

        # at least one vertex + cmd/length
        if (skipped_last and skipped_index > 1): 
            # if we skipped previous vertex we just update it to the last one here.
            handle_skipped_last(f, skipped_index, cur_x, cur_y, x_, y_)
        
        # Update the last length/command value.
        if (cmd_idx >= 0):
            f.geometry.__setitem__(cmd_idx, self._encode_cmd_length(cmd, length))


    # TODO: figure out if cmd can change within a feature geom
    def _get_cmd_type(self, gtype, i, points):
        cmd_type = -1
        if gtype == self.tile.Point:
            cmd_type = CMD_MOVE_TO
        elif gtype == self.tile.Polygon or gtype == self.tile.LineString:
            cmd_type = CMD_LINE_TO
        if i==0:
            cmd_type = CMD_MOVE_TO
        if gtype == self.tile.Polygon and i+1==points:
            cmd_type = CMD_SEG_END
        return cmd_type

    def _encode_cmd_length(self, cmd, length):
        # cmd: 1 (MOVE_TO)
        # cmd: 2 (LINE_TO)
        # cmd: 7 (CLOSE_PATH)
        return (length << cmd_bits) | (cmd & ((1 << cmd_bits) - 1))

    def _chunker(self, seq, size):
        return [seq[pos:pos + size] for pos in xrange(0, len(seq), size)]

    def _handle_skipped_last(self, f, skipped_index, cur_x, cur_y, x_, y_):
        last_x = f.geometry[skipped_index - 2]
        last_y = f.geometry[skipped_index - 1]
        last_dx = ((last_x >> 1) ^ (-(last_x & 1)))
        last_dy = ((last_y >> 1) ^ (-(last_y & 1)))
        dx = cur_x - x_ + last_dx
        dy = cur_y - y_ + last_dy
        x_ = cur_x
        y_ = cur_y
        f.geometry.__setitem__(skipped_index - 2, ((dx << 1) ^ (dx >> 31)))
        f.geometry.__setitem__(skipped_index - 1, ((dy << 1) ^ (dy >> 31)))

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
                    val.string_value = unicode(v,'utf8')
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
