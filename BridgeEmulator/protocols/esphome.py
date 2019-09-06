import json
import logging
import random
import requests

import socket
import sys

from time import sleep
from subprocess import check_output
from functions import light_types, nextFreeId
from functions.colors import convert_rgb_xy, convert_xy
from functions.network import getIpAddress

def getRequest(address, request_data, timeout=3):

    head = {"Content-type": "application/json"}
    response = requests.get("http://" + address + request_data, timeout=timeout, headers=head)
    return response.text

def postRequest(address, request_data, timeout=3):
    head = {"Content-type": "application/json"}
    response = requests.post("http://" + address + request_data, timeout=3, headers=head)
    return response.text

def getLightType(light, data):
    request_data = ""
    if light["modelid"] == "ESPHome-RGBW":
        if "ct" in data:
            request_data = request_data + "/light/white_led"
        elif "xy" in data:
            request_data = request_data + "/light/color_led"
        else:
            if light["state"]["colormode"] == "ct":
                request_data = request_data + "/light/white_led"
            elif light["state"]["colormode"] == "xy":
                request_data = request_data + "/light/color_led"
    elif light["modelid"] == "ESPHome-CT":
        request_data = request_data + "/light/white_led"
    elif light["modelid"] == "ESPHome-RGB":
        request_data = request_data + "/light/color_led"
    elif light["modelid"] == "ESPHome-Dimmable":
        request_data = request_data + "/light/dimmable_led"
    elif light["modelid"] == "ESPHome-Toggle":
        request_data = request_data + "/light/toggle_led"
    
    return request_data

def discover(bridge_config, new_lights):
    logging.debug("ESPHome: <discover> invoked!")

    device_ips = check_output("nmap  " + getIpAddress() + "/24 -p80 --open -n | grep report | cut -d ' ' -f5", shell=True).decode('utf-8').rstrip("\n").split("\n")
    del device_ips[-1] #delete last empty element in list
    for ip in device_ips:
        try:
            logging.debug ( "ESPHome: probing ip " + ip)
            response = requests.get ("http://" + ip + "/text_sensor/light_id", timeout=3)
            device = json.loads(response.text)['state'].split(';') #get device data
            mac = device[1]
            device_name = device[2]
            ct_boost = device[3]
            rgb_boost = device[4]
            if response.status_code == 200 and device[0] == "esphome_diyhue_light":
                logging.debug("ESPHome: Found " + device_name + " at ip " + ip)
                white_response = requests.get ("http://" + ip + "/light/white_led", timeout=3)
                color_response = requests.get ("http://" + ip + "/light/color_led", timeout=3)
                dim_response = requests.get ("http://" + ip + "/light/dimmable_led", timeout=3)
                toggle_response = requests.get ("http://" + ip + "/light/toggle_led", timeout=3)

                if (white_response.status_code != 200 and color_response.status_code != 200 and dim_response != 200 and toggle_response != 200):
                    logging.debug("ESPHome: Device has improper configuration! Exiting.")
                    raise
                elif (white_response.status_code == 200 and color_response.status_code == 200):
                    logging.debug("ESPHome: " + device_name + " is a RGBW ESPHome device")
                    white_device_data = json.loads(white_response.text)
                    color_device_data = json.loads(color_response.text)
                    properties = {"rgb": True, "ct": True, "ip": ip, "name": device_name, "id": mac + "." + ct_boost + "." + rgb_boost, "mac": mac}
                    modelid="LCT015"
                elif (white_response.status_code == 200):
                    logging.debug("ESPHome: " + device_name + " is a CT ESPHome device")
                    white_device_data = json.loads(white_response.text)
                    properties = {"rgb": False, "ct": True, "ip": ip, "name": device_name, "id": mac + "." + ct_boost + "." + rgb_boost, "mac": mac}
                    modelid="LWB010"
                elif (color_response.status_code == 200):
                    logging.debug("ESPHome: " + device_name + " is a RGB ESPHome device")
                    color_device_data = json.loads(color_response.text)
                    properties = {"rgb": True, "ct": False, "ip": ip, "name": device_name, "id": mac + "." + ct_boost + "." + rgb_boost, "mac": mac}
                    modelid="ESPHome-RGB"
                elif (dim_response.status_code == 200):
                    logging.debug("ESPHome: " + device_name + " is a Dimmable ESPHome device")
                    dim_device_data = json.loads(dim_response.text)
                    properties = {"rgb": False, "ct": False, "ip": ip, "name": device_name, "id": mac + "." + ct_boost + "." + rgb_boost, "mac": mac}
                    modelid="ESPHome-Dimmable"
                elif (toggle_response.status_code == 200):
                    logging.debug("ESPHome: " + device_name + " is a Toggle ESPHome device")
                    toggle_device_data = json.loads(toggle_response.text)
                    properties = {"rgb": False, "ct": False, "ip": ip, "name": device_name, "id": mac + "." + ct_boost + "." + rgb_boost, "mac": mac}
                    modelid="ESPHome-Toggle"

                device_exist = False
                for light in bridge_config["lights_address"].keys():
                    if bridge_config["lights_address"][light]["protocol"] == "esphome" and  bridge_config["lights_address"][light]["id"].split('.')[0] == properties["id"].split('.')[0]:
                        device_exist = True
                        bridge_config["lights_address"][light]["ip"] = properties["ip"]
                        bridge_config["lights_address"][light]["id"] = properties["id"]
                        logging.debug("ESPHome: light id " + properties["id"].split('.')[0] + " already exist, updating ip...")
                        break
                if (not device_exist):
                    light_name = "ESPHome id " + properties["id"][-8:] if properties["name"] == "" else properties["name"]
                    logging.debug("ESPHome: Adding ESPHome " + properties["id"])
                    new_light_id = nextFreeId(bridge_config, "lights")
                    bridge_config["lights"][new_light_id] = {"state": light_types[modelid]["state"], "type": light_types[modelid]["type"], "name": light_name, "uniqueid": mac, "modelid": modelid, "manufacturername": "ESPHome", "swversion": light_types[modelid]["swversion"]}
                    new_lights.update({new_light_id: {"name": light_name}})
                    bridge_config["lights_address"][new_light_id] = {"ip": properties["ip"], "id": properties["id"], "protocol": "esphome"}

        except Exception as e:
            logging.debug("ESPHome: ip " + ip + " is unknown device, " + str(e))



def set_light(address, light, data):
    logging.debug("ESPHome: <set_light> invoked! IP=" + address["ip"])
    logging.debug(light["modelid"])

    ct_boost = int(address["id"].split('.')[2])
    rgb_boost = int(address["id"].split('.')[2])
    request_data = ""
    #logging.debug("tasmota: key " + key)
    if "ct" in data:
        postRequest(address["ip"], "/light/color_led/turn_off")
    if "xy" in data:
        postRequest(address["ip"], "/light/white_led/turn_off")
    
    if "alert" in data:
        if data['alert'] == "select":
            request_data = request_data + "/switch/alert/turn_on"
    elif "on" in data:
        request_data = request_data + getLightType(light, data)
        if data['on']:
            request_data = request_data + "/turn_on"
            if "bri" in data:
                brightness = int(data['bri'])
                if light["state"]["colormode"] == "ct":
                    brightness = ct_boost + brightness
                elif light["state"]["colormode"] == "xy":
                    brightness = rgb_boost + brightness
                brightness = str(brightness)
                if ("?" in request_data):
                    request_data = request_data + "&brightness=" + brightness
                else:
                    request_data = request_data + "?brightness=" + brightness
            if "ct" in data:
                if ("?" in request_data):
                    request_data = request_data + "&color_temp=" + str(data['ct'])
                else:
                    request_data = request_data + "?color_temp=" + str(data['ct'])
            if "xy" in data:
                color = convert_xy(data['xy'][0], data['xy'][1], light["state"]["bri"])
                red = str(color[0])
                green = str(color[1])
                blue = str(color[2])
                if ("?" in request_data):
                    request_data = request_data + "&r=" + red + "&g=" + green + "&b=" + blue 
                else:
                    request_data = request_data + "?r=" + red + "&g=" + green + "&b=" + blue
        else:
            request_data = request_data + "/turn_off"

    postRequest(address["ip"], request_data)
    



def get_light_state(address, light):

    # logging.debug("ESPHome: <get_light_state> invoked!")
    # data = sendRequest ("http://" + address["ip"] + "/cm?cmnd=Status%2011")
    # light_data = json.loads(data)["StatusSTS"]
    state = {}

    # if 'POWER'in light_data:
    #     state['on'] = True if light_data["POWER"] == "ON" else False
    # elif 'POWER1'in light_data:
    #     state['on'] = True if light_data["POWER1"] == "ON" else False

    # if 'Color' not in light_data:
    #     if state['on'] == True:
    #         state["xy"] = convert_rgb_xy(255,255,255)
    #         state["bri"] = int(255)
    #         state["colormode"] = "xy"
    # else:
    #     rgb = light_data["Color"].split(",")
    #     logging.debug("tasmota: <get_light_state>: red " + str(rgb[0]) + " green " + str(rgb[1]) + " blue " + str(rgb[2]) )
    #     state["xy"] = convert_rgb_xy(int(rgb[0],16), int(rgb[1],16), int(rgb[2],16))
    #     state["bri"] = (int(light_data["Dimmer"]) / 100.0) * 254.0
    #     state["colormode"] = "xy"
    return state


# response = requests.get('http://light2.local/light/white_led', timeout=3, headers=head)
# response = requests.post('http://light2.local/light/white_led/turn_on?brightness=255&transition=0.4&color_temp=370', timeout=3, headers=head)
# response = requests.post('http://light2.local/light/white_led/turn_off', timeout=3, headers=head)
# requests.post('http://light2.local/light/color_led/turn_on?brightness=255&transition=0.4&r=136&g=65&b=217', timeout=3, headers=head)
# response = requests.get('http://light2.local/light/color_led', timeout=3, headers=head)
# print(response.text)