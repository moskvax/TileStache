# sort functions to apply to features


def _sort_features_by_key(features, key):
    features.sort(key=key)
    return features


def _by_feature_property(property_name):
    def _feature_sort_by_property(feature):
        wkb, properties, fid = feature
        return properties.get(property_name)
    return _feature_sort_by_property


_by_feature_id = _by_feature_property('id')


def _sort_by_area_then_id(features):
    features.sort(key=_by_feature_id)
    features.sort(key=_by_feature_property('area'), reverse=True)
    return features


def _by_scalerank(feature):
    wkb, properties, fid = feature
    value_for_none = 1000
    scalerank = properties.get('scalerank', value_for_none)
    return scalerank


def _by_population(feature):
    wkb, properties, fid = feature
    value_for_none = -1000
    population = int(properties.get('population', value_for_none))
    return population


# place kinds, as used by OSM and NE, mapped to their rough
# priority values so that places can be sorted into a decent
# enough draw order on the server.
_place_sort_order = {
    # zoom >= 13
    'locality': 1302,
    'isolated_dwelling': 1301,
    'farm': 1300,

    # zoom >= 12
    'hamlet': 1201,
    'neighbourhood': 1200,

    # zoom >= 11
    'village': 1100,

    # zoom >= 10
    'suburb': 1002,
    'quarter': 1001,
    'borough': 1000,

    # zoom >= 8
    # note: these have 50 added, so that some can be
    # taken away for capitals & state capitals.
    'town': 851,
    'Populated place': 851,
    'city': 850,
    'Admin-0 capital': 850,
    'Admin-1 capital': 850,

    # zoom >= 4
    'province': 401,
    'state': 400,

    # zoom >= 3
    'sea': 300,

    # always on
    'country': 102,
    'ocean': 101,
    'continent': 100,

# these have a relatively significant level of use in
# OSM, but aren't currently selected by the query.
# perhaps we should be using these too?
#    'island': 0,
#    'islet': 0,
#    'county': 0,
#    'city_block': 0,
#    'region': 0,
#    'municipality': 0,
#    'subdistrict': 0,
#    'township': 0,
#    'archipelago': 0,
#    'country': 0,
#    'district': 0,
#    'block': 0,
#    'department': 0,
}


def _by_place_kind(feature):
    wkb, properties, fid = feature

    kind = properties.get('kind')
    state_capital = properties.get('state_capital')
    capital = properties.get('capital')

    order = _place_sort_order.get(kind, 9999)

    # hmm... seems like a nasty little hack to get
    # state capital status to be taken into account...
    if capital == 'yes':
        order -= 50
    elif state_capital == 'yes':
        order -= 20

    return order


def _sort_by_place_kind_then_population(features):
    features.sort(key=_by_population, reverse=True)
    features.sort(key=_by_place_kind)
    return features


def buildings(features, zoom):
    return _sort_by_area_then_id(features)


def earth(features, zoom):
    return _sort_features_by_key(features, _by_feature_id)


def landuse(features, zoom):
    return _sort_by_area_then_id(features)


def places(features, zoom):
    return _sort_by_place_kind_then_population(features)


def pois(features, zoom):
    return _sort_features_by_key(features, _by_feature_id)


def roads(features, zoom):
    return _sort_features_by_key(features, _by_feature_property('sort_key'))


def water(features, zoom):
    return _sort_by_area_then_id(features)


def transit(features, zoom):
    return _sort_features_by_key(features, _by_feature_id)
