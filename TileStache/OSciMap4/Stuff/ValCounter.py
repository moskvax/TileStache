'''
Created on Aug 13, 2012

@author: jeff
'''

import sqlite3 as lite
import sys


try:
    con = lite.connect('/home/jeff/taginfo-db.db')

    cur = con.cursor()  

    #cur.execute('''SELECT key, value, count_all  FROM tags WHERE count_all > 5000 and key not like 'tiger%' and not key like 'addr%' and not key like '3dshapes%'  and not key like 'kms%' and key not in ('note', 'source', 'comment') and not key like 'osak%' order by key, count_all ''')
    #cur.execute('''select key, c from (SELECT key, sum(count_all) as c  FROM tags WHERE count_all > 1000 group by key)p order by c desc limit 256''')
    
#    cur.execute('''select value, c from (SELECT value, sum(count_all) as c  FROM tags WHERE count_all > 100 and key in ('natural', 'waterway', 'surface', 'oneway', 
#                    'tunnel', 'service', 'railway', 'shop', 'place', 'boundary', 'admin_level', 'aeroway', 'amenity', 'access', 'abutters', 
#                    'barrier', 'bench', 'bicycle', 'bridge', 'building', 'entrance', 'highway', 'landuse', 'leisure', 'man_made', 'route', 'tourism', 
#                    'tracktype', 'wetland', 'wood', 'wheelchair')group by value)p order by c desc limit 256''')
#    
    cur.execute('''SELECT key, count_all from keys where count_all > 50000 and 
         not (key like 'tiger:%' or 
         key like 'note:%' or
         key like 'gnis:%' or
         key like '3dshapes:%' or
         key like 'kms:%' or
         key like 'yh:%' or
         key like 'KSJ2:%' or
         key like 'NHD:%' or
         key like 'LINZ:%' or
         key like 'AND:%' or
         key like 'CLC:%' or
         key like 'canvec:%' or
         key like 'project:%' or
         key like 'geobase:%' or 
         key like 'gnis:%' or
         key like 'osak:%' or
         key like 'ngbe:%' or
         key = 'AND_nosr_r' or
         key like 'it:%' or
         key = 'FIXME' or
         key like 'fresno_%' or
         key = 'NHS' or
         key = 'WroclawGIS:%' or
         key = 'massgis:%' 
        )order by count_all desc''')
    
#                    not in ('name', 'addr:housenumber', 'addr:street', 'addr:city', 
#                    'wall','power','is_in','lanes','maxspeed', 'ref', 'type','foot','layer','ele', 'source','natural', 'waterway', 'surface', 'oneway', 
#                    'tunnel', 'service', 'railway', 'shop', 'place', 'boundary', 'admin_level', 'aeroway', 'amenity', 'access', 'abutters', 
#                    'barrier', 'bench', 'bicycle', 'bridge', 'building', 'entrance', 'highway', 'landuse', 'leisure', 'man_made', 'route', 'tourism', 
#                    'tracktype', 'wetland', 'wood', 'wheelchair') order by count_all desc''')
    rows = cur.fetchall()
    
    cnt = 0    
    for row in rows:
        #print '"%s" : %d,' %(row[0].encode('utf-8'), row[1])
        #print '"%s" : %d,' %(row[0].encode('utf-8'), cnt)
        print '"%s %d",' %(row[0].encode('utf-8'), row[1])
        ##print 'node/way\t%s\ttext delete # %d' %(row[0].encode('utf-8'), row[1])
        cnt += 1
        
    print len(rows)

except lite.Error, e:
    if con:
        con.rollback()
    print "Error %s:" % e.args[0]
    sys.exit(1)
finally:
    if con:
        con.close() 
        
        
