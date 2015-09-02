# transformation functions to apply to features

from numbers import Number
from StreetNames import short_street_name
import re


def _to_float(x):
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

    as_float = _to_float(x)
    if as_float is not None:
        return as_float

    # trim whitespace to simplify further matching
    x = x.strip()

    # try explicit meters suffix
    if x.endswith(' m'):
        meters_as_float = _to_float(x[:-2])
        if meters_as_float is not None:
            return meters_as_float

    # try if it looks like an expression in feet via ' "
    feet_match = feet_pattern.match(x)
    if feet_match is not None:
        feet = feet_match.group(1)
        inches = feet_match.group(2)
        feet_as_float = _to_float(feet)
        inches_as_float = _to_float(inches)

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
        as_float = _to_float(potential_number)
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
            layer_float = _to_float(layer)
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
                k.startswith('old_name:') and v != name):
            properties[k] = v

    for alt_tag_name_candidate in tag_name_alternates:
        alt_tag_name_value = tags.get(alt_tag_name_candidate)
        if alt_tag_name_value and alt_tag_name_value != name:
            properties[alt_tag_name_candidate] = alt_tag_name_value

    return shape, properties, fid

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
# returns a set of feature layers with the base layer
# replaced by a cut one, or None if there's an error.
def intercut(feature_layers, base_layer, cutting_layer, attribute=None, target_attribute=None):
    base = None
    cutting = None

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
    for feature_layer in feature_layers:
        layer_datum = feature_layer['layer_datum']
        layer_name = layer_datum['name']

        if layer_name == base_layer:
            base = feature_layer
        elif layer_name == cutting_layer:
            cutting = feature_layer

    # didn't find one or other layer - what's the appropriate
    # thing to do here, raise an error?
    if base is None or cutting is None:
        return None

    base_features = base['features']
    cutting_features = cutting['features']

    # TODO: this is a very simple way of doing this, and would
    # probably be better replaced by something that isn't O(N^2)
    # and perhaps even unioned features with the same attribute
    # together first.
    for cutting_feature in cutting_features:
        cutting_shape, cutting_props, cutting_id = cutting_feature
        cutting_attr = None
        if attribute is not None and attribute in cutting_props:
            cutting_attr = cutting_props[attribute]

        new_features = []
        for index, base_feature in enumerate(base_features):
            base_shape, base_props, base_id = base_feature

            if base_shape.intersects(cutting_shape):
                inside = base_shape.intersection(cutting_shape)
                outside = base_shape.difference(cutting_shape)

                if cutting_attr is not None:
                    inside_props = base_props.copy()
                    inside_props[target_attribute] = cutting_attr
                else:
                    inside_props = base_props

                new_features.append((inside, inside_props, base_id))

                if not outside.is_empty:
                    new_features.append((outside, base_props, base_id))

            else:
                new_features.append(base_feature)

        base_features = new_features

    base['features'] = base_features

    return base
