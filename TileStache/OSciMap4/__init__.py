""" Provider that returns OpenScienceMap vector-tile responses from PostGIS queries.

Note:

A Standard osm2pgsql import can be used as source. The Database requires the functions
for 'get_tile(x,y,z)' and 'get_tile_poi(x,y,z)' that return columns of 'tags' as hstore
and geometries as ewkb ('geom'). Geometries need to be clipped to tile boundary
(plus a few pixel offset), scaled and translated to tile extents.

Keyword arguments:

  dsn:
    Database connection string suitable for use in psycopg2.connect().
    See http://initd.org/psycopg/docs/module.html#psycopg2.connect for more.

Example Configuration:
"map": {
    "provider": {
        "class": "TileStache.OSciMap:Provider",
        "kwargs": {
            "dsn": "dbname=planet user=osm password=osm"
            "query_tile": "SELECT tags, geom FROM map.get_tile(%s,%s,%s)",
            "query_poi": "SELECT tags, geom FROM map.get_tile_poi(%s,%s,%s)"
        }
    }
}
"""
import types
import TileData_v4_pb2
from GeomEncoder import GeomEncoder
from StaticVals import getValues
from StaticKeys import getKeys
from TagRewrite import fixTag
from TileStache.Core import KnownUnknown
import re
import logging
import struct

#import gzip
#import cStringIO
#import zlib

statickeys = getKeys()
staticvals = getValues()

# custom keys/values start at attrib_offset
attrib_offset = 256

try:
    from psycopg2 import connect as _connect
    from psycopg2.extras import register_hstore
    from psycopg2.pool import ThreadedConnectionPool
except ImportError:
    # At least it should be possible to build the documentation.
    pass


class EmptyResponse:
    """ Wrapper class for OpenScienceMapTile response that makes it behave like a PIL.Image object.

        TileStache.getTile() expects to be able to save one of these to a buffer.
    """
    def __init__(self, content, tile):
        self.content = content
        self.tile = tile

    def save(self, out, format):
        if format != 'OSMTile':
            raise KnownUnknown('OpenScienceMap provider only saves .osmtile tiles, not "%s"' % format)

        out.write(struct.pack(">I", 0))


class Provider:
    """
    """
    def __init__(self, layer, dsn, query_tile, query_poi):
        logging.info("init %s", query_tile)

        self.extension = 'vtm'

        self.layer = layer
        self.dbdsn = dsn
        self.extents = 4096
        self.query_tile = query_tile
        self.query_tile_poi = query_poi

    def renderTile(self, width, height, srs, coord):
        """ Render a single tile, return a SaveableResponse instance.
        """
        ##return EmptyResponse(None, coord)
        tile = VectorTile(self.extents)

        conn = _connect(self.dbdsn)
        db = conn.cursor()
        register_hstore(conn, True, False)

        try:
            db.execute(self.query_tile, (coord.column, coord.row, coord.zoom))
        except Exception, e:
            logging.error("db: %s\n %s", coord, e)
            raise KnownUnknown("query failed")

        rows = db.fetchall()

        try:
            db.execute(self.query_tile_poi, (coord.column, coord.row, coord.zoom))
        except Exception, e:
            logging.error("db: %s\n %s", coord, e)
            raise KnownUnknown("query failed")

        for row in rows:
            # ignore empty geometry
            if (row[0] is None) or (row[1] is None):
                logging.info("empty geom in %s -> %s", coord, row[0])
                continue

            tile.addFeature(row, coord)

        rows = db.fetchall()

        for row in rows:
            # ignore empty feature
            if (row[0] is None) or (row[1] is None):
                continue
            tile.addFeature(row, coord)

        # tile.num_tags = len(tile.keys)
        tile.complete()

        try:
            conn.commit()
        except Exception, e:
            logging.error(">>> %s", e)
            conn.rollback()

        conn.close()
        return SaveableResponse(tile, coord)


    def getTypeByExtension(self, extension):
        """ Get mime-type and format by file extension.
            This only accepts "vtm" for the time being.
        """
        if extension.lower() == 'vtm':
            return 'application/x-protobuf', 'VTM'

        raise KnownUnknown('OpenScienceMap Provider only makes ".vtm", not "%s"' % extension)

class VectorTile:
    """
    """
    def __init__(self, extents):
        self.geomencoder = GeomEncoder(extents)

        # TODO count to sort by number of occurrences
        self.keydict = {}
        self.cur_key = attrib_offset

        self.valdict = {}
        self.cur_val = attrib_offset

        self.tagdict = {}
        self.num_tags = 0

        self.out = TileData_v4_pb2.Data()
        self.out.version = 4


    def complete(self):
        if self.num_tags == 0:
            logging.info("empty tags")

        self.out.num_tags = self.num_tags

        if self.cur_key - attrib_offset > 0:
            self.out.num_keys = self.cur_key - attrib_offset

        if self.cur_val - attrib_offset > 0:
            self.out.num_vals = self.cur_val - attrib_offset

    def addFeature(self, row, coord):
        geom = self.geomencoder
        tags = []

        #height = None
        layer = None

        for tag in row[0].iteritems():
            # use unsigned int for layer. i.e. map to 0..10
            if "layer" == tag[0]:
                layer = self.getLayer(tag[1])
                continue

            tag = fixTag(tag, coord.zoom)

            if tag is None:
                continue

            tags.append(self.getTagId(tag))

        if len(tags) == 0:
            logging.debug('missing tags')
            return

        geom.parseGeometry(row[1])
        feature = None;

        if geom.isPoint:
            feature = self.out.points.add()
            # add number of points (for multi-point)
            if len(geom.coordinates) > 2:
                logging.info('points %s' %len(geom.coordinates))
                feature.indices.add(geom.coordinates/2)
        else:
            # empty geometry
            if len(geom.index) == 0:
                logging.debug('empty geom: %s %s' % row[0])
                return

            if geom.isPoly:
                feature = self.out.polygons.add()
            else:
                feature = self.out.lines.add()

            # add coordinate index list (coordinates per geometry)
            feature.indices.extend(geom.index)

            # add indice count (number of geometries)
            if len(feature.indices) > 1:
                feature.num_indices = len(feature.indices)

        # add coordinates
        feature.coordinates.extend(geom.coordinates)

        # add tags
        feature.tags.extend(tags)
        if len(tags) > 1:
            feature.num_tags = len(tags)

        # add osm layer
        if layer is not None and layer != 5:
            feature.layer = layer

        #logging.debug('tags %d, indices %d' %(len(tags),len(feature.indices)))


    def getLayer(self, val):
        try:
            l = max(min(10, int(val)) + 5, 0)
            if l != 0:
                return l
        except ValueError:
            logging.debug("layer invalid %s" %val)

        return None

    def getKeyId(self, key):
        if key in statickeys:
            return statickeys[key]

        if key in self.keydict:
            return self.keydict[key]

        self.out.keys.append(key);

        r = self.cur_key
        self.keydict[key] = r
        self.cur_key += 1
        return r

    def getAttribId(self, var):
        if var in staticvals:
            return staticvals[var]

        if var in self.valdict:
            return self.valdict[var]

        self.out.values.append(var);

        r = self.cur_val
        self.valdict[var] = r
        self.cur_val += 1
        return r


    def getTagId(self, tag):
        if self.tagdict.has_key(tag):
                return self.tagdict[tag]

        key = self.getKeyId(tag[0].decode('utf-8'))
        val = self.getAttribId(tag[1].decode('utf-8'))

        self.out.tags.append(key)
        self.out.tags.append(val)
        #logging.info("add tag %s - %d/%d" %(tag, key, val))
        r = self.num_tags
        self.tagdict[tag] = r
        self.num_tags += 1
        return r

class SaveableResponse:
    """ Wrapper class for OpenScienceMapTile response that makes it behave like a
        PIL.Image object.TileStache.getTile() expects to be able to save one of
        these to a buffer.
    """
    def __init__(self, content, tile):
        self.content = content.out

        self.tile = tile

    def save(self, out, format):
        if format != 'VTM':
            raise KnownUnknown('OpenScienceMap provider only saves .vtm tiles, not "%s"' % format)

        data = self.content.SerializeToString()

        # zbuf = cStringIO.StringIO()
        # zfile = gzip.GzipFile(mode='wb', fileobj=zbuf, compresslevel=9)
        # zfile.write(data)
        # zout = zlib.compress(data, 9)
        # logging.debug("serialized %s - %fkb <> %fkb" %(self.tile, len(data)/1024.0, len(zout)/1024.0))
        out.write(struct.pack(">I", len(data)))
        out.write(data)
        # zfile.close()
        # out.write(zbuf.getvalue())
        # out.write(self.content.SerializeToString())
