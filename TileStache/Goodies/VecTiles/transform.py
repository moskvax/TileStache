# transformation functions to apply to features

from numbers import Number
from StreetNames import short_street_name
from collections import defaultdict
from shapely.strtree import STRtree
from shapely.geometry.base import BaseMultipartGeometry
from shapely.geometry.polygon import orient
from shapely.ops import linemerge
from shapely.geometry.multilinestring import MultiLineString
import re


# attempts to convert x to a floating point value,
# first removing some common punctuation. returns
# None if conversion failed.
def to_float(x):
    if x is None:
        return None
    # normalize punctuation
    x = x.replace(';', '.').replace(',', '.')
    try:
        return float(x)
    except ValueError:
        return None


feet_pattern = re.compile('([+-]?[0-9.]+)\'(?: *([+-]?[0-9.]+)")?')
number_pattern = re.compile('([+-]?[0-9.]+)')


def _to_float_meters(x):
    if x is None:
        return None

    as_float = to_float(x)
    if as_float is not None:
        return as_float

    # trim whitespace to simplify further matching
    x = x.strip()

    # try explicit meters suffix
    if x.endswith(' m'):
        meters_as_float = to_float(x[:-2])
        if meters_as_float is not None:
            return meters_as_float

    # try if it looks like an expression in feet via ' "
    feet_match = feet_pattern.match(x)
    if feet_match is not None:
        feet = feet_match.group(1)
        inches = feet_match.group(2)
        feet_as_float = to_float(feet)
        inches_as_float = to_float(inches)

        total_inches = 0.0
        parsed_feet_or_inches = False
        if feet_as_float is not None:
            total_inches = feet_as_float * 12.0
            parsed_feet_or_inches = True
        if inches_as_float is not None:
            total_inches += inches_as_float
            parsed_feet_or_inches = True
        if parsed_feet_or_inches:
            meters = total_inches * 0.02544
            return meters

    # try and match the first number that can be parsed
    for number_match in number_pattern.finditer(x):
        potential_number = number_match.group(1)
        as_float = to_float(potential_number)
        if as_float is not None:
            return as_float

    return None


def _coalesce(properties, *property_names):
    for prop in property_names:
        val = properties.get(prop)
        if val:
            return val
    return None


def _remove_properties(properties, *property_names):
    for prop in property_names:
        properties.pop(prop, None)
    return properties


def _building_calc_levels(levels):
    levels = max(levels, 1)
    levels = (levels * 3) + 2
    return levels


def _building_calc_min_levels(min_levels):
    min_levels = max(min_levels, 0)
    min_levels = min_levels * 3
    return min_levels


def _building_calc_height(height_val, levels_val, levels_calc_fn):
    height = _to_float_meters(height_val)
    if height is not None:
        return height
    levels = _to_float_meters(levels_val)
    if levels is None:
        return None
    levels = levels_calc_fn(levels)
    return levels


road_kind_highway = set(('motorway', 'motorway_link'))
road_kind_major_road = set(('trunk', 'trunk_link', 'primary', 'primary_link',
                            'secondary', 'secondary_link',
                            'tertiary', 'tertiary_link'))
road_kind_path = set(('footpath', 'track', 'footway', 'steps', 'pedestrian',
                      'path', 'cycleway'))
road_kind_rail = set(('rail', 'tram', 'light_rail', 'narrow_gauge',
                      'monorail', 'subway'))


def _road_kind(properties):
    highway = properties.get('highway')
    if highway in road_kind_highway:
        return 'highway'
    if highway in road_kind_major_road:
        return 'major_road'
    if highway in road_kind_path:
        return 'path'
    railway = properties.get('railway')
    if railway in road_kind_rail:
        return 'rail'
    return 'minor_road'


def add_id_to_properties(shape, properties, fid, zoom):
    properties['id'] = fid
    return shape, properties, fid


def detect_osm_relation(shape, properties, fid, zoom):
    # Assume all negative ids indicate the data was a relation. At the
    # moment, this is true because only osm contains negative
    # identifiers. Should this change, this logic would need to become
    # more robust
    if isinstance(fid, Number) and fid < 0:
        properties['osm_relation'] = True
    return shape, properties, fid


def remove_feature_id(shape, properties, fid, zoom):
    return shape, properties, None


def building_kind(shape, properties, fid, zoom):
    kind = properties.get('kind')
    if kind:
        return shape, properties, fid
    building = _coalesce(properties, 'building:part', 'building')
    if building and building != 'yes':
        kind = building
    else:
        kind = _coalesce(properties, 'amenity', 'shop', 'tourism')
    if kind:
        properties['kind'] = kind
    return shape, properties, fid


def building_height(shape, properties, fid, zoom):
    height = _building_calc_height(
        properties.get('height'), properties.get('building:levels'),
        _building_calc_levels)
    if height is not None:
        properties['height'] = height
    else:
        properties.pop('height', None)
    return shape, properties, fid


def building_min_height(shape, properties, fid, zoom):
    min_height = _building_calc_height(
        properties.get('min_height'), properties.get('building:min_levels'),
        _building_calc_min_levels)
    if min_height is not None:
        properties['min_height'] = min_height
    else:
        properties.pop('min_height', None)
    return shape, properties, fid


def building_trim_properties(shape, properties, fid, zoom):
    properties = _remove_properties(
        properties,
        'amenity', 'shop', 'tourism',
        'building', 'building:part',
        'building:levels', 'building:min_levels')
    return shape, properties, fid


def road_kind(shape, properties, fid, zoom):
    source = properties.get('source')
    assert source, 'Missing source in road query'
    if source == 'naturalearthdata.com':
        return shape, properties, fid

    properties['kind'] = _road_kind(properties)
    return shape, properties, fid


def road_classifier(shape, properties, fid, zoom):
    source = properties.get('source')
    assert source, 'Missing source in road query'
    if source == 'naturalearthdata.com':
        return shape, properties, fid

    highway = properties.get('highway')
    tunnel = properties.get('tunnel')
    bridge = properties.get('bridge')
    is_link = 'yes' if highway and highway.endswith('_link') else 'no'
    is_tunnel = 'yes' if tunnel and tunnel in ('yes', 'true') else 'no'
    is_bridge = 'yes' if bridge and bridge in ('yes', 'true') else 'no'
    properties['is_link'] = is_link
    properties['is_tunnel'] = is_tunnel
    properties['is_bridge'] = is_bridge
    return shape, properties, fid


def road_sort_key(shape, properties, fid, zoom):
    # Calculated sort value is in the range 0 to 39
    sort_val = 0

    # Base layer range is 15 to 24
    highway = properties.get('highway', '')
    railway = properties.get('railway', '')
    aeroway = properties.get('aeroway', '')

    if highway == 'motorway':
        sort_val += 24
    elif railway in ('rail', 'tram', 'light_rail', 'narrow_guage', 'monorail'):
        sort_val += 23
    elif highway == 'trunk':
        sort_val += 22
    elif highway == 'primary':
        sort_val += 21
    elif highway == 'secondary' or aeroway == 'runway':
        sort_val += 20
    elif highway == 'tertiary' or aeroway == 'taxiway':
        sort_val += 19
    elif highway.endswith('_link'):
        sort_val += 18
    elif highway in ('residential', 'unclassified', 'road', 'living_street'):
        sort_val += 17
    elif highway in ('unclassified', 'service', 'minor'):
        sort_val += 16
    else:
        sort_val += 15

    if zoom >= 15:
        # Bridges and tunnels add +/- 10
        bridge = properties.get('bridge')
        tunnel = properties.get('tunnel')
        if bridge in ('yes', 'true'):
            sort_val += 10
        elif (tunnel in ('yes', 'true') or
              (railway == 'subway' and tunnel not in ('no', 'false'))):
            sort_val -= 10

        # Explicit layer is clipped to [-5, 5] range
        layer = properties.get('layer')
        if layer:
            layer_float = to_float(layer)
            if layer_float is not None:
                layer_float = max(min(layer_float, 5), -5)
                # The range of values from above is [5, 34]
                # For positive layer values, we want the range to be:
                # [34, 39]
                if layer_float > 0:
                    sort_val = int(layer_float + 34)
                # For negative layer values, [0, 5]
                elif layer_float < 0:
                    sort_val = int(layer_float + 5)

    properties['sort_key'] = sort_val

    return shape, properties, fid


def road_trim_properties(shape, properties, fid, zoom):
    properties = _remove_properties(properties, 'bridge', 'layer', 'tunnel')
    return shape, properties, fid


def _reverse_line_direction(shape):
    if shape.type != 'LineString':
        return False
    shape.coords = shape.coords[::-1]
    return True


def road_oneway(shape, properties, fid, zoom):
    oneway = properties.get('oneway')
    if oneway in ('-1', 'reverse'):
        did_reverse = _reverse_line_direction(shape)
        if did_reverse:
            properties['oneway'] = 'yes'
    elif oneway in ('true', '1'):
        properties['oneway'] = 'yes'
    elif oneway in ('false', '0'):
        properties['oneway'] = 'no'
    return shape, properties, fid


def road_abbreviate_name(shape, properties, fid, zoom):
    name = properties.get('name', None)
    if not name:
        return shape, properties, fid
    short_name = short_street_name(name)
    properties['name'] = short_name
    return shape, properties, fid


def route_name(shape, properties, fid, zoom):
    route_name = properties.get('route_name', '')
    if route_name:
        name = properties.get('name', '')
        if route_name == name:
            del properties['route_name']
    return shape, properties, fid


def place_ne_capital(shape, properties, fid, zoom):
    source = properties.get('source', '')
    if source == 'naturalearthdata.com':
        kind = properties.get('kind', '')
        if kind == 'Admin-0 capital':
            properties['capital'] = 'yes'
        elif kind == 'Admin-1 capital':
            properties['state_capital'] = 'yes'
    return shape, properties, fid


def water_tunnel(shape, properties, fid, zoom):
    tunnel = properties.pop('tunnel', None)
    if tunnel in (None, 'no', 'false', '0'):
        properties.pop('is_tunnel', None)
    else:
        properties['is_tunnel'] = 'yes'
    return shape, properties, fid


boundary_admin_level_mapping = {
    2: 'country',
    4: 'state',
    6: 'county',
    8: 'municipality',
}


def boundary_kind(shape, properties, fid, zoom):
    kind = properties.get('kind')
    if kind:
        return shape, properties, fid
    admin_level_str = properties.get('admin_level')
    if admin_level_str is None:
        return shape, properties, fid
    try:
        admin_level_int = int(admin_level_str)
    except ValueError:
        return shape, properties, fid
    kind = boundary_admin_level_mapping.get(admin_level_int)
    if kind:
        properties['kind'] = kind
    return shape, properties, fid


def tags_create_dict(shape, properties, fid, zoom):
    tags_hstore = properties.get('tags')
    if tags_hstore:
        tags = dict(tags_hstore)
        properties['tags'] = tags
    return shape, properties, fid


def tags_remove(shape, properties, fid, zoom):
    properties.pop('tags', None)
    return shape, properties, fid


tag_name_alternates = (
    'int_name',
    'loc_name',
    'nat_name',
    'official_name',
    'old_name',
    'reg_name',
    'short_name',
)


def tags_name_i18n(shape, properties, fid, zoom):
    tags = properties.get('tags')
    if not tags:
        return shape, properties, fid

    name = properties.get('name')
    if not name:
        return shape, properties, fid

    for k, v in tags.items():
        if (k.startswith('name:') and v != name or
                k.startswith('alt_name:') and v != name or
                k.startswith('alt_name_') and v != name or
                k.startswith('old_name:') and v != name or
                k.startswith('left:name:') and v != name or
                k.startswith('right:name:') and v != name):
            properties[k] = v

    for alt_tag_name_candidate in tag_name_alternates:
        alt_tag_name_value = tags.get(alt_tag_name_candidate)
        if alt_tag_name_value and alt_tag_name_value != name:
            properties[alt_tag_name_candidate] = alt_tag_name_value

    return shape, properties, fid


def _no_none_min(a, b):
    """
    Usually, `min(None, a)` will return None. This isn't
    what we want, so this one will return a non-None
    argument instead. This is basically the same as
    treating None as greater than any other value.
    """

    if a is None:
        return b
    elif b is None:
        return a
    else:
        return min(a, b)


def _sorted_attributes(features, attrs, attribute):
    """
    When the list of attributes is a dictionary, use the
    sort key parameter to order the feature attributes.
    evaluate it as a function and return it. If it's not
    in the right format, attrs isn't a dict then returns
    None.
    """

    sort_key = attrs.get('sort_key')
    reverse = attrs.get('reverse')

    assert sort_key is not None, "Configuration " + \
        "parameter 'sort_key' is missing, please " + \
        "check your configuration."

    # first, we find the _minimum_ ordering over the
    # group of key values. this is because we only do
    # the intersection in groups by the cutting
    # attribute, so can only sort in accordance with
    # that.
    group = dict()
    for feature in features:
        val = feature[1].get(sort_key)
        key = feature[1].get(attribute)
        val = _no_none_min(val, group.get(key))
        group[key] = val

    # extract the sorted list of attributes from the
    # grouped (attribute, order) pairs, ordering by
    # the order.
    all_attrs = sorted(group.iteritems(),
        key=lambda x: x[1], reverse=bool(reverse))

    # strip out the sort key in return
    return [x[0] for x in all_attrs]


# the table of geometry dimensions indexed by geometry
# type name. it would be better to use geometry type ID,
# but it seems like that isn't exposed.
#
# each of these is a bit-mask, so zero dimentions is
# represented by 1, one by 2, etc... this is to support
# things like geometry collections where the type isn't
# statically known.
_NULL_DIMENSION         = 0
_POINT_DIMENSION        = 1
_LINE_DIMENSION         = 2
_POLYGON_DIMENSION      = 4


_GEOMETRY_DIMENSIONS = {
    'Point':              _POINT_DIMENSION,
    'LineString':         _LINE_DIMENSION,
    'LinearRing':         _LINE_DIMENSION,
    'Polygon':            _POLYGON_DIMENSION,
    'MultiPoint':         _POINT_DIMENSION,
    'MultiLineString':    _LINE_DIMENSION,
    'MultiPolygon':       _POLYGON_DIMENSION,
    'GeometryCollection': _NULL_DIMENSION,
}


# returns the dimensionality of the object. so points have
# zero dimensions, lines one, polygons two. multi* variants
# have the same as their singular variant.
#
# geometry collections can hold many different types, so
# we use a bit-mask of the dimensions and recurse down to
# find the actual dimensionality of the stored set.
#
# returns a bit-mask, with these bits ORed together:
#   1: contains a point / zero-dimensional object
#   2: contains a linestring / one-dimensional object
#   4: contains a polygon / two-dimensional object
def _geom_dimensions(g):
    dim = _GEOMETRY_DIMENSIONS.get(g.geom_type)
    assert dim is not None, "Unknown geometry type " + \
        "%s in transform._geom_dimensions." % \
        repr(g.geom_type)

    # recurse for geometry collections to find the true
    # dimensionality of the geometry.
    if dim == _NULL_DIMENSION:
        for part in g.geoms:
            dim = dim | _geom_dimensions(part)

    return dim

# creates a list of indexes, each one for a different cut
# attribute value, in priority order.
#
# STRtree stores geometries and returns these from the query,
# but doesn't appear to allow any other attributes to be
# stored along with the geometries. this means we have to
# separate the index out into several "layers", each having
# the same attribute value. which isn't all that much of a
# pain, as we need to cut the shapes in a certain order to
# ensure priority anyway.
#
# intersect_func is a functor passed in to control how an
# intersection is performed. it is passed
class _Cutter:
    def __init__(self, features, attrs, attribute,
                 target_attribute, keep_geom_type,
                 intersect_func):
        group = defaultdict(list)
        for feature in features:
            shape, props, fid = feature
            attr = props.get(attribute)
            group[attr].append(shape)

        # if the user didn't supply any options for controlling
        # the cutting priority, then just make some up based on
        # the attributes which are present in the dataset.
        if attrs is None:
            all_attrs = set()
            for feature in features:
                all_attrs.add(feature[1].get(attribute))
            attrs = list(all_attrs)

        # alternatively, the user can specify an ordering
        # function over the attributes.
        elif isinstance(attrs, dict):
            attrs = _sorted_attributes(features, attrs,
                                       attribute)

        cut_idxs = list()
        for attr in attrs:
            if attr in group:
                cut_idxs.append((attr, STRtree(group[attr])))

        self.attribute = attribute
        self.target_attribute = target_attribute
        self.cut_idxs = cut_idxs
        self.keep_geom_type = keep_geom_type
        self.intersect_func = intersect_func
        self.new_features = []


    # cut up the argument shape, projecting the configured
    # attribute to the properties of the intersecting parts
    # of the shape. adds all the selected bits to the
    # new_features list.
    def cut(self, shape, props, fid):
        original_geom_dim = _geom_dimensions(shape)

        for cutting_attr, cut_idx in self.cut_idxs:
            cutting_shapes = cut_idx.query(shape)

            for cutting_shape in cutting_shapes:
                if cutting_shape.intersects(shape):
                    shape = self._intersect(
                        shape, props, fid, cutting_shape,
                        cutting_attr, original_geom_dim)

                # if there's no geometry left outside the
                # shape, then we can exit the function
                # early, as nothing else will intersect.
                if shape.is_empty:
                    return

        # if there's still geometry left outside, then it
        # keeps the old, unaltered properties.
        self._add(shape, props, fid, original_geom_dim)


    # only keep geometries where either the type is the
    # same as the original, or we're not trying to keep the
    # same type.
    def _add(self, shape, props, fid, original_geom_dim):
        # don't add empty shapes, they're completely
        # useless.
        if shape.is_empty:
            return

        # use a custom dimension measurement here, as it
        # turns out shapely geometry objects don't always
        # form a hierarchy that's usable with isinstance.
        shape_dim = _geom_dimensions(shape)

        # add the shape as-is unless we're trying to keep
        # the geometry type or the geometry dimension is
        # identical.
        if not self.keep_geom_type or \
           shape_dim == original_geom_dim:
            self.new_features.append((shape, props, fid))


    # intersects the shape with the cutting shape and
    # handles attribute projection. anything "inside" is
    # kept as it must have intersected the highest
    # priority cutting shape already. the remainder is
    # returned.
    def _intersect(self, shape, props, fid, cutting_shape,
                   cutting_attr, original_geom_dim):
        inside, outside = \
            self.intersect_func(shape, cutting_shape)

        if cutting_attr is not None:
            inside_props = props.copy()
            inside_props[self.target_attribute] = cutting_attr
        else:
            inside_props = props

        self._add(inside, inside_props, fid,
                  original_geom_dim)
        return outside

# intersect by cutting, so that the cutting shape defines
# a part of the shape which is inside and a part which is
# outside as two separate shapes.
def _intersect_cut(shape, cutting_shape):
    inside = shape.intersection(cutting_shape)
    outside = shape.difference(cutting_shape)
    return inside, outside


# intersect by looking at the overlap size. we can define
# a cut-off fraction and if that fraction or more of the
# area of the shape is within the cutting shape, it's
# inside, else outside.
#
# this is done using a closure so that we can curry away
# the fraction parameter.
def _intersect_overlap(min_fraction):
    # the inner function is what will actually get
    # called, but closing over min_fraction means it
    # will have access to that.
    def _f(shape, cutting_shape):
        overlap = shape.intersection(cutting_shape).area
        area = shape.area

        # need an empty shape of the same type as the
        # original shape, which should be possible, as
        # it seems shapely geometries all have a default
        # constructor to empty.
        empty = type(shape)()

        if ((area > 0) and
            (overlap / area) >= min_fraction):
            return shape, empty
        else:
            return empty, shape
    return _f


# find a layer by iterating through all the layers. this
# would be easier if they layers were in a dict(), but
# that's a pretty invasive change.
#
# returns None if the layer can't be found.
def _find_layer(feature_layers, name):

    for feature_layer in feature_layers:
        layer_datum = feature_layer['layer_datum']
        layer_name = layer_datum['name']

        if layer_name == name:
            return feature_layer

    return None


# shared implementation of the intercut algorithm, used
# both when cutting shapes and using overlap to determine
# inside / outsideness.
def _intercut_impl(intersect_func, feature_layers,
                   base_layer, cutting_layer, attribute,
                   target_attribute, cutting_attrs,
                   keep_geom_type):
    # the target attribute can default to the attribute if
    # they are distinct. but often they aren't, and that's
    # why target_attribute is a separate parameter.
    if target_attribute is None:
        target_attribute = attribute

    # search through all the layers and extract the ones
    # which have the names of the base and cutting layer.
    # it would seem to be better to use a dict() for
    # layers, and this will give odd results if names are
    # allowed to be duplicated.
    base = _find_layer(feature_layers, base_layer)
    cutting = _find_layer(feature_layers, cutting_layer)

    # base or cutting layer not available. this could happen
    # because of a config problem, in which case you'd want
    # it to be reported. but also can happen when the client
    # selects a subset of layers which don't include either
    # the base or the cutting layer. then it's not an error.
    # the interesting case is when they select the base but
    # not the cutting layer...
    if base is None or cutting is None:
        return None

    base_features = base['features']
    cutting_features = cutting['features']

    # make a cutter object to help out
    cutter = _Cutter(cutting_features, cutting_attrs,
                     attribute, target_attribute,
                     keep_geom_type, intersect_func)

    for base_feature in base_features:
        # we use shape to track the current remainder of the
        # shape after subtracting bits which are inside cuts.
        shape, props, fid = base_feature

        cutter.cut(shape, props, fid)

    base['features'] = cutter.new_features

    return base


# intercut takes features from a base layer and cuts each
# of them against a cutting layer, splitting any base
# feature which intersects into separate inside and outside
# parts.
#
# the parts of each base feature which are outside any
# cutting feature are left unchanged. the parts which are
# inside have their property with the key given by the
# 'target_attribute' parameter set to the same value as the
# property from the cutting feature with the key given by
# the 'attribute' parameter.
#
# the intended use of this is to project attributes from one
# layer to another so that they can be styled appropriately.
#
# - feature_layers: list of layers containing both the base
#     and cutting layer.
# - base_layer: str name of the base layer.
# - cutting_layer: str name of the cutting layer.
# - attribute: optional str name of the property / attribute
#     to take from the cutting layer.
# - target_attribute: optional str name of the property /
#     attribute to assign on the base layer. defaults to the
#     same as the 'attribute' parameter.
# - cutting_attrs: list of str, the priority of the values
#     to be used in the cutting operation. this ensures that
#     items at the beginning of the list get cut first and
#     those values have priority (won't be overridden by any
#     other shape cutting).
# - keep_geom_type: if truthy, then filter the output to be
#     the same type as the input. defaults to True, because
#     this seems like an eminently sensible behaviour.
#
# returns a feature layer which is the base layer cut by the
# cutting layer.
def intercut(feature_layers, zoom, base_layer, cutting_layer,
             attribute, target_attribute=None,
             cutting_attrs=None,
             keep_geom_type=True):
    # sanity check on the availability of the cutting
    # attribute.
    assert attribute is not None, \
        'Parameter attribute to intercut was None, but ' + \
        'should have been an attribute name. Perhaps check ' + \
        'your configuration file and queries.'

    return _intercut_impl(_intersect_cut, feature_layers,
        base_layer, cutting_layer, attribute,
        target_attribute, cutting_attrs, keep_geom_type)


# overlap measures the area overlap between each feature in
# the base layer and each in the cutting layer. if the
# fraction of overlap is greater than the min_fraction
# constant, then the feature in the base layer is assigned
# a property with its value derived from the overlapping
# feature from the cutting layer.
#
# the intended use of this is to project attributes from one
# layer to another so that they can be styled appropriately.
#
# it has the same parameters as intercut, see above.
#
# returns a feature layer which is the base layer with
# overlapping features having attributes projected from the
# cutting layer.
def overlap(feature_layers, zoom, base_layer, cutting_layer,
            attribute, target_attribute=None,
            cutting_attrs=None,
            keep_geom_type=True,
            min_fraction=0.8):
    # sanity check on the availability of the cutting
    # attribute.
    assert attribute is not None, \
        'Parameter attribute to overlap was None, but ' + \
        'should have been an attribute name. Perhaps check ' + \
        'your configuration file and queries.'

    return _intercut_impl(_intersect_overlap(min_fraction),
        feature_layers, base_layer, cutting_layer, attribute,
        target_attribute, cutting_attrs, keep_geom_type)


# intracut cuts a layer with a set of features from that same
# layer, which are then removed.
#
# for example, with water boundaries we get one set of linestrings
# from the admin polygons and another set from the original ways
# where the `maritime=yes` tag is set. we don't actually want
# separate linestrings, we just want the `maritime=yes` attribute
# on the first set of linestrings.
def intracut(feature_layers, zoom, base_layer, attribute):
    # sanity check on the availability of the cutting
    # attribute.
    assert attribute is not None, \
        'Parameter attribute to intracut was None, but ' + \
        'should have been an attribute name. Perhaps check ' + \
        'your configuration file and queries.'

    base = _find_layer(feature_layers, base_layer)
    if base is None:
        return None

    # unlike intracut & overlap, which work on separate layers,
    # intracut separates features in the same layer into
    # different sets to work on.
    base_features = list()
    cutting_features = list()
    for shape, props, fid in base['features']:
        if attribute in props:
            cutting_features.append((shape, props, fid))
        else:
            base_features.append((shape, props, fid))

    cutter = _Cutter(cutting_features, None, attribute,
                     attribute, True, _intersect_cut)

    for shape, props, fid in base_features:
        cutter.cut(shape, props, fid)

    base['features'] = cutter.new_features

    return base


# map from old or deprecated kind value to the value that we want
# it to be.
_deprecated_landuse_kinds = {
    'station': 'substation',
    'sub_station': 'substation'
}


def remap_deprecated_landuse_kinds(shape, properties, fid, zoom):
    """
    some landuse kinds are deprecated, or can be coalesced down to
    a single value. this filter implements that by remapping kind
    values.
    """

    original_kind = properties.get('kind')

    if original_kind is not None:
        remapped_kind = _deprecated_landuse_kinds.get(original_kind)

        if remapped_kind is not None:
            properties['kind'] = remapped_kind

    return shape, properties, fid


# explicit order for some kinds of landuse
_landuse_sort_order = {
    'aerodrome': 4,
    'apron': 5,
    'cemetery': 4,
    'commercial': 4,
    'conservation': 2,
    'farm': 3,
    'farmland': 3,
    'forest': 3,
    'generator': 3,
    'golf_course': 4,
    'hospital': 4,
    'nature_reserve': 2,
    'park': 2,
    'parking': 4,
    'pedestrian': 4,
    'place_of_worship': 4,
    'plant': 3,
    'playground': 4,
    'railway': 4,
    'recreation_ground': 4,
    'residential': 1,
    'retail': 4,
    'runway': 5,
    'rural': 1,
    'school': 4,
    'stadium': 3,
    'substation': 4,
    'university': 4,
    'urban': 1,
    'zoo': 4
}


# sets a key "order" on anything with a landuse kind
# specified in the landuse sort order above. this is
# to help with maintaining a consistent order across
# post-processing steps in the server and drawing
# steps on the client.
def landuse_sort_key(shape, properties, fid, zoom):
    kind = properties.get('kind')

    if kind is not None:
        key = _landuse_sort_order.get(kind)
        if key is not None:
            properties['sort_key'] = key

    return shape, properties, fid


# place kinds, as used by OSM, mapped to their rough
# scale_ranks so that we can provide a defaulted,
# non-curated scale_rank / min_zoom value.
_default_scalerank_for_place_kind = {
    'locality': 13,
    'isolated_dwelling': 13,
    'farm': 13,

    'hamlet': 12,
    'neighbourhood': 12,

    'village': 11,

    'suburb': 10,
    'quarter': 10,
    'borough': 10,

    'town': 8,
    'city': 8,

    'province': 4,
    'state': 4,

    'sea': 3,

    'country': 0,
    'ocean': 0,
    'continent': 0
}


# if the feature does not have a scale_rank attribute already,
# which would have come from a curated source, then calculate
# a default one based on the kind of place it is.
def calculate_default_place_scalerank(shape, properties, fid, zoom):
    # don't override an existing attribute
    scalerank = properties.get('scalerank')
    if scalerank is not None:
        return shape, properties, fid

    # base calculation off kind
    kind = properties.get('kind')
    if kind is None:
        return shape, properties, fid

    scalerank = _default_scalerank_for_place_kind.get(kind)
    if scalerank is None:
        return shape, properties, fid

    # adjust scalerank for state / country capitals
    if kind in ('city', 'town'):
        if properties.get('state_capital') == 'yes':
            scalerank -= 1
        elif properties.get('capital') == 'yes':
            scalerank -= 2

    properties['scalerank'] = scalerank

    return shape, properties, fid


def _make_new_properties(props, props_instructions):
    """
    make new properties from existing properties and a
    dict of instructions.

    the algorithm is:
      - where a key appears with value True, it will be
        copied from the existing properties.
      - where it's a dict, the values will be looked up
        in that dict.
      - otherwise the value will be used directly.
    """
    new_props = dict()

    for k, v in props_instructions.iteritems():
        if v is True:
            # this works even when props[k] = None
            if k in props:
                new_props[k] = props[k]
        elif isinstance(v, dict):
            # this will return None, which allows us to
            # use the dict to set default values.
            original_v = props.get(k)
            if original_v in v:
                new_props[k] = v[original_v]
        else:
            new_props[k] = v

    return new_props

def exterior_boundaries(feature_layers, zoom,
                        base_layer,
                        new_layer_name=None,
                        prop_transform=dict(),
                        buffer_size=None,
                        start_zoom=0):
    """
    create new fetures from the boundaries of polygons
    in the base layer, subtracting any sections of the
    boundary which intersect other polygons. this is
    added as a new layer if new_layer_name is not None
    otherwise appended to the base layer.

    the purpose of this is to provide us a shoreline /
    river bank layer from the water layer without having
    any of the shoreline / river bank draw over the top
    of any of the base polygons.

    properties on the lines returned are copied / adapted
    from the existing layer using the new_props dict. see
    _make_new_properties above for the rules.

    buffer_size determines whether any buffering will be
    done to the index polygons. a judiciously small
    amount of buffering can help avoid "dashing" due to
    tolerance in the intersection, but will also create
    small overlaps between lines.

    any features in feature_layers[layer] which aren't
    polygons will be ignored.
    """
    layer = None

    # don't start processing until the start zoom
    if zoom < start_zoom:
        return layer

    # search through all the layers and extract the one
    # which has the name of the base layer we were given
    # as a parameter.
    for feature_layer in feature_layers:
        layer_datum = feature_layer['layer_datum']
        layer_name = layer_datum['name']

        if layer_name == base_layer:
            layer = feature_layer
            break

    # if we failed to find the base layer then it's
    # possible the user just didn't ask for it, so return
    # an empty result.
    if layer is None:
        return None

    features = layer['features']

    # create an index so that we can efficiently find the
    # polygons intersecting the 'current' one. Note that
    # we're only interested in intersecting with other
    # polygonal features, and that intersecting with lines
    # can give some unexpected results.
    indexable_features = list()
    for shape, props, fid in features:
        if shape.geom_type in ('Polygon', 'MultiPolygon'):
            indexable_features.append(shape)
    index = STRtree(indexable_features)

    new_features = list()
    # loop through all the polygons, taking the boundary
    # of each and subtracting any parts which are within
    # other polygons. what remains (if anything) is the
    # new feature.
    for feature in features:
        shape, props, fid = feature

        if shape.geom_type in ('Polygon', 'MultiPolygon'):
            boundary = shape.boundary
            cutting_shapes = index.query(boundary)

            for cutting_shape in cutting_shapes:
                if cutting_shape is not shape:
                    buf = cutting_shape

                    if buffer_size is not None:
                        buf = buf.buffer(buffer_size)

                    boundary = boundary.difference(buf)

            if not boundary.is_empty:
                new_props = _make_new_properties(props,
                    prop_transform)
                new_features.append((boundary, new_props, fid))

    if new_layer_name is None:
        # no new layer requested, instead add new
        # features into the same layer.
        layer['features'].extend(new_features)

        return layer

    else:
        # make a copy of the old layer's information - it
        # shouldn't matter about most of the settings, as
        # post-processing is one of the last operations.
        # but we need to override the name to ensure we get
        # some output.
        new_layer_datum = layer['layer_datum'].copy()
        new_layer_datum['name'] = new_layer_name
        new_layer = layer.copy()
        new_layer['layer_datum'] = new_layer_datum
        new_layer['features'] = new_features
        new_layer['name'] = new_layer_name

        return new_layer


def _inject_key(key, infix):
    """
    OSM keys often have several parts, separated by ':'s.
    When we merge properties from the left and right of a
    boundary, we want to preserve information like the
    left and right names, but prefer the form "name:left"
    rather than "left:name", so we have to insert an
    infix string to these ':'-delimited arrays.

    >>> _inject_key('a:b:c', 'x')
    'a:x:b:c'
    >>> _inject_key('a', 'x')
    'a:x'

    """
    parts = key.split(':')
    parts.insert(1, infix)
    return ':'.join(parts)


def _merge_left_right_props(lprops, rprops):
    """
    Given a set of properties to the left and right of a
    boundary, we want to keep as many of these as possible,
    but keeping them all might be a bit too much.

    So we want to keep the key-value pairs which are the
    same in both in the output, but merge the ones which
    are different by infixing them with 'left' and 'right'.

    >>> _merge_left_right_props({}, {})
    {}
    >>> _merge_left_right_props({'a':1}, {})
    {'a:left': 1}
    >>> _merge_left_right_props({}, {'b':2})
    {'b:right': 2}
    >>> _merge_left_right_props({'a':1, 'c':3}, {'b':2, 'c':3})
    {'a:left': 1, 'c': 3, 'b:right': 2}
    >>> _merge_left_right_props({'a':1},{'a':2})
    {'a:left': 1, 'a:right': 2}
    """
    keys = set(lprops.keys()) | set(rprops.keys())
    new_props = dict()

    # props in both are copied directly if they're the same
    # in both the left and right. they get left/right
    # inserted after the first ':' if they're different.
    for k in keys:
        lv = lprops.get(k)
        rv = rprops.get(k)

        if lv == rv:
            new_props[k] = lv
        else:
            if lv is not None:
                new_props[_inject_key(k, 'left')] = lv
            if rv is not None:
                new_props[_inject_key(k, 'right')] = rv

    return new_props


def _make_joined_name(props):
    """
    Updates the argument to contain a 'name' element
    generated from joining the left and right names.

    Just to make it easier for people, we generate a name
    which is easy to display of the form "LEFT - RIGHT".
    The individual properties are available if the user
    wants to generate a more complex name.

    >>> x = {}
    >>> _make_joined_name(x)
    >>> x
    {}

    >>> x = {'name:left':'Left'}
    >>> _make_joined_name(x)
    >>> x
    {'name': 'Left', 'name:left': 'Left'}

    >>> x = {'name:right':'Right'}
    >>> _make_joined_name(x)
    >>> x
    {'name': 'Right', 'name:right': 'Right'}

    >>> x = {'name:left':'Left', 'name:right':'Right'}
    >>> _make_joined_name(x)
    >>> x
    {'name:right': 'Right', 'name': 'Left - Right', 'name:left': 'Left'}

    >>> x = {'name:left':'Left', 'name:right':'Right', 'name': 'Already Exists'}
    >>> _make_joined_name(x)
    >>> x
    {'name:right': 'Right', 'name': 'Already Exists', 'name:left': 'Left'}
    """

    # don't overwrite an existing name
    if 'name' in props:
        return

    lname = props.get('name:left')
    rname = props.get('name:right')

    if lname is not None:
        if rname is not None:
            props['name'] = "%s - %s" % (lname, rname)
        else:
            props['name'] = lname
    elif rname is not None:
        props['name'] = rname


def _linemerge(geom):
    """
    Try to extract all the linear features from the geometry argument
    and merge them all together into the smallest set of linestrings
    possible.

    This is almost identical to Shapely's linemerge, and uses it,
    except that Shapely's throws exceptions when passed a single
    linestring, or a geometry collection with lines and points in it.
    So this can be thought of as a "safer" wrapper around Shapely's
    function.
    """
    geom_type = geom.type

    if geom_type == 'GeometryCollection':
        # collect together everything line-like from the geometry
        # collection and filter out anything that's empty
        lines = []
        for line in g.geoms:
            line = _linemerge(line)
            if not line.is_empty:
                lines.append(line)

        return linemerge(lines) if lines else MultiLineString([])

    elif geom_type == 'LineString':
        return geom

    elif geom_type == 'MultiLineString':
        return linemerge(geom)

    else:
        return MultiLineString([])


def admin_boundaries(feature_layers, zoom, base_layer,
                     start_zoom=0):
    """
    Given a layer with admin polygons and maritime boundaries,
    attempts to output a set of oriented boundaries with properties
    from both the left and right polygon, and also cut with the
    maritime information to provide a `maritime_boundary=yes` value
    where there's overlap between the maritime lines and the
    polygon boundaries.
    """

    layer = None

    # don't start processing until the start zoom
    if zoom < start_zoom:
        return layer

    layer = _find_layer(feature_layers, base_layer)
    if layer is None:
        return None

    # layer will have polygonal features for the admin
    # polygons and also linear features for the maritime
    # boundaries. further, we want to group the admin
    # polygons by their kind, as this will reduce the
    # working set.
    admin_features = defaultdict(list)
    maritime_features = list()
    new_features = list()

    for shape, props, fid in layer['features']:
        dims = _geom_dimensions(shape)
        kind = props.get('kind')
        maritime_boundary = props.get('maritime_boundary')

        # the reason to use this rather than compare the
        # string of types is to catch the "multi-" types
        # as well.
        if dims == _POLYGON_DIMENSION and kind is not None:
            admin_features[kind].append((shape, props, fid))

        elif dims == _POLYGON_DIMENSION and maritime_boundary == 'yes':
            maritime_features.append((shape, {'maritime_boundary':'no'}, 0))

    # there are separate polygons for each admin level, and
    # we only want to intersect like with like because it
    # makes more sense to have Country-Country and
    # State-State boundaries (and labels) rather than the
    # (combinatoric) set of all different levels.
    for kind, features in admin_features.iteritems():
        num_features = len(features)
        envelopes = [g[0].envelope for g in features]

        for i, feature in enumerate(features):
            shape, props, fid = feature
            envelope = envelopes[i]

            # orient to ensure that the shape is to the
            # left of the boundary.
            boundary = orient(shape).boundary

            # intersect with *preceding* features to remove
            # those boundary parts. this ensures that there
            # are no duplicate parts.
            for j in range(0, i):
                cut_shape, cut_props, cut_fid = features[j]
                cut_envelope = envelopes[j]
                if envelope.intersects(cut_envelope):
                    boundary = boundary.difference(cut_shape)

                if boundary.is_empty:
                    break

            # intersect with every *later* feature. now each
            # intersection represents a section of boundary
            # that we want to keep.
            for j in range(i+1, num_features):
                cut_shape, cut_props, cut_fid = features[j]
                cut_envelope = envelopes[j]

                if envelope.intersects(cut_envelope):
                    inside, boundary = _intersect_cut(boundary, cut_shape)

                    inside = _linemerge(inside)
                    if not inside.is_empty:
                        new_props = _merge_left_right_props(props, cut_props)
                        new_props['id'] = props['id']
                        _make_joined_name(new_props)
                        new_features.append((inside, new_props, fid))

                if boundary.is_empty:
                    break

            # anything left over at the end is still a boundary,
            # but a one-sided boundary to international waters.
            boundary = _linemerge(boundary)
            if not boundary.is_empty:
                new_props = props.copy()
                _make_joined_name(new_props)
                new_features.append((boundary, new_props, fid))


    # use intracut for maritime, but it intersects in a positive
    # way - it sets the tag on anything which intersects, whereas
    # we want to set maritime where it _doesn't_ intersect. so
    # we have to flip the attribute afterwards.
    cutter = _Cutter(maritime_features, None,
                     'maritime_boundary', 'maritime_boundary',
                     _LINE_DIMENSION, _intersect_cut)

    for shape, props, fid in new_features:
        cutter.cut(shape, props, fid)

    # flip the property, so define maritime_boundary=yes where
    # it was previously unset and remove maritime_boundary=no.
    for shape, props, fid in cutter.new_features:
        maritime_boundary = props.pop('maritime_boundary', None)
        if maritime_boundary is None:
            props['maritime_boundary'] = 'yes'

    layer['features'] = cutter.new_features
    return layer


def generate_label_features(
        feature_layers, zoom, source_layer=None, label_property_name=None,
        label_property_value=None, new_layer_name=None):

    assert source_layer, 'generate_label_features: missing source_layer'

    layer = _find_layer(feature_layers, source_layer)
    if layer is None:
        return None

    new_features = []
    for feature in layer['features']:
        shape, properties, fid = feature

        # We only want to create label features for polygonal
        # geometries
        if shape.geom_type not in ('Polygon', 'MultiPolygon'):
            continue

        # shapely also has a function `representative_point` which we
        # might want to consider using here
        label_centroid = shape.centroid
        label_properties = properties.copy()
        if label_property_name:
            label_properties[label_property_name] = label_property_value
        label_feature = label_centroid, label_properties, fid

        # if we're adding these features to a new layer, don't add the
        # original features
        if new_layer_name is None:
            new_features.append(feature)
        new_features.append(label_feature)

    if new_layer_name is None:
        layer['features'] = new_features
        return layer
    else:
        label_layer_datum = layer['layer_datum'].copy()
        label_layer_datum['name'] = new_layer_name
        label_feature_layer = dict(
            name=new_layer_name,
            features=new_features,
            layer_datum=label_layer_datum,
        )
        return label_feature_layer
