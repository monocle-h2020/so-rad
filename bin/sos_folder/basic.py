#!/usr/bin/python3
"""
basic request functions for sos comms

Author: Darren Snee
"""

import requests
import json
import pprint
import xml.etree.ElementTree as et

# for prettier output 
from xml.dom import minidom

proxyHost = 'https://sosproxy.monocle-h2020.eu'
#proxyHost = 'http://192.171.164.62:32145'
sosServer = 'https://rsg.pml.ac.uk/sensorweb'
#sosServer = 'http://192.171.164.62:8080/52n-sos-webapp'

proxyCall = proxyHost + '/api/sos_proxy/{}/xml/submit'   #proxyUrl with marker for auth key
authCall  = proxyHost + '/api/get_token/{}/{}/{}' #authUrl with markers for credentials
sosCall   = sosServer + '/service'
xmlPath   ='xml/request/example/'
COLOUR_YELLOW = 33
authKey   = None

serverSuccess = 'success'

def sendRequest( url, payload = None ):

    result = None

    headers = {
        'X-Requested-With': 'XMLHttpRequest',
        'Content-Type': 'application/xml'
    }

    try:
        if payload != None:
            r = requests.post( url, payload, headers=headers )
        else:
            r = requests.get( url, headers=headers )
        try:
            result = et.fromstring( r.text )
        except Exception as err:
            print( "Error decoding response: {}".format( err ))
            print( "Response was:\n{}".format( r.text ))
            return None
    except IOError as err:
        print ("error connecting to {}, error was {}".format( url, err))
        return None

    return result

def authWithProxy( sensor, user, password):
    authUrl = authCall.format( sensor, user, password)

    authResult = sendRequest( authUrl )

    if authResult == None:
        return None
    elif not validateResponse( authResult, True ):
        print( "Authentication failed" )
        if ( authResult.find( 'message' ) != None ):
            print( authResult.find( 'message' ).text )
        return None
    elif (authResult.find( 'token' ) != None ):
        global authKey
        authKey = authResult.find('token').text
        return authKey

    print( "No token was returned" )
    print( "Response was: {}".format( et.tostring(authResult)))
    return None

def validateResponse( r, enforce=False):

    valid = True

    if not hasattr( r, 'find' ):
        return False
    elif ( enforce
           and
           (r.find( 'status' ) == None )
           and
           (r.find('status').text != serverSuccess)):
           valid = False
    elif (( r.find( 'status' ) != None )
          and
          ( r.find( 'status' ).text != serverSuccess )):
        valid = False

    return valid  

def ppSendRequest( server, payload, name, description="" ):
    colourSpeak( "Sending {} request to {}".format( name, server ), COLOUR_YELLOW )
    if ( "" != description ):
        colourSpeak( description, COLOUR_YELLOW )
    return sendRequest( server, payload )

def getRequestXml( requestType ):
    pathToFile = xmlPath + requestType + '.xml'
    return open( pathToFile ).read()

def getSimpleCall( call ):
    """
    wrapper function to allow calls to sos using the xml files raw
    """
    xml = getRequestXml( call )

    print(
        makeCall(
            xml,
            call,
            ( call.startswith( 'delete' ) or call.startswith( 'insert' ))))

def makeCall( xml: str, name: str, useAuth: bool = False) -> str:
    
    if useAuth:
        # time to use the proxy
        url = proxyCall.format( authKey )
    else:
        # we can go straight to the sos server
        url = sosCall
        
    response = ppSendRequest( url, xml, name )

    if response is not None:

        if not validateResponse( response ):
            print( "Call Failed" )
            if response.find( 'message' ).text:
                print( "reason was: {}".format( response.find('message').text ))
                print( "Full response:" )

        xmlstr = minidom.parseString(
            et.tostring( response)).toprettyxml(
                indent="\t", #
                newl=""      # newlines are already sent by sos
            )

        return xmlstr

    return None

def colourSpeak( s, colour=COLOUR_YELLOW ):
    print(
        "\033[1;"
        + str(colour)
        + ";40m"
        + s
        + "\033[0;0m"
    )
