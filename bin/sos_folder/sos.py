"""
sos accessor functions
"""
CALL_DESCRIBE_SENSOR        = 'describeSensor.xml'
CALL_GET_RESULT             = 'getResult.xml'
CALL_GET_RESULT_TEMPLATE    = 'getResultTemplate.xml'
CALL_INSERT_SENSOR          = 'insertSensor.xml'
CALL_INSERT_RESULT_TEMPLATE = 'insertResultTemplate.xml'
CALL_INSERT_RESULT          = 'insertResult.xml'

DEFAULT_SEPARATOR_BLOCK = '@'
DEFAULT_SEPARATOR_TOKEN = '#'

import sos.templates as templates
import sos.basic as basic

def __makeCall( template: str, params: dict, useProxy: bool = False ) -> str:

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

def insertResult( template: str, values: list ) -> str:
    """
    inserts values using the supplied template, with the following assumptions:

    1) token separator is always DEFAULT_SEPARATOR_TOKEN
    2) block separator is always DEFAULT_SEPARATOR_BLOCK
    3) the provided list (values) is of the correct shape for the template
    """
    resultValuesList = map( lambda x: DEFAULT_SEPARATOR_TOKEN.join( x ), values )
    resultValues     = DEFAULT_SEPARATOR_BLOCK.join( resultValuesList )

    resultValues = "{}{}{}{}".format(
        len(values),
        DEFAULT_SEPARATOR_BLOCK,
        resultValues,
        DEFAULT_SEPARATOR_BLOCK)
    
    params = {
        'template': template,
        'resultValues' : resultValues }
    return __makeCall( CALL_INSERT_RESULT, params, True )

def insertResultTemplate( template: str, identifier: str, offering: str, observedProperty ) -> str:

    raise NotImplementedError
