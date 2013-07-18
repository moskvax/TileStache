Prerequisites:
- Install Postgresql, PostGIS, TileStache, python-psycopg2 and python-protobuf
- Add postgres user 'osm' with password 'osm' (or change example.cfg)

Set up the database:
--------------------

createdb oscimap

psql -d oscimap
create extension postgis;
create extension hstore;
create schema map;
grant all on schema map to public;
\q

psql -d oscimap -f TileStache/OSciMap4/oscimap_functions.sql
psql -d oscimap -f TileStache/OSciMap4/oscimap_example.sql

Import some data:
-----------------
wget "http://www.naturalearthdata.com/http//www.naturalearthdata.com/download/50m/physical/ne_50m_ocean.zip"
unzip ne_50m_ocean.zip
ogr2ogr -f "PostgreSQL" PG:"dbname=oscimap" -nlt multipolygon -clipsrc -180 -85.5 180 85.5  -t_srs EPSG:3857 ne_50m_ocean.shp

wget "http://www.naturalearthdata.com/http//www.naturalearthdata.com/download/10m/cultural/ne_10m_populated_places_simple.zip"
unzip ne_10m_populated_places_simple.zip
ogr2ogr -f "PostgreSQL" PG:"dbname=oscimap" -nln ne_10m_populated_places -clipsrc -180 -85.5 180 85.5  -t_srs EPSG:3857 ne_10m_populated_places_simple.shp 

psql -d oscimap
GRANT SELECT ON ALL TABLES IN SCHEMA public TO public;
\q

Testing the Tile-Server:
------------------------
(in TileStache directory)
export PYTHONPATH=.
./scripts/tilestache-server.py -c TileStache/OSciMap4/example.cfg -p 8888

wget localhost:8888/example/0/0/0.vtm

If everything works, change your VectorTileMap app to point to your test server. 

'''
TileSource tileSource = new OSciMap4TileSource();
tileSource.setOption("url", "http://city.informatik.uni-bremen.de/osci/example");
'''

See TileStache documentation for available options to integrate with apache, nginx, etc 

