
from sos import describeSensor, CALL_DESCRIBE_SENSOR, getResultTemplate
import templates, basic
from templates import getInsertSensorSoRad
from templates import constructTestDict
import configparser


def ConnectToSOS(auth, sensor):

    
    basic.authKey = auth

    returnedResult = describeSensor("https://monocle-h2020.eu/SWE/Procedures/soradtest", auth)

    if(returnedResult is None):
        print("Nothing returned, potential issue with inserting sensor")
    elif("InvalidParameterValue" in returnedResult):
        print("Invalid procedure used, checking if sensor is in SOS server")
        print("Inserting sensor...")
        sensorDict = constructTestDict("soradTestSensor")
        xml = getInsertSensorSoRad(sensorDict)
        result = basic.makeCall( xml, sensorDict, auth ) 
        print(result)       
    # print(result)
    # elif(returnedResult is None):
    #     print("Sensor is in SOS server")
    
    # value = getResultTemplate('my-sorad-sensor', 'blob-of-water')
    # print(value)
    # if("InvalidPropertyOfferingCombination" in value):
    #     print("Result template not available.")
    #     print("Inserting result template...")


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
