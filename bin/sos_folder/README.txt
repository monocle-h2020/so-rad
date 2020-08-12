1. This folder contains the code to upload the templates for your sensor into sos.
2. It currently does not support insertResult but that is being worked on and should be delivered soon.

3. Before running the main code, you must get an AUTH Token from the SOS server, so that the proxy can approve all non-read requests. Do this by opening a terminal, cd into this folder directory, and type "python3 authenticate.py" and enter your sensor name, username and password as prompted.
This will copy your new auth code to the config file.

4. To configure the code for your device, please open the config.ini file, and change the parameters there as you see fit to match your device.

For example: 
#####################################################
[SOS]
# Sensor template definitions
Auth = AUTHKEY
UniqueID = ANYTHING_UNIQUE_TO_YOUR_DEVICE
observableProperty = WATER_CONDITION
offering = SENSOR_NAME
altitude = 5
feature = STATION_SETUP
procedure = RESULT_COLLECTION_IDENTIFIER
latitude = 50.352157
longitude = -4.148167
resultTemplate = TEMPLATE_RESULT_NAME
#####################################################

5. Once you've changed the parameters, you must open up a terminal, cd into the directory of this folder, and enter "python3 sos_functions.py", that will upload your sensor into SOS, and you should see messages confirming this in the terminal, it may take a few seconds. 