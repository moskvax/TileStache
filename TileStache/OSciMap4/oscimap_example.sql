CREATE OR REPLACE FUNCTION map.get_tile(IN x bigint, IN y bigint, IN zoom integer, IN cache boolean default false)
  RETURNS TABLE(tags hstore, geom bytea) AS
$BODY$
declare
bbox geometry;
pixel double precision;
begin
bbox := map.ttb(x,y,zoom, 2);
pixel := map.paz(zoom);

-- simplify geometry with 'pixel' tolerance and tranlate and scale to tile coordinates (0-4096)
return query select 'natural=>water'::hstore, st_asewkb(map.scaletotile(x, y, zoom, st_simplifypreservetopology(g, pixel))) 
	-- clip to intersection of tile bounding box, 
	-- dump geometry collections and make sure the results are polygons
	from (select st_buffer((st_dump(st_intersection(wkb_geometry, bbox))).geom, 0) g 
		from ne_50m_ocean 
		where wkb_geometry && bbox) p
	where st_dimension(g) = 2;
	
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
