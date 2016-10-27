## Used for executing cron job for removing old artist data entries
## This is kept separate from main app because only Admins should access this

import os
import urllib
import logging
import webapp2

from google.appengine.api import urlfetch
from google.appengine.ext import db
from datetime import datetime, timedelta
from datastoreConfig import Artist

# Used for removing datstore artist entries that are older than a specified time
class CheckDS(webapp2.RequestHandler):
    def get(self):
        # Check timestamp of all datastore entries and remove old ones
        artists = db.GqlQuery("SELECT * FROM Artist")
        for artist in artists:
            if artist.timestamp <= datetime.utcnow():
                logging.info("Deleted artist: " + artist.name)
                artist.delete()

app = webapp2.WSGIApplication([
    ('/datastore_check', CheckDS)
])
