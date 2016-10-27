from google.appengine.ext import db

class Artist(db.Model):
    name = db.StringProperty(required=True)
    displayName = db.StringProperty()
    songkick_id = db.StringProperty()
    events = db.BlobProperty()
    hasEvents = db.BooleanProperty()
    timestamp = db.DateTimeProperty()
