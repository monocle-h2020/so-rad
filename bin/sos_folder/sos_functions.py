
from sos import describeSensor, CALL_DESCRIBE_SENSOR, getResultTemplate, insertResultTemplate, deleteSensor
import templates, basic
from templates import getInsertSensorSoRad
from templates import constructTestDict
import configparser


def CheckAndInsertResultTemplate(identifier, offering, observedProperty, auth):
    """
    This checks if the result template exists in SOS by calling GetResultTemplate
    If the returned response contains invalid flags then that signals the template does not exist.
    An attempt will then be made to insert the result template using the provided parameters.
    """
    print("Checking if result template is uploaded.")
    print("Fetching result template...")

    resultTemplate = getResultTemplate(identifier, observedProperty)
    # print(checkResultTemplate)

    if("InvalidParameterValue" in resultTemplate or "InvalidPropertyOfferingCombination" in resultTemplate):
        print("No template found, inserting template.")
        resultTemplate = insertResultTemplate(identifier, offering, observedProperty, auth)
    else:
        print("Result template exists:")
    return resultTemplate


def DeleteSensor(procedure, auth):
    response = deleteSensor(procedure, auth)
    if("the parameter 'procedure' is invalid" in response):
        print("Procedure parameter was invalid, please check your values.")
    else:
        print("Sensor successfully deleted.")

def ConnectToSOS(auth, sensor, observableProperty, offering, altitude, feature, procedure, latitude, longitude):

    basic.authKey = auth

    deleteSensor(procedure, basic.authKey)    

    returnedResult = describeSensor(procedure, auth)
    if(returnedResult is None):
        print("Nothing returned, potential issue when inserting sensor step was carried out.")
    elif("InvalidParameterValue" in returnedResult):
        print("Invalid procedure used, checking if sensor is in SOS server.")
        print("Inserting sensor...")

        sensorDict = constructTestDict(sensor, observableProperty, offering, altitude, feature, procedure, latitude, longitude)
        xml = getInsertSensorSoRad(sensorDict)
        #print(xml)
        result = basic.makeCall( xml, sensorDict, auth ) 
        #print(result)

        returnedResult = describeSensor(procedure, auth)
        #print(returnedResult)
        if("InvalidParameterValue" in returnedResult or returnedResult is None):
            print("Sensor insert failed, please check your template settings.")
        elif("The offering with the identifier" in result and "still exists in this service" in result and "not allowed to insert more than one procedure to an offering" in result):
            print("Sensor is already in SOS server, try checking your sensor values.")
        else:
            print("Insert sensor was successful.")
            returnedTemplate = CheckAndInsertResultTemplate(procedure, offering, observableProperty, auth)
            if("<ns0:acceptedTemplate>" in returnedTemplate):
                print("Template successfully inserted.")
            else:
                print("Template not inserted successfully, please check your template parameters.")
                print(returnedTemplate)
    else:
        print("Sensor is in SOS.")
        returnedTemplate = CheckAndInsertResultTemplate(procedure, offering, observableProperty, auth)
        if("<ns0:acceptedTemplate>" in returnedTemplate):
            print("Template successfully inserted.")
        else:
            print("Template not inserted successfully, please check your template parameters.")
            print(returnedTemplate)


def SendToSOS():
    pass
    # Insert result

if __name__ == '__main__':

    config = configparser.ConfigParser()
    config.read('../config.ini')     

    auth = config.get('SOS', 'Auth')

    uniqueID = config.get('SOS', 'UniqueID')
    observableProperty = config.get('SOS', 'observableProperty')
    offering = config.get('SOS', 'offering')
    altitude = config.get('SOS', 'altitude')
    feature = config.get('SOS', 'feature')
    procedure = config.get('SOS', 'procedure')
    latitude = config.get('SOS', 'latitude')
    longitude = config.get('SOS', 'longitude')

    ConnectToSOS(auth, uniqueID, observableProperty, offering, altitude, feature, procedure, latitude, longitude)
