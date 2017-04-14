from .pyHS100 import SmartDevice


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
    p.hsv = (100, 0, 255)
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

    Errors reported by the device are raised as SmartPlugExceptions,
    and should be handled by the user of the library.

    """
    # bulb states
    BULB_STATE_ON = 'ON'
    BULB_STATE_OFF = 'OFF'

    def __init__(self, ip_address, protocol=None):
        SmartDevice.__init__(self, ip_address, protocol)
        self.emeter_type = "smartlife.iot.common.emeter"
        self.emeter_units = True

    @property
    def is_color(self):
        """
        Whether the bulb supports color changes

        :return: True if the bulb supports color changes, False otherwise
        :rtype: bool
        """
        return bool(self.sys_info['is_color'])

    @property
    def is_dimmable(self):
        """
        Whether the bulb supports brightness changes

        :return: True if the bulb supports brightness changes, False otherwise
        :rtype: bool
        """
        return bool(self.sys_info['is_dimmable'])

    @property
    def is_variable_color_temp(self):
        """
        Whether the bulb supports color temperature changes

        :return: True if the bulb supports color temperature changes, False
        otherwise
        :rtype: bool
        """
        return bool(self.sys_info['is_variable_color_temp'])

    def get_light_state(self):
        return self._query_helper("smartlife.iot.smartbulb.lightingservice",
                                  "get_light_state")

    def set_light_state(self, state):
        return self._query_helper("smartlife.iot.smartbulb.lightingservice",
                                  "transition_light_state", state)

    @property
    def hsv(self):
        """
        Returns the current HSV state of the bulb, if supported

        :return: tuple containing current hue, saturation and value (0-255)
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

        return(hue, saturation, value)

    @hsv.setter
    def hsv(self, state):
        """
        Sets new HSV, if supported

        :param tuple state: hue, saturation and value (0-255 each)
        """
        if not self.is_color:
            return None

        light_state = {
            "hue": state[0],
            "saturation": state[1],
            "brightness": int(state[2] * 100 / 255),
            "color_temp": 0
            }
        return self.set_light_state(light_state)

    @property
    def color_temp(self):
        """
        Color temperature of the device, if supported

        :return: Color temperature in Kelvin
        :rtype: int
        """
        if not self.is_variable_color_temp:
            return None

        light_state = self.get_light_state()
        if not self.is_on:
            return(light_state['dft_on_state']['color_temp'])
        else:
            return(light_state['color_temp'])

    @color_temp.setter
    def color_temp(self, temp):
        """
        Set the color temperature of the device, if supported

        :param int temp: The new color temperature, in Kelvin
        """
        if not self.is_variable_color_temp:
            return None

        light_state = {
            "color_temp": temp,
        }
        return self.set_light_state(light_state)

    @property
    def brightness(self):
        """
        Current brightness of the device, if supported

        :return: brightness in percent
        :rtype: int
        """
        if not self.is_dimmable:
            return None

        light_state = self.get_light_state()
        if not self.is_on:
            return(light_state['dft_on_state']['brightness'])
        else:
            return(light_state['brightness'])

    @brightness.setter
    def brightness(self, brightness):
        """
        Set the current brightness of the device, if supported

        :param int brightness: brightness in percent
        """
        if not self.is_dimmable:
            return None

        light_state = {
            "brightness": brightness,
        }
        return self.set_light_state(light_state)

    @property
    def state(self):
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

    @property
    def is_on(self):
        return self.state == self.BULB_STATE_ON

    @state.setter
    def state(self, bulb_state):
        """
        Set the new bulb state

        :param bulb_state: one of
                           BULB_STATE_ON
                           BULB_STATE_OFF
        """
        print(bulb_state)
        print(self.BULB_STATE_ON)
        print(self.BULB_STATE_OFF)
        if bulb_state == self.BULB_STATE_ON:
            bulb_state = 1
        elif bulb_state == self.BULB_STATE_OFF:
            bulb_state = 0
        else:
            raise ValueError

        light_state = {
            "on_off": bulb_state,
        }
        return self.set_light_state(light_state)

    @property
    def has_emeter(self):
        return True
