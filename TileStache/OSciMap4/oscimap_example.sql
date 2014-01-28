CREATE OR REPLACE FUNCTION map.get_tile(IN x bigint, IN y bigint, IN zoom integer, IN cache boolean default false)
  RETURNS TABLE(tags hstore, geom bytea) AS
$BODY$
declare
bbox geometry;
pixel double precision;
begin
bbox := map.ttb(x,y,zoom, 2);
pixel := map.paz(zoom);

return query
	SELECT
		(
			hstore('name', g.name) ||
			hstore('highway', g.highway)
		) AS tags,
		ST_AsEWKB(map.scaletotile(x, y, zoom, ST_SimplifyPreserveTopology(ST_Intersection(g.way, bbox), pixel)))
	FROM
		planet_osm_line AS g
	WHERE
		g.way && bbox AND
		g.highway IS NOT NULL;
return query
	SELECT
		(
			hstore('name', g.name) ||
			hstore('building', g.building) ||
			hstore('leisure', g.leisure)
		) AS tags,
		ST_AsEWKB(map.scaletotile(x, y, zoom, ST_SimplifyPreserveTopology(ST_Intersection(g.way, bbox), pixel)))
	FROM
		planet_osm_polygon AS g
	WHERE
		g.way && bbox AND
		(
			g.building IS NOT NULL OR
			g.leisure IS NOT NULL
		);

end;
$BODY$
LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION map.get_tile_poi(IN x bigint, IN y bigint, IN zoom integer)
  RETURNS TABLE(tags hstore, geom bytea) AS
$BODY$
declare
bbox geometry;
begin

bbox := map.ttb(x,y,zoom, 0);

return query select t, st_asewkb(map.scaletotile(x, y, zoom, g)) from 
	(select (hstore('name', p.name) || hstore('rank', scalerank::text) || 'place=>city'::hstore) t, 
			p.wkb_geometry g, pop_max population
		from ne_10m_populated_places p 
		where p.wkb_geometry && bbox and scalerank <= zoom 
		order by population desc limit 30
	) p order by population asc;

end;
$BODY$
language plpgsql;
