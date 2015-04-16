# transformation functions to apply to features

from shapely import wkb
import md5
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


def normalize_osm_id(shape, properties, fid):
    if fid < 0:
        properties['osm_id'] = -fid
        properties['osm_relation'] = True
        # preserve previous behavior and use the first 10 digits of
        # the md5 sum for the id on negative ids
        binary = wkb.dumps(shape)
        fid = md5.new(binary).hexdigest()[:10]
    else:
        # always use a string id
        fid = str(fid)
    return shape, properties, fid


def building_kind(shape, properties, fid):
    building = _coalesce(properties, 'building:part', 'building')
    if building and building != 'yes':
        kind = building
    else:
        kind = _coalesce(properties, 'amenity', 'shop', 'tourism')
    if kind:
        properties['kind'] = kind
    return shape, properties, fid


def building_height(shape, properties, fid):
    height = _building_calc_height(
        properties.get('height'), properties.get('building:levels'),
        _building_calc_levels)
    if height is not None:
        properties['height'] = height
    else:
        properties.pop('height', None)
    return shape, properties, fid


def building_min_height(shape, properties, fid):
    min_height = _building_calc_height(
        properties.get('min_height'), properties.get('building:min_levels'),
        _building_calc_min_levels)
    if min_height is not None:
        properties['min_height'] = min_height
    else:
        properties.pop('min_height', None)
    return shape, properties, fid


def building_trim_properties(shape, properties, fid):
    properties = _remove_properties(
        properties,
        'amenity', 'shop', 'tourism',
        'building', 'building:part',
        'building:levels', 'building:min_levels')
    return shape, properties, fid


def road_kind(shape, properties, fid):
    properties['kind'] = _road_kind(properties)
    return shape, properties, fid


def road_classifier(shape, properties, fid):
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


def road_sort_key(shape, properties, fid):
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
    elif highway in ('residential', 'unclassified', 'road'):
        sort_val += 17
    elif highway in ('unclassified', 'service', 'minor'):
        sort_val += 16
    else:
        sort_val += 15

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


def road_trim_properties(shape, properties, fid):
    properties = _remove_properties(properties, 'bridge', 'layer', 'tunnel')
    return shape, properties, fid
