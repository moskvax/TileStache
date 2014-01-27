#!/bin/bash
export PGPASSWORD=
export RDSINSTANCE=localhost
PGOPTS="-d postgres -h $RDSINSTANCE -U postgres"

# water polygons
#
wget http://data.openstreetmapdata.com/water-polygons-split-3857.zip
unzip water-polygons-split-3857.zip
shp2pgsql -dID -s 900913 -W Windows-1252 -g the_geom water-polygons-split-3857/water_polygons.shp water_polygons | psql $PGOPTS
rm ./water-polygons-split-3857.zip && rm -rf ./water-polygons-split-3857

# land polygons
#
wget http://data.openstreetmapdata.com/land-polygons-split-3857.zip
unzip land-polygons-split-3857.zip
shp2pgsql -dID -s 900913 -W Windows-1252 -g the_geom land-polygons-split-3857/land_polygons.shp land_polygons | psql $PGOPTS
rm ./land-polygons-split-3857.zip && rm -rf ./land-polygons-split-3857

# simplified land polygons
#
wget http://data.openstreetmapdata.com/simplified-land-polygons-complete-3857.zip
unzip simplified-land-polygons-complete-3857.zip
shp2pgsql -dID -s 900913 -W Windows-1252 -g the_geom simplified-land-polygons-complete-3857/simplified_land_polygons.shp simplified_land_polygons | psql $PGOPTS
rm ./simplified-land-polygons-complete-3857.zip && rm -rf ./simplified-land-polygons-complete-3857

# highroad
#
git clone https://github.com/migurski/HighRoad.git
psql -f HighRoad/high_road_views-setup.pgsql $PGOPTS
rm -rf ./HighRoad

# skeletron
#
wget https://s3.amazonaws.com/mapzen.skeletron/streets.zip
unzip streets.zip
shp2pgsql -dID -s 900913 -W Latin1 -g way streets.shp streets_skeletron | psql $PGOPTS
rm ./streets.*

# vector data
#
git clone git@github.com:mapzen/vector-datasource.git
cd vector-datasource
cd data
unzip land-usages-naturalearth.zip
unzip water-areas-naturalearth.zip
./shp2pgsql.sh | psql $PGOPTS
cd ..
rm -rf ./vector-datasource