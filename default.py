import sys
import os
import json
import xbmcaddon
import xbmcgui
import xbmcplugin
import xbmcvfs
import urllib
import urlparse
try:
    from sqlite3 import dbapi2 as sqlite
    print "Loading sqlite3 as DB engine"
except:
    from pysqlite2 import dbapi2 as sqlite
    print "Loading pysqlite2 as DB engine"
from time import sleep
import re

#
# Addon information
#
__addonid__      = "script.namecleaner"
__addon__        = xbmcaddon.Addon(__addonid__)
__addonname__    = __addon__.getAddonInfo('name')
__addonicon__    = __addon__.getAddonInfo('icon')
__addonfanart__  = __addon__.getAddonInfo('fanart')
__addonversion__ = __addon__.getAddonInfo('version')
__language__     = __addon__.getLocalizedString

base_url = sys.argv[0]
addon_handle = int(sys.argv[1])
args = urlparse.parse_qs(sys.argv[2][1:])
xbmc.log("base:%s handle:%s url:%s" % (sys.argv[0], sys.argv[1], sys.argv[2]))
mode = args.get('mode', None)

xbmcplugin.setContent(addon_handle, 'movies')
DB = os.path.join(xbmc.translatePath("special://database"), 'MyVideos78.db')
conn = sqlite.connect(DB)

c = conn.cursor()

class Main:
    
    types = {
        'movies': {
            'method': "VideoLibrary.GetMovies",
            'pattern': "moviepattern",
            'properties': ["file", "title", "year", "mpaa", "originaltitle", "imdbnumber", "runtime", "country", "streamdetails"],
            'fileidstmt': "select idfile from movie where idmovie = ?",
            'updstmt': "update movie set c22 = ? where idmovie = ?",
            'id': "movieid"
        },
        'tvshows': {
            'method': "VideoLibrary.GetTVShows",
            'properties': ["file", "title"]
        },
        'episodes': {
            'method': "VideoLibrary.GetEpisodes",
            'pattern': "tvpattern",
            'properties': ["file", "title", "episode", "season", "showtitle", "firstaired"],
            'fileidstmt': "select idfile from episode where idepisode = ?",
            'updstmt': "update episode set c18 = ? where idepisode = ?",
            'id': "episodeid"
        }
    }

    def __init__(self):
        xbmc.log("loading %s: version %s %s" % (__addonname__,
                                             __addonversion__,
                                             mode))
        if mode == None:
            self.showMenu()
        elif mode[0] == 'folder':
            foldername = args.get('foldername', None)
            if foldername != None:
                foldername = foldername[0]
            xbmc.log("using foldername %s" % foldername)
            if xbmcgui.Dialog().yesno(__addon__.getLocalizedString(33001), __addon__.getLocalizedString(33002), __addon__.getLocalizedString(33003)):
                if foldername == "movies":
                    self.doMovies()
                elif foldername == "tvshows":
                    self.doTvShows()

    #
    # Clean everything
    #
    def doAll(self):
        self.doMovies()
        self.doTvShows()

    # 
    # Clean movie folder
    # 
    def doMovies(self):
        xbmc.log("Running rename in movies")
        #Movies
        list = self.getList('movies')
        self.processList(list, self.types['movies'])
        xbmcgui.Dialog().ok(__addon__.getLocalizedString(33001), __addon__.getLocalizedString(33004))

    # 
    # Clean TV Shows
    #
    def doTvShows(self):
        xbmc.log("Running rename in TV shows")
        #TVShows
        shows = self.getList('tvshows')
        for s in shows:
            #Get episode list for the show
            episodes = self.getTvShowList('episodes', s['tvshowid'])
            self.processList(episodes, self.types['episodes'], s["file"])
        xbmcgui.Dialog().ok(__addon__.getLocalizedString(33001), __addon__.getLocalizedString(33004))

    #
    # Process an xbmc file list
    #
    def processList(self, list, type, showfolder=""):
        progress = xbmcgui.DialogProgress();
        progress.create(__addon__.getLocalizedString(33001), __addon__.getLocalizedString(33005))
        i = 0
        for s in list:
            if progress.iscanceled():
                # stop renaming
                return
            i += 1
            oldFileName, oldFileExtension = os.path.splitext(s["file"])
            oldPath = os.path.dirname(s["file"])
            filename = __addon__.getSetting(type['pattern'])
            for prop in type['properties']:
            	# Convert the value to a string
                if isinstance(s[prop], basestring):
                    val = unicode(s[prop])
                else:
                    val = str(s[prop])
                if prop == "season" or prop == "episode":
                    val = "%02d" % s[prop]
                filename = filename.replace("#" + prop.upper() + "#", val.replace(":", ""))
                filename = filename.replace("/", "-")
            	# TODO Sonderfall arrays (country, streamdetails)

            filename = filename.replace("#EXT#", oldFileExtension.lower())
            # Create a season folder for tv shows
            if showfolder != "" and __addon__.getSetting("seasonfolder"):
                folder = os.path.join(showfolder, "Season " + str(s["season"])) + os.sep
                if not xbmcvfs.exists(folder):
                	xbmcvfs.mkdirs(folder)
            else:
                folder = oldPath + os.sep

            newfile = os.path.join(folder, filename)
            newfile = newfile.encode("utf-8");
            # Display a progress. Shorten the names to make them fit inside the progress bar
            progress.update(100*i/len(list), self.shorten(s["file"]), self.shorten(newfile))
            # Rename the file
            if s["file"].encode("utf-8") != newfile:
                xbmc.log("renaming")
                if xbmcvfs.rename(s["file"], newfile):
                	# Rename successful. Update the entry in the database
                    xbmc.log("renaming successful. Updating database entry")
                    id = str(s[type["id"]])
                    c.execute(type["updstmt"], [newfile.decode("utf-8"), id])
                    cursor = conn.execute(type["fileidstmt"], [id])
                    for row in cursor:
                        fileid = row[0]
                        conn.execute("update files set strFilename = ? where idFile = ?", [filename, fileid])
                        # Check if the path already exists (a new path could be created by the season folder)
                        c2 = conn.execute("select idPath from path where strPath = ?", [folder])
                        data = c2.fetchall()
                        if len(data)>0:
                            idPath = data[0][0]
                        else:
                            c.execute("insert into path (strPath) values(?)", [folder])
                            idPath = c.lastrowid
                        # Update the path id in the file
                        conn.execute("update files set idPath = ? where idFile = ?", [idPath, fileid])
                    conn.commit()
                    xbmc.log("database entry updated")
                else:
                	# Rename failed. Show a notification about it
                    xbmcgui.Dialog().notification(__addon__.getLocalizedString(33001), __addon__.getLocalizedString(33006) % s["file"], xbmcgui.NOTIFICATION_WARNING, 5000)
            #sleep(0.1)
        progress.close()
    
    #
    # Shorten the string for the progress bar
    #
    def shorten(self, text):
        while len(text) > 50:
            text = re.sub(r"^.{5}", "..", text)
        return text

    #
    # Retrieve a list from xbmc
    #
    def getList(self, type):
        request = {
            "jsonrpc": "2.0",
            "method": self.types[type]['method'],
            "params": {
                "properties": self.types[type]['properties']
            },
            "id": 1
        }
        return self.getJsonRequest(request)["result"][type]

    def getTvShowList(self, type, showid):
        request = {
            "jsonrpc": "2.0",
            "method": self.types[type]['method'],
            "params": {
                "tvshowid": showid,
                "properties": self.types[type]['properties']
            },
            "id": 1
        }
        res = self.getJsonRequest(request)["result"]
        limits = res["limits"]
        if limits["total"] > 0:
            return res["episodes"]
        else:
            return []

    def callJson(self, type):
        request = {
            "jsonrpc": "2.0",
            "method": type,
            "id": 1
        }
        self.getJsonRequest(request)

    #
    # Retrieve a list from xbmc
    #
    def getJsonRequest(self, request):
        rpc_cmd = json.dumps(request)
        response = xbmc.executeJSONRPC(rpc_cmd)
        xbmc.log("Response: %r" % (response))
        result = json.loads(response)
        return result

    #
    # Creates a URL for a directory
    #
    def _build_url(self, query):
        return base_url + '?' + urllib.urlencode(query)

    # 
    # Display the default list of items in the root menu
    #
    def showMenu(self):
        # Movies
        url = self._build_url({'mode': 'folder', 'foldername': "movies"})
        li = xbmcgui.ListItem(__addon__.getLocalizedString(32011), iconImage=__addonicon__)
        #li.setProperty( "Fanart_Image", __addonfanart__ )
        li.addContextMenuItems( [], replaceItems=True )
        xbmcplugin.addDirectoryItem(handle=addon_handle, url=url, listitem=li, isFolder=True)
    
        # TV Shows
        url = self._build_url({'mode': 'folder', 'foldername': "tvshows"})
        li = xbmcgui.ListItem(__addon__.getLocalizedString(32012), iconImage=__addonicon__)
        #li.setProperty( "Fanart_Image", __addonfanart__ )
        li.addContextMenuItems( [], replaceItems=True )
        xbmcplugin.addDirectoryItem(handle=addon_handle, url=url, listitem=li, isFolder=True)

        xbmcplugin.endOfDirectory(addon_handle)

Main()