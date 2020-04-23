
from sos import describeSensor, CALL_DESCRIBE_SENSOR
import templates, basic
from templates import getInsertSensorSoRad
from templates import constructTestDict
import configparser


def ConnectToSOS(auth, sensor):

    basic.authKey = auth
    returnedResult = describeSensor(sensor, auth)
    print(returnedResult)
    if("InvalidParameterValue" in returnedResult):
        
        print("Sensor is not in SOS server.")
        print("Inserting sensor...")
        sensorDict = constructTestDict(sensor)
        xml = getInsertSensorSoRad(sensorDict)
        result = basic.makeCall( xml, sensorDict, auth )        
    else:
        print("I think sensor is in there")
    # Describe sensor (check if sensor is there)
    # If sensor not there, then insert sensor - take output template (pass in unique id (procedure)) (render simple template function)
    # Get result template (check if result template is there) (give unique name: unique string based on format of template)
    # Insert result template if not there

def SendToSOS():
    pass
    # Insert result

if __name__ == '__main__':


    # args = parse_args()
    # conf = read_config(args.config_file)

    # sos = conf['SOS']
    # Auth = sos.get('Auth')
    # print(Auth)

    config = configparser.ConfigParser()
    config.read('../config.ini')     

    auth = config.get('SOS', 'Auth')
    uniqueID = config.get('SOS', 'UniqueID')
    # name = config.get('SOS', 'Auth')
    # user = config.get('SOS', 'Auth')
    # password = config.get('SOS', 'Auth')

    ConnectToSOS(auth, uniqueID)
