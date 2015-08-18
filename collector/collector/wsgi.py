from flask import Flask, Response, request, jsonify
from sqlalchemy import create_engine, select, text, MetaData, Table, String, Integer, BigInteger, Boolean, Column, DateTime, String, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from geoalchemy2 import Geometry
from geoalchemy2.functions import ST_X, ST_Y
import ipaddress
import datetime

app = Flask(__name__)

if not app.debug:
    import logging
    import logging.handlers
    handler = logging.handlers.RotatingFileHandler("/var/log/piecewise/collector.log", maxBytes = 10 * 1000 * 1000, backupCount = 5)
    handler.setLevel(logging.WARNING)
    app.logger.addHandler(handler)

db_engine = create_engine("postgresql+psycopg2://postgres:@/piecewise")
Base = declarative_base()
Session = sessionmaker(bind=db_engine)
db_session = Session()

metadata = MetaData()
metadata.bind = db_engine
extra_data = Table('extra_data', metadata, 
    Column('id', Integer, primary_key = True),
    Column('timestamp', DateTime),
    Column('verified', Boolean),
    Column('bigquery_key', String),
    Column('location', Geometry("Point", srid=4326)),
    Column('connection_type', String),
    Column('advertised_download', Integer),
    Column('advertised_upload', Integer),
    Column('location_type', String),
    Column('cost_of_service', Integer))
metadata.create_all()

class ExtraData(Base):
    __tablename__ = 'extra_data'
    id = Column('id', Integer, primary_key = True)
    timestamp = Column('timestamp', DateTime)
    verified = Column('verified', Boolean)
    bigquery_key = Column('bigquery_key', String)
    location = Column('location', Geometry("Point", srid=4326))
    connection_type = Column('connection_type', String)
    advertised_download = Column('advertised_download', Integer)
    advertised_upload = Column('advertised_upload', Integer)
    location_type = Column('location_type', String)
    cost_of_service = Column('cost_of_service', Integer)

@app.route("/unverify", methods=['GET'])
def unverify_extra_data():
    if not request.args.get('id'):
        return ('', 400, {})

    try:
        result = db_session.query(ExtraData).filter_by(
            id=request.args.get('id')).update({"verified": "f"})
        db_session.commit()
    except:
        db_session.rollback()

    if result:
        return ('', 200, {})
    else:
        return ('', 500, {})


@app.route("/verify", methods=['GET'])
def verify_extra_data():
    if not request.args.get('id'):
        return ('', 400, {})

    try:
        result = db_session.query(ExtraData).filter_by(
            id=request.args.get('id')).update({"verified": "t"})
        db_session.commit()
    except:
        db_session.rollback()

    if result:
        return ('', 200, {})
    else:
        return ('', 500, {})

@app.route("/retrieve", methods=['GET'])
def retrieve_extra_data():
    if request.args.get('limit'):
       limit = int(request.args.get('limit'))
    else:
        limit = 50

    if request.args.get('page'):
        offset = (int(request.args.get('page')) - 1) * limit
    else:
        offset = 0

    order_by = ExtraData.id.desc()
    sort_fields = ['id', 'timestamp', 'advertised_download', 'advertised_upload',
            'cost_of_service', 'location_type', 'connection_type', 'verified']

    if request.args.get('sort'):
        if request.args.get('sort') in sort_fields:
            if request.args.get('order'):
                if request.args.get('order') in ['desc', 'asc']:
                    order_by = eval('ExtraData.%s.%s()' % (request.args.get('sort'),\
                            request.args.get('order')), {"__builtins__": None},\
                            {"ExtraData": ExtraData})
                else:
                    order_by = eval('ExtraData.%s.%s()' % (request.args.get('sort'),\
                            request.args.get('order')), {"__builtins__": None},\
                            {"ExtraData": ExtraData})
            else:
                order_by = eval('ExtraData.%s.desc()' % request.args.get('sort'),\
                        {"__builtins__": None}, {"ExtraData": ExtraData})

    record_count = int(db_session.query(ExtraData).count())
    results = db_session.query(ExtraData, ST_X(ExtraData.location).label('lon'),
            ST_Y(ExtraData.location).label('lat')).order_by(
            order_by).limit(limit).offset(offset).all()
    
    records = []
    for row in results:
        record = {}
        record['id'] = row[0].id
        record['bigquery_key'] = row[0].bigquery_key
        record['verified'] = row[0].verified
        record['timestamp'] = int(row[0].timestamp.strftime('%s')) * 1000
        record['connection_type'] = row[0].connection_type
        record['location_type'] = row[0].location_type
        record['advertised_download'] = row[0].advertised_download
        record['advertised_upload'] = row[0].advertised_upload
        record['cost_of_service'] = row[0].cost_of_service
        record['latitude'] = row.lat
        record['longitude'] = row.lon
        records.append(record)

    if len(records):
        return (jsonify(record_count=record_count, records=records), 200, {})
    else:
        return ('', 500, {})


@app.route("/collect", methods=['GET'])
def append_extra_data():
    location_types = ['residence', 'workplace', 'business', 'public', 'other']
    connection_types = ['cable', 'dsl', 'fiber', 'cellular', 'other']

    try:
        if request.args.get('longitude') and request.args.get('latitude'):
            longitude = float(request.args.get('longitude'))
            latitude = float(request.args.get('latitude'))
            location = 'srid=4326;POINT(%f %f)' % (longitude, latitude)
    except Exception, e:
        location = None
        app.logger.exception(e)

    if request.args.get('connection_type') in connection_types:
        connection_type = request.args.get('connection_type')
    else:
        connection_type = None

    if request.args.get('location_type') in location_types:
        location_type = request.args.get('location_type')
    else:
        location_type = None

    try:
        advertised_download = int(float(request.args.get('advertised_download')))
    except Exception, e:
        advertised_download = None
        app.logger.exception(e)

    try:
        advertised_upload = int(float(request.args.get('advertised_upload')))
    except Exception, e:
        advertised_upload = None
        app.logger.exception(e)

    try:
        cost_of_service = float(request.args.get('cost_of_service'))
    except Exception, e:
        cost_of_service = None
        app.logger.exception(e)

    if len(request.args.get('bigquery_key')) < 100:
        bigquery_key = request.args.get('bigquery_key')
    else:
        bigquery_key = None

    try:
        with db_engine.begin() as conn:
            query = extra_data.insert(dict(
                bigquery_key = bigquery_key,
                location = location,
                connection_type = connection_type,
                advertised_download = advertised_download,
                advertised_upload = advertised_upload,
                location_type = location_type,
                cost_of_service = cost_of_service))
            conn.execute(query)
        return ("", 201, {})
    except Exception, e:
        app.logger.exception(e)
        return ("Failed due to error: " + str(e), 400, {})
