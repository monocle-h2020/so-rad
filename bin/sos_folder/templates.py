"""
Handler for the xml templates, both interrogating and using
"""

import re

__templatePath = 'templates/'

def __getXmlAsString( template: str ) -> str:
    """ 
    utility function to open xml files for reading and return their contents as a string 
    """
    f = open( __templatePath + template, 'r' )
    t = f.read()
    return t

def __checkListKeys( required: list, provided: list, throwError:bool = False ) -> bool:
    """
    utility function to compare two lists of dictionary keys and asser that the 'provided' list has at least
    the keys that 'required' has
    """
    required = set( required)
    provided = set( provided)
    isGood = True
    if not ( required.issubset( provided)):
        if throwError:
            missingKeys = required.difference( set( provided))
            raise ValueError( "passed values are missing the following keys {}".format( ",".join(missingKeys)))
        else:
            isGood = False
    return isGood

def renderSimpleTemplate( template: str, values: dict ) -> str:
    """
    Convert a dictionary and a template on the disk to a string with the 
    dynamic sections replaced by the dictionary (value) contents (using keys)
    """
    t = __getXmlAsString( template)
    output = t.format( **values)

    return output

def getTemplateParams( template: str, ignoreInternal: bool = True ) -> list:
    """
    get a list of all the keys that need to be supplied to make this template a valid xml call

    some templates have a section marked for the addition of another sub template,
    setting the optional value to False will return these as well
    """
    t = __getXmlAsString( template)

    keys = set( re.findall( "{([A-z|-]+)}", t))

    if ignoreInternal:
        keys = set( filter( lambda x: "-" not in x, keys))
    
    return list( keys)

    
def getInsertSensorBB3( values: dict ) -> str:
    """
    render BB3 template and return it
    """
    if not __checkListKeys( getTemplateParams( "insertSensor.xml" ), values.keys(), True):
        return None

    innerTemplate = renderSimpleTemplate( "partial/bb3-outputs.xml", values)

    newDict = values.copy()
    newDict['xml-outputs'] = innerTemplate

    return( renderSimpleTemplate( "insertSensor.xml", newDict))


def getInsertSensorSoRad(values: dict ) -> str:
    """
    render So-Rad template and return it
    """
    if not __checkListKeys( getTemplateParams( "insertSensor.xml" ), values.keys(), True):
        return None

    innerTemplate = renderSimpleTemplate( "partial/so-rad-outputs.xml", values)

    newDict = values.copy()
    newDict['xml-outputs'] = innerTemplate

    return( renderSimpleTemplate( "insertSensor.xml", newDict))


def constructTestDict( sensor: str ) -> dict:

    availableDicts = {
        'soradTestSensor': {
            'observableProperty': 'blob-of-water',
            'offering' : 'the-sorad-sensor',
            'altitude' : '5',
            'feature'  : 'our-lake',
            'procedure': 'https://monocle-h2020.eu/SWE/Procedures/soradtest',
            'latitude' : '10',
            'longitude': '10'
        }
    }

    if sensor not in availableDicts.keys():
        raise ValueError( "this sensor has not been defined" )
        
    return availableDicts[sensor]