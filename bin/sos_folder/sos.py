"""
sos accessor functions
"""
CALL_DESCRIBE_SENSOR        = 'describeSensor.xml'
CALL_GET_RESULT             = 'getResult.xml'
CALL_GET_RESULT_TEMPLATE    = 'getResultTemplate.xml'
CALL_INSERT_SENSOR          = 'insertSensor.xml'
CALL_INSERT_RESULT_TEMPLATE = 'insertResultTemplate.xml'
CALL_INSERT_RESULT          = 'insertResult.xml'
CALL_DELETE_SENSOR          = 'deleteSensor.xml'

DEFAULT_SEPARATOR_BLOCK = '@'
DEFAULT_SEPARATOR_TOKEN = '#'

import templates
import basic

def __makeCall( template: str, params: dict, useProxy: bool = False ) -> str:
    """
    Construct the xml body using the provided template and sensor parameters
    Make the call to the SOS server and return the response
    """
    body = templates.renderSimpleTemplate( template, params )
    return basic.makeCall( body, template, useProxy )

def describeSensor( sensor: str , AuthKey: str) -> str:
    """
    makes a describe sensor call for the passed sensor
    """
    return __makeCall( CALL_DESCRIBE_SENSOR, { 'procedure': sensor }, AuthKey )


def getResult( offering: str, observedProperty: str ) -> str:
    """
    makes a getResult call for the offering and observed property
    """
    return __makeCall(
        CALL_GET_RESULT, {
            'offering': offering,
            'observedProperty': observedProperty })

def getResultTemplate( offering: str, observedProperty: str ) -> str:
    """
    makes a getResult call for the offering and observed property
    """
    return __makeCall(
        CALL_GET_RESULT_TEMPLATE, {
            'offering': offering,
            'observedProperty': observedProperty })

# def insertResult( template: str, values: list , auth) -> str:
#     """
#     inserts values using the supplied template, with the following assumptions:

#     1) token separator is always DEFAULT_SEPARATOR_TOKEN
#     2) block separator is always DEFAULT_SEPARATOR_BLOCK
#     3) the provided list (values) is of the correct shape for the template
#     """
#     resultValuesList = map( lambda x: DEFAULT_SEPARATOR_TOKEN.join( x ), values )
#     resultValues     = DEFAULT_SEPARATOR_BLOCK.join( resultValuesList )

#     resultValues = "{}{}{}{}".format(
#         len(values),
#         DEFAULT_SEPARATOR_BLOCK,
#         resultValues,
#         DEFAULT_SEPARATOR_BLOCK)
    
#     params = {
#         'template': template,
#         'resultValues' : resultValues }
#     return __makeCall( CALL_INSERT_RESULT, params, auth )

def insertResultTemplate(resultTemplateName, identifier, offering, observedProperty, useProxy) -> str:
    """
    Inserts the result template for a specific sensor into SOS.
    """
    from templates import checkDictValues, constructResultTemplateDict
    dictValues = constructResultTemplateDict(resultTemplateName, identifier, offering, observedProperty)
    parametersExist = checkDictValues(dictValues)
    if(parametersExist is True):
        body = templates.renderSimpleTemplate( CALL_INSERT_RESULT_TEMPLATE, dictValues ) 
        print(body)
        print("   ")
        print("   ")
        response = basic.makeCall( body, CALL_INSERT_RESULT_TEMPLATE, useProxy )  
    else:
        print("Missing template parameters, please check you have set up the dictionary correctly.")
    return response


def deleteSensor(procedure, useProxy) -> str:
    """Function to delete a sensor in SOS"""
    tempDictionary = {
        "procedure": procedure
    }
    body = templates.renderSimpleTemplate(CALL_DELETE_SENSOR, tempDictionary)
    response = basic.makeCall( body, CALL_DELETE_SENSOR, useProxy ) 
    if("deletedProcedure" in response):
        print("Successfully deleted sensor.")
    else:
        print("Error when deleting sensor, please check your parameters.")
        print(response)


def insertResult(resultValues: list, auth, resultTemplateName):
    """
    Insert a set of results into SOS.
    """
    arr_len = len(resultValues)
    b = DEFAULT_SEPARATOR_BLOCK.join(map(str,resultValues))
    b = b.replace("'","").replace("[","").replace("]","").replace(", ",DEFAULT_SEPARATOR_TOKEN)
    resultValues = "{}{}{}{}".format(arr_len,DEFAULT_SEPARATOR_BLOCK,b,DEFAULT_SEPARATOR_BLOCK)
    params = {
        'template': resultTemplateName,
        'resultValues' : resultValues }
    body = templates.renderSimpleTemplate( CALL_INSERT_RESULT, params )
    response = basic.makeCall( body, CALL_INSERT_RESULT, auth )
    return response