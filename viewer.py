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
        # player_args = player_bin + ['-s', uri]
        player_args = player_bin + [uri]
        # self.player = subprocess.Popen(player_args, bufsize=-1, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        self.player = pexpect.spawn('%s %s' % ('/usr/bin/omxplayer', uri))
        #logging.info('Player started. Running as PID %d.' % self.player.pid)
        logging.info('Player started.')

        self.player.send('p')
        logging.debug('Player init written command')
        #self.player.stdin.flush()
        #logging.debug('Player init flushed command')

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
        #self.player.stdin.flush()
        #logging.debug('Player start flushed command')

    def wait(self):
        #while True:
        #    #logging.debug('Player wait in loop')
        #    l = self.player.readline()
        #    logging.debug('Player wait read line: "%s"' % l)
        #    if not l:
        #        logging.debug('Player wait read eof')
        #        break
        #    logging.debug('Player wait read line: "%s"' % l)
        #self.player.wait()
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

        #sleep(5)  # give browser time to open window
        #wmctrl = subprocess.Popen(['wmctrl', '-l'], bufsize=-1, stdin=None, stdout=subprocess.PIPE)
        #lines = wmctrl.stdout.readlines()
        ##logging.debug('Browser wmctrl read #lines: "%d"' % len(lines))
        #self.windowID = ''
        #searchString = "<" + str(self.uzbl_pid) + ">" 
        ##logging.debug('Browser wmctrl looking for "%s"' % searchString)
        #for l in lines:
        #    #logging.debug('Browser wmctrl read line: "%s"' % l)
        #    #if searchString in l:
        #    #    logging.info('found id')
        #    #if "Uzbl browser" in l:
        #    #    logging.info('found Uzbl')
        #    if searchString in l and "Uzbl browser" in l:
        #        logging.info('found all')
        #        self.windowID = l.split(' ', 2)[0]
        #        break
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

    def reload(self):
        logging.debug('Browser %s reload "%s" ...' % (self.windowID, self.uri))
        self.browser.stdin.write('reload\n')
        logging.debug('Browser %s reload written command' % self.windowID)
        self.browser.stdin.flush()
        logging.debug('Browser %s reload flushed command' % self.windowID)
        result = True
        while True:
            #logging.debug('Browser reload in loop')
            l = self.browser.stdout.readline()
            #logging.debug('Browser reload read line: "%s"' % l)
            if "LOAD_ERROR" in l:
                logging.debug('Browser %s reload load error line: "%s"' % (self.windowID, l))
                result = False
                break
            elif "LOAD_FINISH '" in l and  self.uri + "'" in l:
                logging.debug('Browser %s reload load finish line: "%s"' % (self.windowID, l))
                result = True
                break
        # logging.debug('Browser %s reload "%s" sleep' % (self.windowID, self.uri))
        # seems to be necessary; does it take time for uzbl to update screen after loading page?
        # sleep(0.2)
        logging.debug('Browser %s reload "%s" done' % (self.windowID, self.uri))
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
                    return Asset(next_asset)
                else: 
                    logging.debug('Received non-200 status %d (or file not found if local) from %s. Skipping.' % (web_status, url))
                    pass
            else:
                return Asset(next_asset)
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
    
class Asset(object):
    def __init__(self, asset):
        self.asset = asset
        #self.prefetched = False

    def show(self):
        global player
        next_asset = None
        if "image" in self.asset["mimetype"]:
            # view_image(self.asset["uri"], self.asset["name"], self.asset["duration"], self.asset["fade-color"])
            #if not self.prefetched:
            #    browser.show(self.asset["uri"])
            #    self.prefetched = True
            browser.raisewindow()
            swap_browser()
            # seems that we need slightly more time than .05 to raise the window
            #sleep(0.05)
            #sleep(0.075)
            sleep(0.15)
            shutter.fade_in()
            browser.iconifywindow()
            start = time()
        elif "video" in self.asset["mimetype"]:
            # view_video(self.asset["uri"], self.asset["fade-color"])
            arch = machine()

            #if not self.prefetched:
            #    browser.show(black_video_background_page)
            #    self.prefetched = True

            #shutter.hard_in()
            #sleep(2)

            # browser.reload()
            #browser2.lowerwindow()
            #browser.raisewindow()
            #browser.iconifywindow()
            swap_browser()
            browser.iconifywindow()
            # sleep(2)

            # seems that we need slightly more time than .05 to raise the window
            #sleep(0.05)
            #sleep(0.1)
            sleep(0.15)
            # now that we just show a black background,
            # it makes no sense to waste time by fading in
            # shutter.fade_in()
            shutter.hard_in()
            # sleep(5)

            if player:
                player.start()

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

        elif "web" in self.asset["mimetype"]:
            #if not self.prefetched:
            #    browser.show(self.asset["uri"])
            #    self.prefetched = True
            browser.raisewindow()
            swap_browser()
            # seems that we need slightly more time than .05 to raise the window
            #sleep(0.05)
            # sleep(0.075)
            sleep(0.15)
            shutter.fade_in()
            browser.iconifywindow()
            start = time()
        else:
            print "Unknown MimeType, or MimeType missing"

        next_asset = scheduler.get_next_asset()
        logging.debug('got asset'+str(next_asset))

        next_player = None
        if next_asset and next_asset.asset["mimetype"]:
            if "image" in next_asset.asset["mimetype"] or "web" in next_asset.asset["mimetype"]:
                # load this in browser, not browser2, because we just swapped them
                browser.show(next_asset.asset["uri"])
                # next_asset.prefetch()
                #next_asset.prefetched = True
            elif "video" in next_asset.asset["mimetype"]:
                # black_video_background_page seems not necessary any more,
                # video start up is fast enough to just use black_page
                # browser.show(black_video_background_page)
                # no need for black page anymore: we use black X root window
                # browser.show(black_page)
                next_player = Player(next_asset.asset["uri"])
                #next_asset.prefetched = True

        if "image" in self.asset["mimetype"] or "web" in self.asset["mimetype"]:
            remaining = (start + int(self.asset["duration"]) - time())
            logging.debug('remaining of duration %s: sleep time: %f' % (self.asset["duration"], remaining))
            if remaining > 0:
                sleep(remaining)
        elif player:
           player.wait()

        if next_asset and next_asset.asset["mimetype"] and  "video" in next_asset.asset["mimetype"] and next_player:
           player = next_player

        if "video" in self.asset["mimetype"]:
            shutter.hard_to_black()
        else:
            shutter.fade_to(self.asset["fade-color"])

        return next_asset

    def name(self):
        return self.asset["name"]

def swap_browser():
    global browser
    global browser2
    b = browser2
    browser2 = browser
    browser = b

def view_image(image, name, duration, fade_color):
    logging.debug('Displaying image %s for %s seconds.' % (image, duration))
    url = html_templates.image_page(image, name)
    # browser.show(url)
    browser.raisewindow()
    swap_browser()
    shutter.fade_in()
    
    sleep(int(duration))
    
    shutter.fade_to(fade_color)
    #browser.show(black_page)
    
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
    web_resource = 200
    #if (html_folder in url and path.exists(url)):
    #    web_resource = 200
    #else:
    #    web_resource = get(url).status_code

    next_asset = None

    if web_resource == 200:
        logging.debug('Web content appears to be available. Proceeding.')  
        logging.debug('Displaying url %s for %s seconds.' % (url, duration))
        # browser.show(url)
        browser.raisewindow()
        swap_browser()
        shutter.fade_in()
    
        next_asset = scheduler.get_next_asset()
        logging.debug('got asset'+str(next_asset))

        if next_asset and next_asset.asset["mimetype"]:
            if "image" in next_asset.asset["mimetype"] or "web" in next_asset.asset["mimetype"]:
                # load this in browser, not browser2, because we just swapped them
                browser.show(next_asset.asset["uri"])
                # next_asset.prefetch()

        sleep(int(duration))

        shutter.fade_to(fade_color)
    
        #browser.show(black_page)
    else: 
        logging.debug('Received non-200 status (or file not found if local) from %s. Skipping.' % (url))
        pass
    return next_asset

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
black_video_background_page = html_templates.black_video_background_page()

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
player_bin = ['omxplayer']
omxplayer_logfile = path.join(getenv('HOME'), 'omxplayer.log')
omxplayer_old_logfile = path.join(getenv('HOME'), 'omxplayer.old.log')
player = None

if show_splash:
    # FIXME can/should we deal with splash page as a special (synthesized) asset?
    browser.show("http://127.0.0.1:8080/splash_page")
    # don't know why we used black_video_background_page here;
    # using black_page will look much better.
    # browser.show(black_video_background_page)
    swap_browser()
    #browser.show(black_page)
    shutter.fade_in()
    time_to_wait = 15 # was 60
    # browser.show(black_page)
else:
    time_to_wait = 1

cur = time()
scheduler = Scheduler()
asset = scheduler.get_next_asset()

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
        # next_asset  = view_web(black_page, 1, 'white')
        next_asset  = scheduler.get_next_asset()
    else:
        logging.info('show asset %s' % asset.name())
        next_asset = asset.show()

    asset = next_asset
