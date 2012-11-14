#!/usr/bin/env python
# -*- coding: utf8 -*-

__author__ = "Viktor Petersson"
__copyright__ = "Copyright 2012, WireLoad Inc"
__license__ = "Dual License: GPLv2 and Commercial License"
__version__ = "0.1"
__email__ = "vpetersson@wireload.net"

import sqlite3, ConfigParser
from sys import exit
from requests import get, head
from platform import machine 
from os import path, getenv, remove, makedirs
from os import stat as os_stat
#from subprocess import Popen, call 
import subprocess
import pexpect
import html_templates
from datetime import datetime
from time import sleep, time
import logging
from glob import glob
from stat import S_ISFIFO

# Initiate logging
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(message)s')
#,
#                    filename='/tmp/screenly_viewer.log',

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

class Player(object):
    def __init__(self, uri):
        # do not use '-s' flag (not needed, will give lots of unneeded output)
        self.player = pexpect.spawn('%s %s' % (player_bin, uri))
        logging.info('Player started.')

        self.player.send('p')
        logging.debug('Player init written command')

        # wait for  Subtitle count
        while True:
            #logging.debug('Player init in loop')
            l = self.player.readline()
            if not l:
                logging.debug('Player init read eof')
                break
            logging.debug('Player init read line: "%s"' % l)
            if "Subtitle count" in l:
                break
        logging.debug('Player init done')

    def start(self):
        self.player.send('p')
        logging.debug('Player start written command')

    def wait(self):
        logging.debug('Player waiting for eof on process')
        self.player.expect(pexpect.EOF, timeout=None)
        logging.debug('Player waiting seen eof on process')
        self.player.terminate(force=True)
        logging.debug('Player waiting cleanup')
        # Clean up after omxplayer
        if path.isfile(omxplayer_old_logfile):
            remove(omxplayer_old_logfile)
        elif path.isfile(omxplayer_logfile):
            remove(omxplayer_logfile)
        logging.debug('Player done')

class Browser(object):
    def __init__(self, resolution):
        self.uri = None
        logging.debug('Browser init...')
        browser_args = browser_bin + ["-c", "-", "--print-events", "--geometry=" + resolution]
        self.browser = subprocess.Popen(browser_args, bufsize=-1, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        logging.info('Browser loaded. Running as PID %d.' % self.browser.pid)

        # wait for FOCUS_GAINED
        while True:
            #logging.debug('Browser init in loop')
            l = self.browser.stdout.readline()
            #logging.debug('Browser init read line: "%s"' % l)
            # EVENT [2785]
            if "FOCUS_GAINED" in l:
                break
        self.browser.stdin.write('set show_status=0\n')
        logging.debug('Browser init written command')
        self.browser.stdin.flush()
        logging.debug('Browser init flushed command')
        while True:
            #logging.debug('Browser init in loop')
            l = self.browser.stdout.readline()
            #logging.debug('Browser init read line: "%s"' % l)
            # EVENT [2785]
            if "VARIABLE_SET show_status int 0" in l:
                word = l.split(' ', 3)[1]
                self.uzbl_pid = word.strip('[]')
                break

        # sync_spawn /bin/bash -c "echo $UZBL_XID"
        # EVENT [20546] COMMAND_EXECUTED sync_spawn  '/bin/bash' '-c' 'echo $UZBL_XID'
        # 20971556
        self.browser.stdin.write('sync_spawn /bin/bash -c "echo $UZBL_XID"\n')
        self.browser.stdin.flush()
        logging.debug('Browser init flushed spawn command')
        while True:
            l = self.browser.stdout.readline()
            logging.debug('Browser init read line (should be EVENT): "%s"' % l)
            if "COMMAND_EXECUTED sync_spawn" in l:
                l = self.browser.stdout.readline()
                logging.debug('Browser init read line(should be windowid in decimal): "%s"' % l)
                self.windowID = l.strip()
                break
        logging.info('Browser loaded. Window id %s.' % self.windowID)
        logging.debug('Browser init done')

    def raisewindow(self):
        logging.debug('Browser %s raisewindow ...' % self.windowID )
        run = subprocess.call(['xwit', '-pop', '-id', self.windowID], stdout=False)
        #run = subprocess.call(['xwit', '-sync', '-raise', '-id', self.windowID], stdout=False)
        #run = subprocess.call(['wmctrl', '-i', '-a', self.windowID], stdout=False)
        logging.debug(run)
        if run != 0:
            logging.debug("Unclean wmctrl raise exit: " + str(run))

    def lowerwindow(self):
        logging.debug('Browser %s lowerwindow ...' % self.windowID )
        run = subprocess.call(['xwit', '-sync', '-lower', '-id', self.windowID], stdout=False)
        logging.debug(run)
        if run != 0:
            logging.debug("Unclean wmctrl lower exit: " + str(run))

    def iconifywindow(self):
        logging.debug('Browser %s iconifywindow ...' % self.windowID )
        run = subprocess.call(['xwit', '-iconify', '-id', self.windowID], stdout=False)
        logging.debug(run)
        if run != 0:
            logging.debug("Unclean wmctrl iconify exit: " + str(run))

    def show(self, uri):
        self.uri = uri
        logging.debug('Browser %s show "%s" ...' % (self.windowID, uri))
        self.browser.stdin.write('set uri=%s\n' % uri)
        logging.debug('Browser %s show written command' % self.windowID)
        self.browser.stdin.flush()
        logging.debug('Browser %s show flushed command' % self.windowID)
        result = True
        while True:
            #logging.debug('Browser show in loop')
            l = self.browser.stdout.readline()
            #logging.debug('Browser show read line: "%s"' % l)
            if "LOAD_ERROR" in l:
                logging.debug('Browser %s show load error line: "%s"' % (self.windowID, l))
                result = False
                break
            elif "LOAD_FINISH '" in l and  uri + "'" in l:
                logging.debug('Browser %s show load finish line: "%s"' % (self.windowID, l))
                result = True
                break
        # logging.debug('Browser %s show "%s" sleep' % (self.windowID, uri))
        # seems to be necessary; does it take time for uzbl to update screen after loading page?
        # sleep(0.2)
        logging.debug('Browser %s show "%s" done' % (self.windowID, uri))
        return result

class Shutter(object):
    # FIXME we only look at stdout of fade program;
    # instead, we should also watch its stderr.
    # moreover, what if something goes wrong and we hang forever in readline() ?
    # should we use a timer to be robust against that?
    def __init__(self):
        self.shutter = None
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
        logging.debug('%s start' % function_name)
        self.shutter.stdin.write(command)
        self.shutter.stdin.flush()
        l = self.shutter.stdout.readline()
        # logging.debug('%s read "%s"' % (function_name, l))
        logging.debug('%s read end' % function_name)


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
        i = 0
        while i < self.nassets:
            idx = self.index
            self.index = (self.index + 1) % self.nassets
            logging.debug('get_next_asset counter %d returning asset %d of %d' % (self.counter, idx+1, self.nassets))
            if shuffle_playlist and self.index == 0:
                self.counter += 1
            next_asset = self.assets[idx]
            if next_asset and "web" in next_asset["mimetype"]:
                url = next_asset["uri"]
                web_status = 200
                if html_folder in url and path.exists(url):
                    web_status = 200
                else:
                    try:
                        web_status = head(url).status_code
                    except:
                        web_status = 0
                if web_status == 200:
                    logging.debug('Web content appears to be available. Proceeding.')
                    logging.debug('got asset'+str(next_asset))
                    return BrowserAsset(next_asset)
                else:
                    logging.debug('Received non-200 status %d (or file not found if local) from %s. Skipping.' % (web_status, url))
                    pass
            elif next_asset and "image" in next_asset["mimetype"]:
                return BrowserAsset(next_asset)
            elif next_asset and "video" in next_asset["mimetype"]:
                return PlayerAsset(next_asset)
            else:
                logging.debug('skipping None asset, or with unknown mimetype')
                pass
            i = i + 1
        return None

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

class BaseAsset(object):
    def __init__(self, asset):
        self.asset = asset

    def prepare(self):
        raise NotImplementedError

    def start(self):
        raise NotImplementedError

    def wait(self):
        raise NotImplementedError

    def name(self):
        return self.asset["name"]

class BrowserAsset(BaseAsset):
    def __init__(self, *args, **kwargs):
        super(BrowserAsset, self).__init__(*args, **kwargs)
        self.starttime = time() # or should we initialize to 0 or -1?
        #self.prefetched = False

    def prepare(self):
        #load this in browser, not browser2, because we just swapped them
        browser.show(self.asset["uri"])
        self.starttime = time() # or should we initialize to 0 or -1?
        #self.prefetched = True

    def start(self):
        #if not self.prefetched:
        #    browser.show(self.asset["uri"])
        #    self.prefetched = True
        browser.raisewindow()
        swap_browser()
        # seems that we need slightly more time than .05 to raise the window
        #sleep(0.05)
        #sleep(0.075)
        #sleep(0.15)
        sleep(0.2)
        shutter.fade_in()
        browser.iconifywindow()
        self.starttime = time()

    def wait(self):
        remaining = (self.starttime + int(self.asset["duration"]) - time())
        logging.debug('remaining of duration %s: sleep time: %f' % (self.asset["duration"], remaining))
        if remaining > 0:
            sleep(remaining)
        shutter.fade_to(self.asset["fade-color"])
 
class PlayerAsset(BaseAsset):
    def __init__(self, *args, **kwargs):
        super(PlayerAsset, self).__init__(*args, **kwargs)
        self.player = None
        #self.prefetched = False

    def prepare(self):
        self.player = Player(self.asset["uri"])
        #self.prefetched = True

    def start(self):
        # view_video(self.asset["uri"], self.asset["fade-color"])

        #if not self.prefetched:
        #    self.player = Player(self.asset["uri"])
        #    self.prefetched = True

        # browser is already/still iconified
        swap_browser()
        browser.iconifywindow()

        # seems that we need slightly more time than .05 to raise the window
        #sleep(0.05)
        #sleep(0.1)
        #sleep(0.15)
        sleep(0.2)
        # now that we just show a black background,
        # it makes no sense to waste time by fading in
        # shutter.fade_in()
        shutter.hard_in()

        if self.player:
            self.player.start()

        #arch = machine()
        ### For Raspberry Pi
        #if arch == "armv6l":
        #    logging.debug('Displaying video %s. Detected Raspberry Pi. Using omxplayer.' % self.asset["uri"])
        #    omxplayer = "omxplayer"
        #    omxplayer_args = [omxplayer, "-o", audio_output, "-w", str(self.asset["uri"])]
        #    run = subprocess.call(omxplayer_args, stdout=True)
        #    logging.debug(run)
        #
        #    if run != 0:
        #        logging.debug("Unclean exit: " + str(run))
        #
        #    # Clean up after omxplayer
        #    omxplayer_logfile = path.join(getenv('HOME'), 'omxplayer.log')
        #    if path.isfile(omxplayer_logfile):
        #        remove(omxplayer_logfile)
        #
        ### For x86
        #elif arch == "x86_64" or arch == "x86_32":
        #    logging.debug('Displaying video %s. Detected x86. Using mplayer.' % self.asset["uri"])
        #    mplayer = "mplayer"
        #    run = subprocess.call([mplayer, "-fs", "-nosound", str(self.asset["uri"]) ], stdout=False)
        #    if run != 0:
        #        logging.debug("Unclean exit: " + str(run))

    def wait(self):
        if self.player:
            self.player.wait()
        shutter.hard_to_black()

def swap_browser():
    global browser
    global browser2
    b = browser2
    browser2 = browser
    browser = b

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

# FIXME do not hardcode shutter executable location
shutter_bin = path.join(getenv('HOME'), 'screenly', 'shutter', 'shutter.bin')
shutter = Shutter()

# FIXME specify shutter timing here, or via config,
# instead of hard-coded in the view_foo functions, as it is now.

shutter.fade_to_black()
logging.debug('Xsetroot black...' )
run = subprocess.call(['xsetroot', '-solid', 'black'], stdout=False)
logging.debug(run)
if run != 0:
    logging.debug("Unclean xsetroot exit: " + str(run))


# Fire up the browser
browser_bin = [path.join(getenv('HOME'), 'screenly', 'filter-for-uzbl.py'), 'uzbl']
browser = Browser(resolution)
browser2 = Browser(resolution)
browser2.lowerwindow()
browser.iconifywindow()
browser2.iconifywindow()
player_bin = '/usr/bin/omxplayer'
omxplayer_logfile = path.join(getenv('HOME'), 'omxplayer.log')
omxplayer_old_logfile = path.join(getenv('HOME'), 'omxplayer.old.log')

if show_splash:
    # FIXME can/should we deal with splash page as a special (synthesized) asset?
    browser.show("http://127.0.0.1:8080/splash_page")
    browser.raisewindow()
    swap_browser()
    #sleep(0.15)
    sleep(0.2)
    shutter.fade_in()
    time_to_wait = 15 # was 60
else:
    time_to_wait = 1

cur = time()
scheduler = Scheduler()
asset = scheduler.get_next_asset()
if asset:
    asset.prepare()

remaining = (cur + time_to_wait) - time()
if remaining > 0:
    sleep(remaining)

if show_splash and asset:
    shutter.fade_to(asset.asset["fade-color"])

# Infinit loop. 
logging.debug('Entering infinite loop.')
while True:

    if asset == None:
        # The playlist is empty, go to sleep.
        logging.info('Playlist is empty. Going to sleep.')
        sleep(5)
        next_asset  = scheduler.get_next_asset()
        if next_asset:
            next_asset.prepare()
    else:
        logging.info('show asset %s' % asset.name())
        asset.start()
        next_asset  = scheduler.get_next_asset()
        if next_asset:
            next_asset.prepare()
        asset.wait()

    asset = next_asset
