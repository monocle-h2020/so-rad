
from sos import describeSensor, CALL_DESCRIBE_SENSOR, getResultTemplate, insertResultTemplate, deleteSensor
import templates, basic
from templates import getInsertSensorSoRad
from templates import constructTestDict
import configparser


def CheckAndInsertResultTemplate(identifier, offering, observedProperty):
    """
    This checks if the result template exists in SOS by calling GetResultTemplate
    If the returned result contains invalid flags then that signals the template does not exist.
    An attempt will then be made to insert the result template using the provided parameters.
    """
    print("Checking if result template is uploaded.")
    print("Fetching result template...")

    resultTemplate = getResultTemplate(identifier, observedProperty)
    #print(resultTemplate)

    #resultTemplate = getResultTemplate('sorad-test-sensor5', 'https://monocle-h2020.eu/SWE/observableProperty/Lake4')
    if("InvalidParameterValue" in resultTemplate or "InvalidPropertyOfferingCombination" in resultTemplate):
        print("No template found, inserting template.")
        resultTemplate = insertResultTemplate(identifier, offering, observedProperty, auth)
    else:
        print("Result template exists:")
    print(resultTemplate)
    return resultTemplate


def ConnectToSOS(auth, sensor):

    
    basic.authKey = auth

    #deleteSensor('https://monocle-h2020.eu/SWE/Procedures/soradtest3', basic.authKey)
    #insertResultTemplate('soradTestSensor', 'the-sorad-sensor', 'blob-of-water', auth)
    

    # sensorDict = constructTestDict(sensor)
    # xml = getInsertSensorSoRad(sensorDict)
    # print(xml)
    # result = basic.makeCall( xml, sensorDict, auth ) 
    # print(result)

    # returnedResult = describeSensor("https://monocle-h2020.eu/SWE/Procedures/soradtest5", auth)
    # print(returnedResult)





    returnedResult = describeSensor("https://monocle-h2020.eu/SWE/Procedures/soradtest5", auth)
    if(returnedResult is None):
        print("Nothing returned, potential issue when inserting sensor step was carried out.")
    elif("InvalidParameterValue" in returnedResult):
        print("Invalid procedure used, checking if sensor is in SOS server.")
        print("Inserting sensor...")

        sensorDict = constructTestDict(sensor)
        xml = getInsertSensorSoRad(sensorDict)
        #print(xml)
        result = basic.makeCall( xml, sensorDict, auth ) 
        #print(result)

        returnedResult = describeSensor("https://monocle-h2020.eu/SWE/Procedures/soradtest5", auth)
        
        if("InvalidParameterValue" in returnedResult or returnedResult is None):
            print("Sensor insert failed, please check your template settings.")
        elif("The offering with the identifier" in result and "still exists in this service" in result and "not allowed to insert more than one procedure to an offering" in result):
            print("Sensor is already in SOS server, try checking your sensor values.")
        else:
            returnedTemplate = CheckAndInsertResultTemplate('soradTestSensor5', 'sorad-test-sensor5', 'Lake5')
            #print(returnedResult)
    else:
        print("Sensor is in SOS.")
        returnedTemplate = CheckAndInsertResultTemplate('soradTestSensor5', 'sorad-test-sensor5', 'Lake5')
        print(returnedResult)
        

def SendToSOS():
    pass
    # Insert result

if __name__ == '__main__':

    config = configparser.ConfigParser()
    config.read('../config.ini')     

    auth = config.get('SOS', 'Auth')
    uniqueID = config.get('SOS', 'UniqueID')

    ConnectToSOS(auth, uniqueID)
