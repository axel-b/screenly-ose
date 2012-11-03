#!/usr/bin/env python
# -*- coding: utf8 -*-

__author__ = "Viktor Petersson"
__copyright__ = "Copyright 2012, WireLoad Inc"
__license__ = "Dual License: GPLv2 and Commercial License"
__version__ = "0.1.2"
__email__ = "vpetersson@wireload.net"

import sqlite3, ConfigParser
from netifaces import ifaddresses
from sys import exit, platform, stdout, path as sys_path
from requests import get as req_get
from os import path, getenv, makedirs, getloadavg, statvfs
from hashlib import md5
from json import dumps, loads 
from datetime import datetime, timedelta
from time import time
from bottle import route, run, debug, template, request, validate, error, static_file, get, redirect, app as bottle_app
from cherrypy.wsgiserver import CherryPyWSGIServer
from cherrypy.wsgiserver.ssl_builtin import BuiltinSSLAdapter
from paste.translogger import TransLogger
from dateutils import datestring
from StringIO import StringIO
from PIL import Image
from urlparse import urlparse
from hurry.filesize import size

sys_path.append('bottlesession')
import bottlesession

# when no credentials are given in config, the web interface will not ask for them
config_defaults = {'username':'', 'password':''}

# when ssl certificate and key files are given, use https; otherwise, use http
config_defaults.update({'sslcert':'', 'sslkey':''})

# Get config file
config = ConfigParser.ConfigParser(config_defaults)
conf_file = path.join(getenv('HOME'), '.screenly', 'screenly.conf')
if not path.isfile(conf_file):
    print 'Config-file missing.'
    exit(1)
else:
    print 'Reading config-file...'
    config.read(conf_file)

configdir = path.join(getenv('HOME'), config.get('main', 'configdir'))
database = path.join(getenv('HOME'), config.get('main', 'database'))
nodetype = config.get('main', 'nodetype')

# always use cherrypy, independent of use of http or https,
# such that we always can use same logging config via translogger
# (if we just use wsgiref server for http, we get double logging)
server = 'cherrypy'
# make sure we get logging output while using cherrypy as server
logapp = TransLogger(bottle_app())

# decide whether to use https or http
sslcert = config.get('main', 'sslcert')
sslkey = config.get('main', 'sslkey')
if sslcert and sslkey:
    proto = 'HTTPS'
    CherryPyWSGIServer.ssl_adapter = BuiltinSSLAdapter(sslcert, sslkey, None)
else:
    proto = 'HTTP'
print 'using %s via %s server' % (proto, server)

# get database last modification time
try:
    db_mtime = path.getmtime(database)
except:
    db_mtime = 0

username = config.get('main', 'username')
password = config.get('main', 'password')
credentials = { username:password, }

# Initialize session manager
if not username or not password:
    print 'Not using authentication in web interface.'
    print 'To enable authentication in web interface,'
    print ' specify both a username and a password in the config-file.'
    session_manager = bottlesession.PreconfiguredSession({'valid':True, 'name': '', 'new': False})
else:
    session_manager = bottlesession.MemorySession()
    print 'Using authentication in web interface.'
valid_user = bottlesession.authenticator(session_manager)
    
def time_lookup():
    if nodetype == "standalone":
        return datetime.now()
    elif nodetype == "managed":
        return datetime.utcnow()

def get_playlist():
    
    conn = sqlite3.connect(database, detect_types=sqlite3.PARSE_DECLTYPES)
    c = conn.cursor()
    c.execute("SELECT * FROM assets ORDER BY name")
    assets = c.fetchall()
    
    playlist = []
    for asset in assets:
        # Match variables with database
        asset_id = asset[0]  
        name = asset[1]
        uri = asset[2] # Path in local database
        input_start_date = asset[4]
        input_end_date = asset[5]

        try:
            start_date = datestring.date_to_string(asset[4])
        except:
            start_date = None

        try:
            end_date = datestring.date_to_string(asset[5])
        except:
            end_date = None
            
        duration = asset[6]
        mimetype = asset[7]

        playlistitem = {
                "name" : name,
                "uri" : uri,
                "duration" : duration,
                "mimetype" : mimetype,
                "asset_id" : asset_id,
                "start_date" : start_date,
                "end_date" : end_date
                }
        if (start_date and end_date) and (input_start_date < time_lookup() and input_end_date > time_lookup()):
		playlist.append(playlistitem)
    
    return dumps(playlist)

def get_assets():
    
    conn = sqlite3.connect(database, detect_types=sqlite3.PARSE_DECLTYPES)
    c = conn.cursor()
    c.execute("SELECT asset_id, name, uri, start_date, end_date, duration, mimetype FROM assets ORDER BY name")
    assets = c.fetchall()
    
    playlist = []
    for asset in assets:
        # Match variables with database
        asset_id = asset[0]  
        name = asset[1]
        uri = asset[2] # Path in local database

        try:
            start_date = datestring.date_to_string(asset[3])
        except:
            start_date = ""

        try:
            end_date = datestring.date_to_string(asset[4])
        except:
            end_date = ""
            
        duration = asset[5]
        mimetype = asset[6]

        playlistitem = {
                "name" : name,
                "uri" : uri,
                "duration" : duration,
                "mimetype" : mimetype,
                "asset_id" : asset_id,
                "start_date" : start_date,
                "end_date" : end_date
                }
	playlist.append(playlistitem)
    
    return dumps(playlist)

def initiate_db():
    global db_mtime

    # Create config dir if it doesn't exist
    if not path.isdir(configdir):
       makedirs(configdir)

    conn = sqlite3.connect(database, detect_types=sqlite3.PARSE_DECLTYPES)
    c = conn.cursor()

    # Check if the asset-table exist. If it doesn't, create it.
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='assets'")
    asset_table = c.fetchone()
    
    if not asset_table:
        c.execute("CREATE TABLE assets (asset_id TEXT, name TEXT, uri TEXT, md5 TEXT, start_date TIMESTAMP, end_date TIMESTAMP, duration TEXT, mimetype TEXT)")
        db_mtime = time()
        return "Initiated database."

@route('/auth/login', method='POST')
@route('/auth/login', method='GET')
def login():
    username = request.POST.get('username')
    password = request.POST.get('password')

    #if (request.POST.get('name','').strip() and
    #    request.POST.get('password','').strip()
    #    ):
    #
    #    name =  request.POST.get('name','').strip()
    #    password = request.POST.get('password','').strip()
    #    if (name, password) == ('rott', 'hackme'):
    #           return template('index')
    #
    # return template('login')

    session = session_manager.get_session()
    session['valid'] = False

    if request.method == 'POST' and session['new']:
        message = "Cookies must be enabled to be able to authenticate."
        return template('login', message=message, error='')

    if not username or not password:
        message = "Please specify username and password"
        return template('login', message=message, error='')

    if password and credentials.get(username) == password:
        session['valid'] = True
        session['name'] = username

    session_manager.save(session)

    if not session['valid']:
        error = "Username or password is invalid"
        return template('login', message='', error=error)

    redirpath = request.get_cookie('validuserloginredirect')
    redirect(redirpath)


@route('/auth/logout')
@valid_user()
def logout():
    # actually, instead of marking session as invalid, we should just delete it
    # unfortunately, the session manager does not allow us to do that (yet?)
    session = session_manager.get_session()
    session['valid'] = False
    session_manager.save(session)
    redirect('/auth/login')

@route('/dbisnewer/:t#[0-9]+(\.[0-9]+)?#')
def dbisnewer(t):
    try:
        if float(db_mtime) >= float(t):
            res = 'yes'
        else:
            res = 'no'
    except:
        res = 'error'

    print 'dbisnewer t='+str(t)+'  db_mtime='+str(db_mtime)+' : '+res
    stdout.flush()
    return res

@route('/process_asset', method='POST')
@valid_user()
def process_asset():
    global db_mtime
    username = request.environ['REMOTE_USER']

    conn = sqlite3.connect(database, detect_types=sqlite3.PARSE_DECLTYPES)
    c = conn.cursor()

    if (request.POST.get('name','').strip() and 
        request.POST.get('uri','').strip() and
        request.POST.get('mimetype','').strip()
        ):

        name =  request.POST.get('name','').decode('UTF-8')
        uri = request.POST.get('uri','').strip()
        mimetype = request.POST.get('mimetype','').strip()

        # Make sure it's a valid resource
        uri_check = urlparse(uri)
        if not (uri_check.scheme == "http" or uri_check.scheme == "https"):
            header = "Ops!"
            message = "URL must be HTTP or HTTPS."
            return template('message', header=header, message=message, username=username)

        file = req_get(uri)

        # Only proceed if fetch was successful. 
        if file.status_code == 200:
            asset_id = md5(name+uri).hexdigest()
            
            strict_uri = uri_check.scheme + "://" + uri_check.netloc + uri_check.path

            if "image" in mimetype:
                resolution = Image.open(StringIO(file.content)).size
            else:
                resolution = "N/A"

            if "video" in mimetype:
                duration = "N/A"

            start_date = ""
            end_date = ""
            duration = ""
            
            c.execute("INSERT INTO assets (asset_id, name, uri, start_date, end_date, duration, mimetype) VALUES (?,?,?,?,?,?,?)", (asset_id, name, uri, start_date, end_date, duration, mimetype))
            conn.commit()
            db_mtime = time()
            
            header = "Yay!"
            message =  "Added asset (" + asset_id + ") to the database."
            return template('message', header=header, message=message, username=username)
            
        else:
            header = "Ops!"
            message = "Unable to fetch file."
            return template('message', header=header, message=message, username=username)
    else:
        header = "Ops!"
        message = "Invalid input."
        return template('message', header=header, message=message, username=username)

@route('/process_schedule', method='POST')
@valid_user()
def process_schedule():
    global db_mtime
    username = request.environ['REMOTE_USER']
    conn = sqlite3.connect(database, detect_types=sqlite3.PARSE_DECLTYPES)
    c = conn.cursor()

    if (request.POST.get('asset','').strip() and 
        request.POST.get('start','').strip() and
        request.POST.get('end','').strip()
        ):

        asset_id =  request.POST.get('asset','').strip()
        input_start = request.POST.get('start','').strip()
        input_end = request.POST.get('end','').strip() 

        start_date = datetime.strptime(input_start, '%Y-%m-%d @ %H:%M')
        end_date = datetime.strptime(input_end, '%Y-%m-%d @ %H:%M')

        query = c.execute("SELECT mimetype FROM assets WHERE asset_id=?", (asset_id,))
        asset_mimetype = c.fetchone()
        
        if "image" or "web" in asset_mimetype:
            try:
                duration = request.POST.get('duration','').strip()
            except:
                header = "Ops!"
                message = "Duration missing. This is required for images and web-pages."
                return template('message', header=header, message=message, username=username)
        else:
            duration = "N/A"

        c.execute("UPDATE assets SET start_date=?, end_date=?, duration=? WHERE asset_id=?", (start_date, end_date, duration, asset_id))
        conn.commit()
        db_mtime = time()
        
        header = "Yes!"
        message = "Successfully scheduled asset."
        return template('message', header=header, message=message, username=username)
        
    else:
        header = "Ops!"
        message = "Failed to process schedule."
        return template('message', header=header, message=message, username=username)

@route('/update_asset', method='POST')
@valid_user()
def update_asset():
    global db_mtime
    username = request.environ['REMOTE_USER']
    conn = sqlite3.connect(database, detect_types=sqlite3.PARSE_DECLTYPES)
    c = conn.cursor()

    if (request.POST.get('asset_id','').strip() and 
        request.POST.get('name','').strip() and
        request.POST.get('uri','').strip() and
        request.POST.get('mimetype','').strip()
        ):

        asset_id =  request.POST.get('asset_id','').strip()
        name = request.POST.get('name','').decode('UTF-8')
        uri = request.POST.get('uri','').strip()
        mimetype = request.POST.get('mimetype','').strip()

        try:
            duration = request.POST.get('duration','').strip()
        except:
            duration = None

        try:
            input_start = request.POST.get('start','')
            start_date = datetime.strptime(input_start, '%Y-%m-%d @ %H:%M')
        except:
            start_date = None

        try:
            input_end = request.POST.get('end','').strip()
            end_date = datetime.strptime(input_end, '%Y-%m-%d @ %H:%M')
        except:
            end_date = None

        c.execute("UPDATE assets SET start_date=?, end_date=?, duration=?, name=?, uri=?, duration=?, mimetype=? WHERE asset_id=?", (start_date, end_date, duration, name, uri, duration, mimetype, asset_id))
        conn.commit()
        db_mtime = time()

        header = "Yes!"
        message = "Successfully updated asset."
        return template('message', header=header, message=message, username=username)

    else:
        header = "Ops!"
        message = "Failed to update asset."
        return template('message', header=header, message=message, username=username)


@route('/delete_asset/:asset_id')
@valid_user()
def delete_asset(asset_id):
    global db_mtime
    username = request.environ['REMOTE_USER']
    conn = sqlite3.connect(database, detect_types=sqlite3.PARSE_DECLTYPES)
    c = conn.cursor()
    
    c.execute("DELETE FROM assets WHERE asset_id=?", (asset_id,))
    try:
        conn.commit()
        db_mtime = time()
        
        header = "Success!"
        message = "Deleted asset."
        return template('message', header=header, message=message, username=username)
    except:
        header = "Ops!"
        message = "Failed to delete asset."
        return template('message', header=header, message=message, username=username)

@route('/')
@valid_user()
def viewIndex():
    username = request.environ['REMOTE_USER']
    initiate_db()
    return template('index', username=username)


@route('/system_info')
@valid_user()
def system_info():
    username = request.environ['REMOTE_USER']
    viewer_log_file = '/tmp/screenly_viewer.log'
    if path.exists(viewer_log_file):
        f = open(viewer_log_file, 'r')
        viewlog = f.readlines()    
        f.close()
    else:
    	viewlog = ["(no viewer log present -- is only the screenly server running?)\n"]

    loadavg = getloadavg()[2]
    
    # Calculate disk space
    slash = statvfs("/")
    free_space = size(slash.f_bsize * slash.f_bavail)
    
    # Get uptime
    with open('/proc/uptime', 'r') as f:
        uptime_seconds = float(f.readline().split()[0])
        uptime = str(timedelta(seconds = uptime_seconds))

    return template('system_info', viewlog=viewlog, loadavg=loadavg, free_space=free_space, uptime=uptime, username=username)

@route('/splash_page')
def splash_page():

    # Make sure the database exist and that it is initiated.
    initiate_db()

    try:
        my_ip = ifaddresses('eth0')[2][0]['addr']
        ip_lookup = True
        url = 'http://' + my_ip + ':8080'
    except:
        ip_lookup = False
        url = "Unable to lookup IP from eth0."

    return template('splash_page', ip_lookup=ip_lookup, url=url)


@route('/view_playlist')
@valid_user()
def view_node_playlist():
    username = request.environ['REMOTE_USER']

    nodeplaylist = loads(get_playlist())
    
    return template('view_playlist', nodeplaylist=nodeplaylist, username=username)

@route('/view_assets')
@valid_user()
def view_assets():
    username = request.environ['REMOTE_USER']

    nodeplaylist = loads(get_assets())
    
    return template('view_assets', nodeplaylist=nodeplaylist, username=username)


@route('/add_asset')
@valid_user()
def add_asset():
    username = request.environ['REMOTE_USER']
    return template('add_asset', username=username)


@route('/schedule_asset')
@valid_user()
def schedule_asset():
    username = request.environ['REMOTE_USER']
    
    conn = sqlite3.connect(database, detect_types=sqlite3.PARSE_DECLTYPES)
    c = conn.cursor()

    assets = []
    c.execute("SELECT name, asset_id FROM assets ORDER BY name")
    query = c.fetchall()
    for asset in query:
        name = asset[0]
        asset_id = asset[1]
        
        assets.append({
            'name' : name,
            'asset_id' : asset_id,
        })

    return template('schedule_asset', assets=assets, username=username)
        
@route('/edit_asset/:asset_id')
@valid_user()
def edit_asset(asset_id):
    username = request.environ['REMOTE_USER']

    conn = sqlite3.connect(database, detect_types=sqlite3.PARSE_DECLTYPES)
    c = conn.cursor()

    c.execute("SELECT name, uri, md5, start_date, end_date, duration, mimetype FROM assets WHERE asset_id=?", (asset_id,))
    asset = c.fetchone()
    
    name = asset[0]
    uri = asset[1]
    md5 = asset[2]

    if asset[3]:
	    start_date = datestring.date_to_string(asset[3])
    else:
	    start_date = None

    if asset[4]:
	    end_date = datestring.date_to_string(asset[4])
    else:
	    end_date = None

    duration = asset[5]
    mimetype = asset[6]

    asset_info = {
            "name" : name,
            "uri" : uri,
            "duration" : duration,
            "mimetype" : mimetype,
            "asset_id" : asset_id,
            "start_date" : start_date,
            "end_date" : end_date
            }
    #return str(asset_info)
    return template('edit_asset', asset_info=asset_info, username=username)
        
# Static
@route('/static/:path#.+#', name='static')
def static(path):
    return static_file(path, root='static')

@error(403)
def mistake403(code):
    return 'The parameter you passed has the wrong format!'

@error(404)
def mistake404(code):
    return 'Sorry, this page does not exist!'

# Ugly local dev fix.
if platform == "darwin":
    port = '8080'
    run(app=logapp, host='127.0.0.1', port=port, reloader=True, server=server)
else:
    run(app=logapp, host='0.0.0.0', port=8080, reloader=True, server=server)
