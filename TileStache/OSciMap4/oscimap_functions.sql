
CREATE OR REPLACE FUNCTION map.scaletotile(tilex bigint, tiley bigint, tilez integer, geom geometry)
  RETURNS geometry AS
$BODY$
DECLARE
bbox geometry;
x double precision;
y double precision;
w double precision;
h double precision;
BEGIN
	-- tile to bounding box
	bbox := map.ttb(tileX, tileY, tileZ, 0);
	
	x = st_xmin(bbox);
	y = st_ymin(bbox);
	w = 4096 / (st_xmax(bbox) - x); 
	h = 4096 / (st_ymax(bbox) - y);

	return ST_TransScale(geom, -x, -y, w, h);

END;
$BODY$
  LANGUAGE plpgsql IMMUTABLE;


CREATE OR REPLACE FUNCTION map.ttb(tilex bigint, tiley bigint, tilez integer, pixel integer DEFAULT 0, clip boolean DEFAULT false)
  RETURNS geometry AS
$BODY$
DECLARE
scaleFactor double precision = 20037508.342789244;
size integer = 256;
minLon double precision;
maxLon double precision;
minLat double precision;
maxLat double precision;
center double precision;
BEGIN
	tileX := tileX * size;
	tileY := tileY * size;
	center := (size << tileZ) >> 1;
		
	minLat := ((center - (tileY + size + pixel)) / center) * scaleFactor;
	maxLat := ((center - (tileY - pixel)) / center) * scaleFactor;

	minLon := (((tileX - pixel) - center) / center) * scaleFactor;
	maxLon := (((tileX + size + pixel) - center) / center) * scaleFactor;

	if clip then
		-- this prevents a rendering issue on low zoom-levels, need to investigate..
		scaleFactor := 20037500;
		
		-- limit to max coordinate range:
		minLon := least(minLon, scaleFactor);
		minLon :=  greatest(minLon, -scaleFactor);

		maxLon := least(maxLon, scaleFactor);
		maxLon :=  greatest(maxLon, -scaleFactor);

		minLat := least(minLat, scaleFactor);
		minLat :=  greatest(minLat, -scaleFactor);

		maxLat := least(maxLat, scaleFactor);
		maxLat :=  greatest(maxLat, -scaleFactor);
	end if;
	
	RETURN ST_MakeEnvelope(minLon, minLat, maxLon, maxLat, 3857);	
	
END;
$BODY$
LANGUAGE plpgsql IMMUTABLE;

-- pixel at zoom-level for tiles rendered at 256px
CREATE OR REPLACE FUNCTION map.paz(zoom integer)
  RETURNS double precision AS
$BODY$
 SELECT 20037508.342789244 / 256 / (2 ^ $1)
$BODY$
LANGUAGE sql IMMUTABLE;


GRANT EXECUTE ON FUNCTION map.scaletotile(bigint, bigint, integer, geometry) TO public;
GRANT EXECUTE ON FUNCTION map.ttb(bigint, bigint, integer, integer, boolean) TO public;
GRANT EXECUTE ON FUNCTION map.paz(integer) TO public;

