import json
import requests
from datetime import datetime
import time
import sqlite3

db = sqlite3.connect('monocle_sensor.db')
monocle_cursor = db.cursor()
monocle_cursor.row_factory = sqlite3.Row

insertObservationPayload = {
  "request": "InsertObservation",
  "service": "SOS",
  "version": "2.0.0",
  "offering": "http://monocle-h2020.eu/GPS_PLATFORM",
  "observation": {
    "identifier": {
      "value": "http://monocle-h2020.eu/GPS_PLATFORM/<<timestamp>>",
      "codespace": "http://www.opengis.net/def/nil/OGC/0/unknown"
    },
    "type": "http://www.opengis.net/def/observationType/OGC-OM/2.0/OM_Measurement",
    "procedure": "http://monocle-h2020.eu/SHIPBOARD_PLATFORM",
    "observedProperty": "http://monocle-h2020.eu/HEADING",
    "featureOfInterest": {
      "identifier": {
        "value": "http://monocle-h2020.eu/GPS_PLATFORM_FEATURE",
        "codespace": "http://www.opengis.net/def/nil/OGC/0/unknown"
      },
      "name": [
        {
          "value": "235017045",
          "codespace": "http://www.opengis.net/def/nil/OGC/0/unknown"
        }
      ],      
      "geometry": {
        "type": "Point",
        "coordinates": [
          9999,
          9999
        ],
        "crs": {
          "type": "name",
          "properties": {
            "name": "EPSG:4326"
          }
        }
      }
    },
    "phenomenonTime": "2019-03-07T14:29:40Z",
    "resultTime": "2019-03-07T14:29:40Z",
    "result": {
      "uom": "http://www.opengis.net/def/uom/OGC/1.0/degree",
      "value": 63.39077417
    }
  }
}


def insertObservation(server, _date, _lat, _lon, value):
    """Adds the observation data into the insertObservationPayload json object to send to the SOS proxy server
    
    :param server: The SOS proxy URL
    :type server: string
    :param _date: The date and time the data was recorded
    :type _date: string
    :param _lat: The latitude of the data point
    :type _lat: float
    :param _lon: The longitude of the data point
    :type _lon: float
    :param value: The heading of the sun
    :type value: float
    """

    _now = time.time()
    insertObservationPayload['observation']['result']['value'] = float(value)
    insertObservationPayload['observation']['featureOfInterest']['geometry']['coordinates'] = [float(_lat),float(_lon)]
    insertObservationPayload['observation']['resultTime'] = _date
    insertObservationPayload['observation']['phenomenonTime'] = _date
    insertObservationPayload['observation']['identifier']['value'] = "http://monocle-h2020.eu/GPS_PLATFORM/%.5f" % _now
    insertObservationPayload['observation']['featureOfInterest']['identifier']['value'] = "http://monocle-h2020.eu/GPS_PLATFORM_FEATURE/%.5f" % _now
    print("attempting insert")
    print(insertObservationPayload)
    resp = requests.post(server, json=insertObservationPayload)
    print(resp.json())





if __name__ == '__main__':
    sos_url = "https://sosproxy.monocle-h2020.eu/api/sos_proxy/2087496c5f8456a2736ba6e8d77e354b/not_needed_but_need_to_remove_from_api"
    #insertSensor(sos_url)
    #insertObservation(sos_url)
    # example line 
    # Mar  7 14:29:53 raspberrypi motor_controller_auto[602]: |Update rate=1|Heading=63.16001154939312|GPS 1 datetime=2019-03-07 14:29:42|GPS 2 datetime=2019-03-07 14:29:42|PC datetime=2019-03-07 14:29:42.358076|GPS 1 Lat=50.3662548|GPS 1 Lon=-4.148388066666667|GPS 2 Lat=50.36627636666667|GPS 2 Lon=-4.14832125
    holder = []
    #with open("motor_controller_auto_test2_1Hz_7m.log") as infile:
    
    monocle_cursor.execute('SELECT rowid, * FROM GPS_Data')
    l = monocle_cursor.fetchall()

    row_id = 0
    for row in l:

        #if row_id != 0:
        #    monocle_cursor.execute('DELETE FROM GPS_Data WHERE rowid=?', (row_id,))

        row_id = row["rowid"]
        # print(row_id)
        # print(type(row_id))

        if row["heading"] and row["gps2_longitude"] and row["gps2_latitude"] and row["gps2_datetime"]:
            heading = row["heading"]
            lon = row["gps2_longitude"]
            lat = row["gps2_latitude"]
            try:
                date = datetime.strptime(row["gps2_datetime"], "%Y-%m-%d %H:%M:%S.%f").strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            except ValueError:
                date = datetime.strptime(row["gps2_datetime"], "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%dT%H:%M:%SZ")

        holder.append( {
            'date' : date,
            'lat' : lat,
            'lon' : lon,
            'heading' : heading,
            'row_id' : row_id
        })
    
    #print(holder)

    count = 0

    for item in holder:
        #print(item['date'])
        #if count >= 100 :
        insertObservation(sos_url,item['date'], item['lat'], item['lon'], item['heading'])
        # a simple sleep to ease the system stress may not be needed, we will test to find out
        
        monocle_cursor.execute('DELETE FROM GPS_Data WHERE rowid=?', (item['row_id'],))
        db.commit()

        time.sleep(0.1)
        count = count + 1



# example payloads for requesting metadata to test ingest

# {
#   "request": "GetObservation",
#   "service": "SOS",
#   "version": "2.0.0",
#   "procedure": "http://monocle-h2020.eu/SHIPBOARD_PLATFORM",
#   "offering": "http://monocle-h2020.eu/GPS_PLATFORM",
#   "observedProperty": "http://monocle-h2020.eu/HEADING"
# }


# {
#   "request": "DescribeSensor",
#   "service": "SOS",
#   "version": "2.0.0",
#   "procedure": "http://monocle-h2020.eu/SHIPBOARD_PLATFORM",
#   "procedureDescriptionFormat": "http://www.opengis.net/sensorML/1.0.1"
# }






















    