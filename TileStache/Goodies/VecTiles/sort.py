# sort functions to apply to features

from transform import _to_float


def _sort_features_by_key(features, key):
    features.sort(key=key)
    return features


def _place_key(feature):
    wkb, properties, fid = feature
    admin_level = properties.get('admin_level')
    admin_level_float = _to_float(admin_level)
    if admin_level_float is None:
        return 1000.0
    return admin_level


def _by_feature_id(feature):
    wkb, properties, fid = feature
    return fid


def _by_area(feature):
    wkb, properties, fid = feature
    return properties.get('area')


def _sort_by_area_then_id(features):
    features.sort(key=_by_feature_id)
    features.sort(key=_by_area, reverse=True)
    return features


def _road_key(feature):
    wkb, properties, fid = feature
    return properties.get('sort_key')


def buildings(features):
    return _sort_by_area_then_id(features)


def earth(features):
    return _sort_features_by_key(features, _by_feature_id)


def landuse(features):
    return _sort_by_area_then_id(features)


def places(features):
    return _sort_features_by_key(features, _place_key)


def pois(features):
    return _sort_features_by_key(features, _by_feature_id)


def roads(features):
    return _sort_features_by_key(features, _road_key)


def water(features):
    return _sort_by_area_then_id(features)
