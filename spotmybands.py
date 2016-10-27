## This web application has been created as part of the assessment criteria for
## COMSM0010 Cloud Computing at the University of Bristol
## Designed and created by Nick Phillips

import os
import urllib
import json
import logging
import jinja2
import webapp2

from google.appengine.api import users
from google.appengine.api import urlfetch
from google.appengine.api import memcache
from google.appengine.ext import db
from webapp2_extras import sessions
from datetime import datetime, timedelta
from datastoreConfig import Artist

f = open('keys.json', 'r')
KEYS = json.loads(f.read())
f.close()

DEV_MODE = 'development' in os.environ.get('SERVER_SOFTWARE', '').lower()

JINJA_ENVIRONMENT = jinja2.Environment(
    loader = jinja2.FileSystemLoader(os.path.dirname(__file__)),
    extensions = ['jinja2.ext.autoescape'],
    autoescape = True)

# Spotify vals
spotify_id = str(KEYS["spotify_client_id"])
spotify_secret = str(KEYS["spotify_secret"])

# Callback route is different between prod and dev.
spotify_callback = "http://spotmybands.com/access_token"
if DEV_MODE:
    spotify_callback = "http://localhost:8080/access_token"

# Songkick vals
SONGKICK_API_KEY = str(KEYS["songkick"])
# Store songkick data for 24 hours max (given in seconds)
# Checks are done every 12 hours, so set timestamp to 12 hours
SONGKICK_TIMEOUT = 60*60*12

# Google Maps
GOOGLE_API_KEY = str(KEYS["google_maps"])

# Used for managing session data for each request handler
class BaseHandler(webapp2.RequestHandler):
    def dispatch(self):
        # Get a session store for this request.
        self.session_store = sessions.get_store(request=self.request)
        try:
            # Dispatch the request.
            webapp2.RequestHandler.dispatch(self)
        finally:
            # Save all sessions.
            self.session_store.save_sessions(self.response)

    @webapp2.cached_property
    def session(self):
        # Returns a session using the default cookie key. Doesn't work properly when backend is set to securecookie
        return self.session_store.get_session(backend="memcache")

# Connect SpotMyBands to a user's Spotify account
class Authenticate(BaseHandler):
    def get(self):
        fields = {
            "client_id" : spotify_id,
            "response_type" : "code",
            "redirect_uri" : spotify_callback,
            "scope" : "user-library-read playlist-read-private",
            "show_dialog" : "true"
        }
        url = "https://accounts.spotify.com/authorize?"
        data = urllib.urlencode(fields)
        self.redirect(url + data)

# In case of authorisation errors
class AccessDenied(BaseHandler):
    def get(self):
        template = JINJA_ENVIRONMENT.get_template('access_denied.html')
        self.response.write(template.render())

# Homepage for the website, with information on what the site does
class Welcome(BaseHandler):
    def get(self):
        values = {
            "current_page" : "welcome"
        }
        template = JINJA_ENVIRONMENT.get_template('index.html')
        self.response.write(template.render(values))

class GetArtistData(BaseHandler):
    def get(self):
        artist_name = self.request.get("artist_name")
        artist_found = False
        # Find artist entry in event_data
        for artist in self.session.get("event_data"):
            if artist["name"] == artist_name:
                SongkickGetArtistEvents(artist)
                self.response.out.write(json.dumps(artist))
                artist_found = True
        # Artist not found - return error
        if not artist_found:
            self.response.set_status(500)

# Called by the frontend through AJAX
class GetEventData(BaseHandler):
    def get(self):
        if(not self.session.get("event_data")):
            # Get access token for accessing Spotify API
            self.access_token = self.session.get("spotify_access_token")
            self.user_id = self.session.get("user_id")

            # Get playlists
            if(not self.session.get("playlists")):
                self.session["playlists"] = self.SpotifyGetPlaylists()
            playlists = self.session.get("playlists")

            # Get artists
            if(not self.session.get("artists")):
                self.session["artists"] = self.SpotifyGetArtistsFromPlaylists(playlists)
            artists = self.session.get("artists")
            # Get event data
            self.session["event_data"] = self.SongkickGetEvents(artists)
        self.response.out.write(json.dumps(self.session.get("event_data")))

    # Returns a user's playlist data
    def SpotifyGetPlaylists(self):
        url = "https://api.spotify.com/v1/users/" + self.user_id + "/playlists"
        result = urlfetch.fetch(url=url,
                method=urlfetch.GET,
                headers={"Authorization" : "Bearer " + self.access_token})
        return json.loads(result.content)

    # Returns all the artists from all of a user's playlists
    def SpotifyGetArtistsFromPlaylists(self, playlist_data):
        artists = []
        for pl_data in playlist_data["items"]:
            # For each playlist, make a request to the track list
            url = pl_data["tracks"]["href"]
            # We only need artist data from each track
            fields = {
                "fields" : "items(track(artists))"
            }
            result = urlfetch.fetch(url=url,
                    payload=urllib.urlencode(fields),
                    method=urlfetch.GET,
                    headers={"Authorization" : "Bearer " + self.access_token})
            data = json.loads(result.content)["items"]
            for j in range(0,len(data)):
                # For each track
                track_artists_data = data[j]["track"]["artists"]
                for k in range(0,len(track_artists_data)):
                    # For each artist who contributed to the track, create dict and get their name
                    artist = {
                        "name" : "",
                        "displayName" : "",
                        "songkick_id" : None,
                        "events" : [],
                        "hasEvents" : True
                    }
                    artist["name"] = track_artists_data[k]["name"]
                    # Unless explicitly set, the display name should initially match the name
                    artist["displayName"] = artist["name"]
                    # Add to artists list, with redundancy checking
                    if(artist not in artists):
                        artists.append(artist)
        return artists

    # Fetches and populates event data for each artist entry
    def SongkickGetEvents(self, artists):
        # Counter for fetched artists
        num_fetched_artists = 0
        for artist in artists:
            SongkickGetArtistEvents(artist)
            num_fetched_artists += 1
            # Stop fetching after 10 artists - avoids long wait times for client
            if num_fetched_artists == 10:
                break
        return artists

# Returns value from memcache or Datastore, failing that then returns None
def GetFromStorage(key_val):
    # Check memcache first
    data = memcache.get(key_val)
    if(data is not None):
        return data
    else:
        entries = db.GqlQuery("SELECT * FROM Artist WHERE name = :1", key_val)
        for entry in entries:
            # Check timestamp - delete and renew if it is old
            if entry.timestamp <= datetime.utcnow():
                # Remove from Datastore, fetch values again
                entry.delete()
                return None
            data = {}
            data["name"] = entry.name
            data["displayName"] = entry.displayName
            data["songkick_id"] = entry.songkick_id
            data["events"] = json.loads(entry.events)
            data["hasEvents"] = entry.hasEvents
            return data
    # Can't find it
    return None

# Returns a boolean to indicate if data was stored successfully
def AddToStorage(key_val, data):
    isStored = False
    # Add to memcache
    isStored = memcache.add(key_val, data, SONGKICK_TIMEOUT)
    artist_entry = Artist(name=key_val)
    artist_entry.displayName = data["displayName"]
    artist_entry.songkick_id = data["songkick_id"]
    artist_entry.events = json.dumps(data["events"])
    artist_entry.hasEvents = data["hasEvents"]
    # Time limit on datastore - set to 24 hours from current time
    artist_entry.timestamp = datetime.utcnow() + timedelta(hours=24)

    isStored = artist_entry.put()
    return isStored

# Public method which obtains all event data for a single artist
# Returns true if artist event data is fetched form API; false otherwise
# Argument 'artist' can be assigned within this function's scope
def SongkickGetArtistEvents(artist):
    fetched = False
    artist_name = artist["name"]
    # Check storage to avoid API calls
    mem_artist = GetFromStorage(artist_name)
    if(mem_artist is not None):
        logging.debug("obtained artist data from storage!")
        # Copy parameters - Python cannot directly assign dicts
        artist["displayName"] = mem_artist["displayName"]
        artist["songkick_id"] = mem_artist["songkick_id"]
        artist["events"] = mem_artist["events"]
        artist["hasEvents"] = mem_artist["hasEvents"]
        # Retrieval is quick, don't count it as being fetched from API
        return False

    # Get artist ID
    query = artist_name.replace(" ", "+") # GET requests don't take spaces
    url = "http://api.songkick.com/api/3.0/search/artists.json?query="+query+"&apikey="+SONGKICK_API_KEY
    result = urlfetch.fetch(url=url,
            method=urlfetch.GET)
    artist_data_results = json.loads(result.content)["resultsPage"]

    # Exception handling
    if(result.status_code != 200 or len(artist_data_results["results"]) == 0):
        logging.error("Artist %s cannot be found" %(artist_name))
        # Add entry to storage with no event data
        artist["hasEvents"] = False
        if not AddToStorage(artist_name, artist):
            logging.error("Storage failed on adding artist which can't be found on Songkick")
        # The artist cannot be found
        return False

    # NOTE: this assumes that the first search result is the one we want
    artist_data = artist_data_results["results"]["artist"][0]
    artist["displayName"] = artist_data["displayName"]
    # Songkick ID for artist
    artist["songkick_id"] = str(artist_data["id"])

    # Get event data using ID
    url = "http://api.songkick.com/api/3.0/artists/"+artist["songkick_id"]+"/calendar.json?apikey="+SONGKICK_API_KEY
    result = urlfetch.fetch(url=url,
            method=urlfetch.GET)
    if(result.status_code != 200):
        logging.error("Error in getting Songkick Events for artist %s" %(artist_name))
        artist["hasEvents"] = False
        # Add data to storage
        if not AddToStorage(artist_name, artist):
            logging.error("Storage failed on adding artist event data")
        return False
    event_data_results = json.loads(result.content)["resultsPage"]["results"]
    if(len(event_data_results) > 0):
        event_data = event_data_results["event"]
        for event in event_data:
            event_uri = event["uri"]
            event_name = event["displayName"]
            event_time = event["start"]["datetime"]
            event_location = event["location"]
            artist["events"].append({"uri" : event_uri,
                                    "name" : event_name,
                                    "time" : event_time,
                                    "location" : event_location})
        fetched = True
    else:
        artist["hasEvents"] = False
    # Add to storage
    if not AddToStorage(artist_name, artist):
        logging.error("Storage failed on adding artist event data")
    return fetched

# Used for getting the access token used for Spotify API
class AccessToken(BaseHandler):
    def get(self):
        # Check for errors (e.g. access_denied)
        if(self.request.get("error")):
            self.redirect("/access_denied")
        else:
            # Obtain access token
            self.session["spotify_access_token"] = self.SpotifyAuth(self.request)

            # Clear cached event, playlist, and artist data
            self.session["event_data"] = None
            self.session["playlists"] = None
            self.session["artists"] = None
            self.session["user_id"] = None

            self.redirect("/main")

    # Returns the access token used for contacting spotify's API
    def SpotifyAuth(self,req):
        code = req.get("code")
        state = req.get("state")

        # Make POST request for access and refresh tokens
        fields = {
            "grant_type" : "authorization_code",
            "code" : code,
            "redirect_uri" : spotify_callback,
            "client_id" : spotify_id,
            "client_secret" : spotify_secret
        }
        url = "https://accounts.spotify.com/api/token"
        field_data = urllib.urlencode(fields)
        result = urlfetch.fetch(url=url,
                payload=field_data,
                method=urlfetch.POST,
                headers={'Content-Type': 'application/x-www-form-urlencoded'})
        return json.loads(result.content)["access_token"]

# Shows the map and event info using a user's Spotify data
class MainPage(BaseHandler):
    def get(self):
        self.access_token = self.session.get("spotify_access_token")

        if(not self.session.get("user_id")):
            self.session["user_id"] = self.SpotifyGetUserID()
        self.user_id = self.session.get("user_id")

        values = {
            "username" : self.user_id,
            "current_page" : "main",
            "google_api_key" : GOOGLE_API_KEY
        }
        template = JINJA_ENVIRONMENT.get_template('main.html')
        self.response.write(template.render(values))

    # Returns the Spotify ID of the current user
    def SpotifyGetUserID(self):
        url = "https://api.spotify.com/v1/me"
        result = urlfetch.fetch(url=url,
                method=urlfetch.GET,
                headers={"Authorization" : "Bearer " + self.access_token})
        user_id = json.loads(result.content)["id"]
        return user_id
    '''
    # Returns a user's saved track data
    def SpotifyGetTracks(self):
        url = "https://api.spotify.com/v1/me/tracks"
        result = urlfetch.fetch(url=url,
                method=urlfetch.GET,
                headers={"Authorization" : "Bearer " + self.access_token})
        return json.loads(result.content)
    '''




config = {}
config["webapp2_extras.sessions"] = {
    "secret_key" : "pass1234"
}
config["webapp2_extras.auth"] = {'session_backend': 'memcache'}

app = webapp2.WSGIApplication([
    ('/', Welcome),
    ('/auth', Authenticate),
    ('/access_token', AccessToken),
    ('/main', MainPage),
    ('/event_data', GetEventData),
    ('/artist_data', GetArtistData),
    ('/access_denied', AccessDenied)
], config=config, debug=True)
