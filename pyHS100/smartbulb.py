from pyHS100 import SmartDevice
from typing import Any, Dict, Optional, Tuple


class SmartBulb(SmartDevice):
    """Representation of a TP-Link Smart Bulb.

    Usage example when used as library:
    p = SmartBulb("192.168.1.105")
    # print the devices alias
    print(p.alias)
    # change state of bulb
    p.state = "ON"
    p.state = "OFF"
    # query and print current state of plug
    print(p.state)
    # check whether the bulb supports color changes
    if p.is_color:
    # set the color to an HSV tuple
    p.hsv = (180, 100, 100)
    # get the current HSV value
    print(p.hsv)
    # check whether the bulb supports setting color temperature
    if p.is_variable_color_temp:
    # set the color temperature in Kelvin
    p.color_temp = 3000
    # get the current color temperature
    print(p.color_temp)
    # check whether the bulb is dimmable
    if p.is_dimmable:
    # set the bulb to 50% brightness
    p.brightness = 50
    # check the current brightness
    print(p.brightness)

    Errors reported by the device are raised as SmartDeviceExceptions,
    and should be handled by the user of the library.

    """
    # bulb states
    BULB_STATE_ON = 'ON'
    BULB_STATE_OFF = 'OFF'

    def __init__(self,
                 ip_address: str,
                 protocol: 'TPLinkSmartHomeProtocol' = None) -> None:
        SmartDevice.__init__(self, ip_address, protocol)
        self.emeter_type = "smartlife.iot.common.emeter"
        self.emeter_units = True

    @property
    def is_color(self) -> bool:
        """
        Whether the bulb supports color changes

        :return: True if the bulb supports color changes, False otherwise
        :rtype: bool
        """
        return bool(self.sys_info['is_color'])

    @property
    def is_dimmable(self) -> bool:
        """
        Whether the bulb supports brightness changes

        :return: True if the bulb supports brightness changes, False otherwise
        :rtype: bool
        """
        return bool(self.sys_info['is_dimmable'])

    @property
    def is_variable_color_temp(self) -> bool:
        """
        Whether the bulb supports color temperature changes

        :return: True if the bulb supports color temperature changes, False
        otherwise
        :rtype: bool
        """
        return bool(self.sys_info['is_variable_color_temp'])

    def get_light_state(self) -> Dict:
        return self._query_helper("smartlife.iot.smartbulb.lightingservice",
                                  "get_light_state")

    def set_light_state(self, state: Dict) -> Dict:
        return self._query_helper("smartlife.iot.smartbulb.lightingservice",
                                  "transition_light_state", state)

    @property
    def hsv(self) -> Optional[Tuple[int, int, int]]:
        """
        Returns the current HSV state of the bulb, if supported

        :return: hue, saturation and value (degrees, %, %)
        :rtype: tuple
        """

        if not self.is_color:
            return None

        light_state = self.get_light_state()
        if not self.is_on:
            hue = light_state['dft_on_state']['hue']
            saturation = light_state['dft_on_state']['saturation']
            value = int(light_state['dft_on_state']['brightness'] * 255 / 100)
        else:
            hue = light_state['hue']
            saturation = light_state['saturation']
            value = int(light_state['brightness'] * 255 / 100)

        return hue, saturation, value

    @hsv.setter
    def hsv(self, state: Tuple[int, int, int]):
        """
        Sets new HSV, if supported

        :param tuple state: hue, saturation and value (degrees, %, %)
        """
        if not self.is_color:
            return None

        light_state = {
            "hue": state[0],
            "saturation": state[1],
            "brightness": int(state[2] * 100 / 255),
            "color_temp": 0
            }
        self.set_light_state(light_state)

    @property
    def color_temp(self) -> Optional[int]:
        """
        Color temperature of the device, if supported

        :return: Color temperature in Kelvin
        :rtype: int
        """
        if not self.is_variable_color_temp:
            return None

        light_state = self.get_light_state()
        if not self.is_on:
            return int(light_state['dft_on_state']['color_temp'])
        else:
            return int(light_state['color_temp'])

    @color_temp.setter
    def color_temp(self, temp: int) -> None:
        """
        Set the color temperature of the device, if supported

        :param int temp: The new color temperature, in Kelvin
        """
        if not self.is_variable_color_temp:
            return None

        light_state = {
            "color_temp": temp,
        }
        self.set_light_state(light_state)

    @property
    def brightness(self) -> Optional[int]:
        """
        Current brightness of the device, if supported

        :return: brightness in percent
        :rtype: int
        """
        if not self.is_dimmable:
            return None

        light_state = self.get_light_state()
        if not self.is_on:
            return int(light_state['dft_on_state']['brightness'])
        else:
            return int(light_state['brightness'])

    @brightness.setter
    def brightness(self, brightness: int) -> None:
        """
        Set the current brightness of the device, if supported

        :param int brightness: brightness in percent
        """
        if not self.is_dimmable:
            return None

        light_state = {
            "brightness": brightness,
        }
        self.set_light_state(light_state)

    @property
    def state(self) -> str:
        """
        Retrieve the bulb state

        :returns: one of
                  BULB_STATE_ON
                  BULB_STATE_OFF
        :rtype: str
        """
        light_state = self.get_light_state()
        if light_state['on_off']:
            return self.BULB_STATE_ON
        return self.BULB_STATE_OFF

    @state.setter
    def state(self, bulb_state: str) -> None:
        """
        Set the new bulb state

        :param bulb_state: one of
                           BULB_STATE_ON
                           BULB_STATE_OFF
        """
        if bulb_state == self.BULB_STATE_ON:
            new_state = 1
        elif bulb_state == self.BULB_STATE_OFF:
            new_state = 0
        else:
            raise ValueError

        light_state = {
            "on_off": new_state,
        }
        self.set_light_state(light_state)

    @property
    def state_information(self) -> Dict[str, Any]:
        """
        Return bulb-specific state information.
        :return: Bulb information dict, keys in user-presentable form.
        :rtype: dict
        """
        info = {
            'Brightness': self.brightness,
            'Is dimmable': self.is_dimmable,
        }  # type: Dict[str, Any]
        if self.is_variable_color_temp:
            info["Color temperature"] = self.color_temp
        if self.is_color:
            info["HSV"] = self.hsv

        return info

    @property
    def is_on(self) -> bool:
        return bool(self.state == self.BULB_STATE_ON)

    def turn_off(self) -> None:
        """
        Turn the bulb off.
        """
        self.state = self.BULB_STATE_OFF

    def turn_on(self) -> None:
        """
        Turn the bulb on.
        """
        self.state = self.BULB_STATE_ON

    @property
    def has_emeter(self) -> bool:
        return True
