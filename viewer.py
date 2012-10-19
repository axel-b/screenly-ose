#!/usr/bin/env python
# -*- coding: utf8 -*-

__author__ = "Viktor Petersson"
__copyright__ = "Copyright 2012, WireLoad Inc"
__license__ = "Dual License: GPLv2 and Commercial License"
__version__ = "0.1"
__email__ = "vpetersson@wireload.net"

import sqlite3, ConfigParser
from sys import exit
from requests import get 
from platform import machine 
from os import path, getenv, remove, makedirs
from os import stat as os_stat
#from subprocess import Popen, call 
import subprocess
import html_templates
from datetime import datetime
from time import sleep, time
import logging
from glob import glob
from stat import S_ISFIFO

# Initiate logging
logging.basicConfig(level=logging.INFO,
                    filename='/tmp/screenly_viewer.log',
                    format='%(asctime)s %(message)s',
                    datefmt='%a, %d %b %Y %H:%M:%S')

# Silence urllib info messages ('Starting new HTTP connection')
# that are triggered by the remote url availability check in view_web
requests_log = logging.getLogger("requests")
requests_log.setLevel(logging.WARNING)

logging.debug('Starting viewer.py')

# Get config file
config = ConfigParser.ConfigParser()
conf_file = path.join(getenv('HOME'), '.screenly', 'screenly.conf')
if not path.isfile(conf_file):
    logging.info('Config-file missing.')
    exit(1)
else:
    logging.debug('Reading config-file...')
    config.read(conf_file)

def time_lookup():
    if nodetype == "standalone":
        return datetime.now()
    elif nodetype == "managed":
        return datetime.utcnow()

def str_to_bol(string):
    if 'true' in string.lower():
        return True
    else:
        return False

class Browser(object):
    def __init__(self, resolution):
        logging.debug('Browser init...')
        browser_args = browser_bin + ["-c", "-", "--print-events", "--geometry=" + resolution]
        self.browser = subprocess.Popen(browser_args, bufsize=-1, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        logging.info('Browser loaded. Running as PID %d.' % self.browser.pid)

        self.browser.stdin.write('set show_status=0\n')
        logging.debug('Browser init written command')
        self.browser.stdin.flush()
        logging.debug('Browser init flushed command')
        while True:
            #logging.debug('Browser init in loop')
            l = self.browser.stdout.readline()
            #logging.debug('Browser init read line: "%s"' % l)
            if "VARIABLE_SET show_status int 0" in l:
                break
        logging.debug('Browser init done')

    def show(self, uri):
        logging.debug('Browser show "%s" ...' % uri)
        self.browser.stdin.write('set uri=%s\n' % uri)
        logging.debug('Browser show written command')
        self.browser.stdin.flush()
        logging.debug('Browser show flushed command')
        result = True
        while True:
            #logging.debug('Browser show in loop')
            l = self.browser.stdout.readline()
            #logging.debug('Browser show read line: "%s"' % l)
            if "LOAD_ERROR" in l:
                logging.debug('Browser show load error line: "%s"' % l)
                result = False
                break
            elif "LOAD_FINISH '" in l and  uri + "'" in l:
                logging.debug('Browser show load finish line: "%s"' % l)
                result = True
                break
        logging.debug('Browser show "%s" done' % uri)
        # seems to be necessary; does it take time for uzbl to update screen after loading page?
        sleep(0.2)
        return result

class Shutter(object):
    # FIXME we only look at stdout of fade program;
    # instead, we should also watch its stderr.
    # moreover, what if something goes wrong and we hang forever in readline() ?
    # should we use a timer to be robust against that?
    def __init__(self):
        shutter_args = [shutter_bin]
        self.shutter = subprocess.Popen(shutter_args, bufsize=1, stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    def fade_to(self, color):
        if color == 'white':
            self.fade_to_white()
        elif color == 'black':
            self.fade_to_black()
        else:
            # FIXME give error message?
            self.fade_to_black()

    def fade_to_black(self):
        self.issue_command('fade-to-black\n', 'fade_to_black')

    def fade_to_white(self):
        self.issue_command('fade-to-white\n', 'fade_to_white')

    def fade_in(self):
        self.issue_command('fade-in\n', 'fade_in')

    def hard_to_black(self):
        self.issue_command('hard-to-black\n', 'hard_to_black')

    def hard_to_white(self):
        self.issue_command('hard-to-white\n', 'hard_to_white')

    def hard_in(self):
        self.issue_command('hard-in\n', 'hard_in')

    def issue_command(self, command, function_name):
        if not self.shutter:
                return
        self.shutter.stdin.write(command)
        self.shutter.stdin.flush()
        l = self.shutter.stdout.readline()
        logging.debug('%s read "%s"' % (function_name, l))


class Scheduler(object):
    def __init__(self, *args, **kwargs):
        logging.debug('Scheduler init')
        self.update_playlist()

    def get_next_asset(self):
        logging.debug('get_next_asset')
        self.refresh_playlist()
        logging.debug('get_next_asset after refresh')
        if self.nassets == 0:
            return None
        idx = self.index
        self.index = (self.index + 1) % self.nassets
        logging.debug('get_next_asset counter %d returning asset %d of %d' % (self.counter, idx+1, self.nassets))
        if shuffle_playlist and self.index == 0:
            self.counter += 1
        return self.assets[idx]

    def refresh_playlist(self):
        logging.debug('refresh_playlist')
        time_cur = time_lookup()
        logging.debug('refresh: counter: (%d) deadline (%s) timecur (%s)' % (self.counter, self.deadline, time_cur))
        if self.dbisnewer():
            self.update_playlist()
        elif shuffle_playlist and self.counter >= 5:
            self.update_playlist()
        elif self.deadline != None and self.deadline <= time_cur:
            self.update_playlist()

    def update_playlist(self):
        logging.debug('update_playlist')
        (self.assets, self.deadline) = generate_asset_list()
        self.nassets = len(self.assets)
        self.gentime = time()
        self.counter = 0
        self.index = 0
        logging.debug('update_playlist done, count %d, counter %d, index %d, deadline %s' % (self.nassets, self.counter, self.index, self.deadline))

    def dbisnewer(self):
        return self.dbisnewer_check_file()
        # return self.dbisnewer_ask_server()

    def dbisnewer_ask_server(self):
        dbisnewer = get("http://127.0.0.1:8080/dbisnewer/"+str(self.gentime))
        logging.info('dbisnewer: code (%d), text: (%s)' % (dbisnewer.status_code, dbisnewer.text))
        return dbisnewer.status_code == 200 and dbisnewer.text == "yes"

    def dbisnewer_check_file(self):
        # get database file last modification time
        try:
            db_mtime = path.getmtime(database)
        except:
            db_mtime = 0
        return db_mtime >= self.gentime

def generate_asset_list():
    logging.info('Generating asset-list...')
    conn = sqlite3.connect(database, detect_types=sqlite3.PARSE_DECLTYPES)
    c = conn.cursor()
    c.execute("SELECT asset_id, name, uri, md5, start_date, end_date, duration, mimetype FROM assets ORDER BY name")
    query = c.fetchall()

    playlist = []
    time_cur = time_lookup()
    deadline = None
    for asset in query:
        asset_id = asset[0]  
        name = asset[1].encode('ascii', 'ignore')
        uri = asset[2]
        md5 = asset[3]
        start_date = asset[4]
        end_date = asset[5]
        duration = asset[6]
        mimetype = asset[7]

        logging.debug('generate_asset_list: %s: start (%s) end (%s)' % (name, start_date, end_date))
        if (start_date and end_date) and (start_date < time_cur and end_date > time_cur):
            playlist.append({"name" : name, "uri" : uri, "duration" : duration, "mimetype" : mimetype})
        if (start_date and end_date) and (start_date < time_cur and end_date > time_cur):
            if deadline == None or end_date < deadline:
               deadline = end_date
        if (start_date and end_date) and (start_date > time_cur and end_date > start_date):
            if deadline == None or start_date < deadline:
               deadline = start_date

    logging.debug('generate_asset_list deadline: %s' % deadline)

    if shuffle_playlist:
        from random import shuffle
        shuffle(playlist)

    # associate fade-(out-)color with each asset in playlist,
    # based on the mime-type of the asset succeding (after) it;
    # we might allow user to associate colors with assets in web-interface,
    # for now: all video: black; anything else: white
    i = 0
    nplaylist = len(playlist)
    while i < nplaylist:
        if "video" in playlist[(i+1)%nplaylist]['mimetype']:
            playlist[i]['fade-color'] = 'black'
        else:
            playlist[i]['fade-color'] = 'white'
        i = i + 1
    
    return (playlist, deadline)
    

def view_image(image, name, duration, fade_color):
    logging.debug('Displaying image %s for %s seconds.' % (image, duration))
    url = html_templates.image_page(image, name)
    browser.show(url)
    shutter.fade_in()
    
    sleep(int(duration))
    
    shutter.fade_to(fade_color)
    browser.show(black_page)
    
def view_video(video, fade_color):
    arch = machine()

    shutter.fade_in()

    ## For Raspberry Pi
    if arch == "armv6l":
        logging.debug('Displaying video %s. Detected Raspberry Pi. Using omxplayer.' % video)
        omxplayer = "omxplayer"
        omxplayer_args = [omxplayer, "-o", audio_output, "-w", str(video)]
        run = subprocess.call(omxplayer_args, stdout=True)
        logging.debug(run)

        if run != 0:
            logging.debug("Unclean exit: " + str(run))

        # Clean up after omxplayer
        omxplayer_logfile = path.join(getenv('HOME'), 'omxplayer.log')
        if path.isfile(omxplayer_logfile):
            remove(omxplayer_logfile)

    ## For x86
    elif arch == "x86_64" or arch == "x86_32":
        logging.debug('Displaying video %s. Detected x86. Using mplayer.' % video)
        mplayer = "mplayer"
        run = subprocess.call([mplayer, "-fs", "-nosound", str(video) ], stdout=False)
        if run != 0:
            logging.debug("Unclean exit: " + str(run))

    shutter.fade_to(fade_color)

def view_web(url, duration, fade_color):
    # If local web page, check if the file exist. If remote, check if it is
    # available.
    if (html_folder in url and path.exists(url)):
        web_resource = 200
    else:
        web_resource = get(url).status_code

    if web_resource == 200:
        logging.debug('Web content appears to be available. Proceeding.')  
        logging.debug('Displaying url %s for %s seconds.' % (url, duration))
        browser.show(url)
        shutter.fade_in()
    
        sleep(int(duration))

        shutter.fade_to(fade_color)
    
        browser.show(black_page)
    else: 
        logging.debug('Received non-200 status (or file not found if local) from %s. Skipping.' % (url))
        pass

# Get config values
configdir = path.join(getenv('HOME'), config.get('main', 'configdir'))
database = path.join(getenv('HOME'), config.get('main', 'database'))
nodetype = config.get('main', 'nodetype')
show_splash = str_to_bol(config.get('viewer', 'show_splash'))
audio_output = config.get('viewer', 'audio_output')
shuffle_playlist = str_to_bol(config.get('viewer', 'shuffle_playlist'))

try:
    resolution = config.get('viewer', 'resolution')
except:
    resolution = '1920x1080'

# Create folder to hold HTML-pages
html_folder = '/tmp/screenly_html/'
if not path.isdir(html_folder):
   makedirs(html_folder)

# Set up HTML templates
black_page = html_templates.black_page()

# FIXME do not hardcode shutter executable location
shutter_bin = path.join(getenv('HOME'), 'screenly', 'shutter', 'shutter.bin')
shutter = Shutter()

# FIXME specify shutter timing here, or via config,
# instead of hard-coded in the view_foo functions, as it is now.

shutter.fade_to_black()

# Fire up the browser
browser_bin = [path.join(getenv('HOME'), 'screenly', 'filter-for-uzbl.py'), 'uzbl']
browser = Browser(resolution)

if show_splash:
    # FIXME can/should we deal with splash page as a special (synthesized) asset?
    browser.show("http://127.0.0.1:8080/splash_page")
    shutter.fade_in()
    sleep(60)
    shutter.fade_to_black()

# Bring up the blank page (in case there are only videos).
logging.debug('Loading blank page.')
view_web(black_page, 1, 'white')

scheduler = Scheduler()

# Infinit loop. 
logging.debug('Entering infinite loop.')
while True:

    asset = scheduler.get_next_asset()
    logging.debug('got asset'+str(asset))

    if asset == None:
        # The playlist is empty, go to sleep.
        logging.info('Playlist is empty. Going to sleep.')
        sleep(5)
    else:
        logging.info('show asset %s' % asset["name"])

        if "image" in asset["mimetype"]:
            view_image(asset["uri"], asset["name"], asset["duration"], asset["fade-color"])
        elif "video" in asset["mimetype"]:
            view_video(asset["uri"], asset["fade-color"])
        elif "web" in asset["mimetype"]:
            view_web(asset["uri"], asset["duration"], asset["fade-color"])
        else:
            print "Unknown MimeType, or MimeType missing"
