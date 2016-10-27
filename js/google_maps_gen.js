var infoWindow = new google.maps.InfoWindow(), marker, i, j;
var map = null;
var markers = [];
function PlaceEventsAndArtists(artists) {
    // Get user's location
    lat = 0
    lon = 0
    // if (navigator.geolocation) {
    //     navigator.geolocation.getCurrentPosition(drawUserCentredMap);
    // } else {
        // Set to Bristol
        lat = 51.4500;
        lon = -2.5833;
        drawMap();
    // }

    function drawUserCentredMap(position) {
        lat = position.coords.latitude;
        lon = position.coords.longitude;
        drawMap();
    }

    function drawMap() {
        user_position = new google.maps.LatLng(lat,lon);
        var mapOptions = {
            center: user_position,
            zoom: 6,
            mapTypeId: google.maps.MapTypeId.ROADMAP
        };
        map = new google.maps.Map(document.getElementById('map'), mapOptions);
        setMarkers();
        // Buttons for showing/hiding all events
        setEventToggleButtons();
    }

    // In the event of null coords, find coords by given address
    function getCoordsByCity(address){
        var cs = [0,0];
        var geocoder = new google.maps.Geocoder();
        address = address;
        geocoder.geocode({ 'address': address }, function (results, status) {
            if (status == google.maps.GeocoderStatus.OK) {
                cs[0] = results[0].geometry.location.lat();
                cs[1] = results[0].geometry.location.lng();
                return cs;
            }
            else {
                console.log("geocode error");
            }
        });
        return cs;
    }

    // Formats a givne date as a string given as dd/mm/yyyy
    function formatDate(given_date) {
        if(given_date == null) {
            return "";
        }
        var d = new Date(given_date);
        var dd = d.getDate();
        // +1 because of zero-indexing
        var mm = d.getMonth()+1;
        var yyyy = d.getFullYear();
        if(dd<10){
            dd = '0' + dd;
        }
        if(mm<10){
            mm = '0' + mm;
        }
        return ' - (' + dd + '/' + mm +'/' + yyyy + ')';
    }

    function getDateFromName(event_name) {
        var regExp = /\(([^)]+)\)/g;
        var matches = event_name.match(regExp);
        if(matches == null) {
            return null;
        }
        // Get last result (there may be other things stored in brackets)
        date = matches[matches.length-1];
        // Remove parentheses
        date = date.replace("(", "");
        date = date.replace(")", "");
        return date.replace(",", "");
    }

    // Returns colour of marker with respect to event date from current date
    function getMarkerColour(event_date) {
        if(event_date == null) {
            // Date unknown
            return "FF00FA";
        }
        var event_UTC = Date.parse(event_date);
        var current_UTC = Date.now();
        var day_diff = (event_UTC - current_UTC) / (1000*60*60*24);

        if(day_diff <= 7) {
            // Within a week
            return "00BA22";
        }
        else if(day_diff <= 14) {
            // Within two weeks
            return "9DFF00";
        }
        else if(day_diff <= 30) {
            // Within a month
            return "E5FF00";
        }
        else if(day_diff <= 60) {
            // Two months
            return "FFD000";
        }
        else if(day_diff <= 180) {
            // Six months
            return "FF8400";
        }
        else {
            return "FF4000";
        }
    }

    // Adds an event marker and infowindow on the map
    function addArtistEventMarkers(artist_data) {
        var artist_name = artist_data["name"];
        var artist_displayName = artist_data["displayName"];
        var event_data = artist_data["events"];

        for(k=0; k<event_data.length; k++) {
            var current_event = event_data[k];
            var m_lat = current_event["location"]["lat"];
            var m_lon = current_event["location"]["lng"];
            var position = new google.maps.LatLng(m_lat, m_lon);

            var time = current_event["time"]
            if(time == null) {
                // Get time value from date given in the event name
                time = getDateFromName(current_event["name"]);
            }
            // Set marker colour based on date of event
            var pinColor = getMarkerColour(time);
            var pinImage = new google.maps.MarkerImage("http://chart.apis.google.com/chart?chst=d_map_pin_letter&chld=%E2%80%A2|" + pinColor,
                new google.maps.Size(21, 34),
                new google.maps.Point(0,0),
                new google.maps.Point(10, 34));

            // Create Information window content
            var contentString = '<h3>' + artist_displayName + formatDate(time) + '</h3>';
            contentString += '<p>' + current_event["name"] + '</p>';
            contentString += '<a href=' + current_event["uri"] + '>' + current_event["uri"] + '</a>';

            // Create Marker
            var marker = new google.maps.Marker({
                position : position,
                map : map,
                icon: pinImage,
                title : current_event["name"],
                html : contentString
            });
            markers.push({"marker" : marker, "artist" : artist_name});

            google.maps.event.addListener(markers[markers.length-1]["marker"], 'click', function() {
                infoWindow.setContent(this.html);
                infoWindow.open(map, this);
            });
        }
    }

    // Draw event markers of the map
    function setMarkers() {
        for(var i=0; i<artists.length; i++){
            // Events for a single artist
            var artist_data = artists[i];
            // Add button for the artist
            addArtistButton(artist_data);
            // Add event markers
            addArtistEventMarkers(artist_data);
        }
    }

    function showArtistMarkers(artist_data) {
        name = artist_data["name"];
        if(!artist_data["hasEvents"]) {
            // Hasn't got any events, just change the class
            $("#"+escaped(name)).removeClass("artist_notshown").addClass("artist_noevents");
        }
        else {
            // It's got events, so add new markers
            addArtistEventMarkers(artist_data);
            $("#"+escaped(name)).removeClass("artist_notshown").addClass("artist_shown");
        }
    }

    function getArtistEventData(artist_name) {
        // Add loader icon
        loader_icon = "<img src=\"images\/artist-loader.gif\" />";
        $("#"+escaped(artist_name)).append(loader_icon);

        // Get data using AJAX
        $.ajax({
            url : "/artist_data?artist_name="+encodeURIComponent(artist_name),
            type : "GET",
            dataType : "json",
            success : function(json) {
                // Display map with markers
                showArtistMarkers(json);
                // Set local artist data
                for(var i=0; i<artists.length; i++) {
                    if(artists[i]["name"] == artist_name) {
                        artists[i] = json;
                    }
                }
            },
            error : function(xhr, status, errorThrown) {
                console.log(status + ": failed to get artist event data");
                $("#"+escaped(artist_name)).removeClass("artist_notshown").addClass("artist_noevents");
            },
            complete : function() {
                $("#"+escaped(artist_name) + " img").remove();
            }
        });
    }

    // Sets individual artist's event markers
    function setArtistMarkers(artist, show) {
        var name = artist["name"];
        if(show) {
            // Check if event markers are already created for the artist
            var events_exist = false;
            ms = [];
            for(i = 0; i < markers.length; i++) {
                if(markers[i]["artist"] == name) {
                    events_exist = true;
                    // Set map for the marker
                    markers[i]["marker"].setMap(map);
                }
            }
            // If no markers exist for the artist, check if there is any by fetching from backend
            if(!events_exist) {
                getArtistEventData(name);
            }
            else {
                // Events exist and are displayed, so set the class
                $("#"+escaped(name)).removeClass("artist_notshown").addClass("artist_shown");
            }
        }
        else {
            for(i=0; i<markers.length; i++) {
                if(markers[i]["artist"] == name) {
                    // Unset the map from the marker
                    markers[i]["marker"].setMap(null);
                }
            }
            $("#"+escaped(name)).removeClass("artist_shown").addClass("artist_notshown");
        }
        artist["shown"] = show;
    }

    function addArtistListener(artist) {
        $("#" + escaped(artist["name"])).on("click", function(){
            if(artist["hasEvents"]) {
                // Set 'shown' to the opposite value
                setArtistMarkers(artist, !artist["shown"]);
            }
        });
    }

    // Used for making strings acceptable to be set as a DOM id
    function escaped(s) {
        // Remove all non-alphanumeric characters
        return s.replace(/[^\w]/g, "");
    }

    function addArtistButton(artist) {
        var classname = "artist_notshown";
        if(artist["shown"] == true) {
            classname = "artist_shown";
        }
        else if(artist["hasEvents"] == false) {
            classname = "artist_noevents";
        }
        button = "<span id=\"" + escaped(artist["name"]) + "\" class=\"" + classname + "\">";
        button += artist["displayName"] + "</span>";
        $("#artists-table").append(button);

        // Add listener
        addArtistListener(artist);
    }

    // Add listeners to the event toggle buttons
    function setEventToggleButtons() {
        $("#but_showAllEvents").on("click", function(){
            for(var i=0; i<artists.length; i++) {
                if(artists[i]["hasEvents"]) {
                    setArtistMarkers(artists[i], true);
                }
            }
        });

        $("#but_hideAllEvents").on("click", function(){
            for(var i=0; i<artists.length; i++) {
                if(artists[i]["hasEvents"]) {
                    setArtistMarkers(artists[i], false);
                }
            }
        });
    }
}

function run() {
    $.ajax({
        url : "/event_data",
        type : "GET",
        dataType : "json",
        success : function(json) {
            // Append 'shown' property to artist data and set appropriately
            for(var i=0; i<json.length; i++) {
                json[i]["shown"] = false;
                if(json[i]["events"].length > 0) {
                    json[i]["shown"] = true;
                }
            }
            // Hide the loader image
            $("#map-loading").remove();
            // Display map with markers
            PlaceEventsAndArtists(json);
        },
        error : function(xhr, status, errorThrown) {
            console.log("Error with AJAX in getting event data")
        }
    });
}

$(document).ready(run);
