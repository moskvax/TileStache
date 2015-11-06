FROM ubuntu:14.04
MAINTAINER Stephen Caraher <moskvax@gmail.com>

RUN echo "deb http://ppa.launchpad.net/mapnik/nightly-2.3/ubuntu trusty main">>/etc/apt/sources.list && \
    apt-key adv --recv-keys --keyserver keyserver.ubuntu.com 4F7B93595D50B6BA

RUN apt-get update && apt-get install -y \
      libmapnik-dev \
      libgdal-dev \
      libgeos-dev \
      python-mapnik \
      python-pip \
      node-mapnik \
      nodejs-legacy \
      npm \
      gcc \
      --no-install-recommends

RUN pip install -U pillow modestmaps werkzeug mapbox-vector-tile shapely psycopg2

ADD . /usr/src/app/
WORKDIR /usr/src/app
RUN python setup.py install

EXPOSE 8080
CMD ["./scripts/tilestache-server.py", "-i", "0.0.0.0"]
