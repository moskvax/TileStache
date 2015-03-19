# transformation functions to apply to features


def normalize_osm_id(shape, properties, fid):
    osm_id = properties.get('osm_id')
    if osm_id is None:
        return shape, properties, fid
    try:
        int_osm_id = int(osm_id)
    except ValueError:
        return shape, properties, fid
    else:
        if int_osm_id < 0:
            properties['osm_id'] = -int_osm_id
            properties['osm_relation'] = True
        else:
            properties['osm_id'] = int_osm_id
        return shape, properties, fid
