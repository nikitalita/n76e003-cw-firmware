from collections import OrderedDict
import time
from chipwhisperer.capture.targets.simpleserial_readers._base import SimpleSerialTemplate
from chipwhisperer.capture.targets.simpleserial_readers.cwlite import SimpleSerial_ChipWhispererLite
from chipwhisperer.common.utils.util import camel_case_deprecated, dict_to_str
from chipwhisperer.capture.targets._base import TargetTemplate


from chipwhisperer.logging import *

NEWLINE_NUM = ord('\n')


class NormalSerialTemplate(SimpleSerialTemplate):
    def __init__(self):
        SimpleSerialTemplate.__init__(self)
        self._name = "Normal Serial Reader"

    def read(self, num=0, timeout=250):
        data = self.hardware_read(num, timeout=timeout)
        return data

    def write(self, string):
        # Write to hardware
        self.hardware_write(string)


class NormalSerialTemplate_ChipWhispererLite(NormalSerialTemplate, SimpleSerial_ChipWhispererLite):
    def __init__(self):
        NormalSerialTemplate.__init__(self)
        SimpleSerial_ChipWhispererLite.__init__(self)


class NormalSerial(TargetTemplate):
    """
    Regular serial communication with no SS protocol
    """
    _name = "Normal Serial"

    def __init__(self):
        TargetTemplate.__init__(self)

        self.ser = NormalSerialTemplate_ChipWhispererLite()

        self._protver = 'auto'
        self.protformat = 'hex'
        self.last_key = bytearray(16)
        self._output_len = 16

        self._proto_ver = "auto"
        self._proto_timeoutms = 20
        self._normalserial_last_read = ""
        self._normalserial_last_sent = ""

    def __repr__(self):
        ret = "SimpleSerial Settings ="
        for line in dict_to_str(self._dict_repr()).split("\n"):
            ret += "\n\t" + line
        return ret

    def __str__(self):
        return self.__repr__()

    def _dict_repr(self):
        rtn = OrderedDict()
        rtn['output_len'] = self.output_len

        rtn['baud'] = self.baud
        rtn['ns_last_read'] = self.ns_last_read
        rtn['ns_last_sent'] = self.ns_last_sent
        return rtn

    @property
    def ns_last_read(self):
        """The last raw string read by a simpleserial_read* command"""
        return self._normalserial_last_read

    @property
    def ns_last_sent(self):
        """The last raw string written via simpleserial_write"""
        return self._normalserial_last_sent

    @property
    def baud(self):
        """The current baud rate of the serial connection.

        :Getter: Return the current baud rate.

        :Setter: Set a new baud rate. Valid baud rates are any integer in the
                        range [500, 2000000].

        Raises:
                        AttributeError: Target doesn't allow baud to be changed.
        """
        if hasattr(self.ser, 'baud') and callable(self.ser.baud):
            return self.ser.baud()
        else:
            raise AttributeError("Can't access baud rate")

    @baud.setter
    def baud(self, new_baud):
        if hasattr(self.ser, 'baud') and callable(self.ser.baud):
            self.ser.setBaud(new_baud)
        else:
            raise AttributeError("Can't access baud rate")

    def _con(self, scope=None, **kwargs):
        if not scope or not hasattr(scope, "qtadc"):
            Warning("You need a scope with OpenADC connected to use this Target")

        self.ser.con(scope)

        if kwargs.get('noflush', False) == False:
            # 'x' flushes everything & sets system back to idle
            self.ser.flush()

    def dis(self):
        self.close()

    def close(self):
        if self.ser != None:
            self.ser.close()

    def init(self):
        self.ser.flush()

    def is_done(self):
        """Always returns True"""
        return True

    def _write(self, data):
        """ Writes data to the target over serial.

        Args:
                        data (str): Data to write over serial.

        Raises:
                        Warning: Target not connected

        .. versionadded:: 5.1
                        Added target.write()
        """
        if not self.connectStatus:
            raise Warning("Target not connected")

        try:
            self.ser.write(data)
        except Exception as e:
            self.dis()
            raise e

    def _read(self, num_char: int = 0, timeout: int = 250) -> str:
        """ Reads data from the target over serial.

        Args:
                        num_char (int, optional): Number of byte to read. If 0, read all
                                        data available. Defaults to 0.
                        timeout (int, optional): How long in ms to wait before returning.
                                        If 0, block for a long time. Defaults to 250.

        Returns:
                        String of received data.

        .. versionadded:: 5.1
                        Added target.read()
        """
        if not self.connectStatus:
            raise Warning("Target not connected")
        if timeout == 0:
            timeout = 10000000000
        try:
            if num_char == 0:
                num_char = self.ser.inWaiting()
            return self.ser.read(num_char, timeout)
        except Exception as e:
            self.dis()
            raise e

    def in_waiting(self):
        """Returns the number of characters available from the serial buffer.

        Returns:
                        The number of characters available via a target.read() call.

        .. versionadded:: 5.1
                        Added target.in_waiting()
        """
        return self.ser.inWaiting()

    inWaiting = camel_case_deprecated(in_waiting)

    def flush(self):
        """Removes all data from the serial buffer.

        .. versionadded:: 5.1
                        Added target.flush()
        """
        self.ser.flush()

    def in_waiting_tx(self):
        """Returns the number of characters waiting to be sent by the ChipWhisperer.

        Requires firmware version >= 0.2 for the CWLite/Nano and firmware version and
        firmware version >= 1.2 for the CWPro.

        Used internally to avoid overflowing the TX buffer, since CW version 5.3

        Returns:
                        The number of characters waiting to be sent to the target

        .. versionadded:: 5.3.1
                        Added public method for in_waiting_tx().
        """
        return self.ser.inWaitingTX()

    def _con(self, scope=None, **kwargs):
        if not scope or not hasattr(scope, "qtadc"):
            Warning("You need a scope with OpenADC connected to use this Target")

        self.ser.con(scope)

        # Check to see if the caller wants to be responsible for flushing the
        # UART on connect. For real world targets, we may just want to quietly
        # open serial port without sending "xxx..." at a potentially incorrect
        # baud rate.
        if kwargs.get('noflush', False) == False:
            self.ser.flush()

    def write(self, data: str):
        # if not type(data) is str:
        # 	data = bytearray(data)
        # 	if end:
        # 		data += bytearray(end, encoding='latin-1') if type(end) is str else bytearray(end)
        # else:
        # 	data += str(end)
        self._write(data)
        self._normalserial_last_sent = data

    def readline(self, timeout: int = 250) -> str:
        response = self.ser.readline(timeout=timeout)
        if len(response) == 0:
            target_logger.warning("Read empty string")
        elif '\n' not in response:
            target_logger.warning(
                "Read string without newline: {}".format(response))
        return response

    def read(self, recv_len: int, timeout: int = 250) -> str:
        response = self._read(recv_len, timeout=timeout)
        self._normalserial_last_read = response

        if len(response) != recv_len:
            target_logger.warning(
                "Unexpected response length: {}".format(len(response)))

        return response

    def read_witherrors(self, recv_len: int, end: str = '', timeout: int = 250):
        response = self._read(recv_len, timeout=timeout)
        self._normalserial_last_read = response

        valid = True
        if len(response) != recv_len:
            target_logger.warning(
                "Unexpected response length: {}".format(len(response)))
            valid = False
        if len(end) > 0:
            if response[0:(len(end))] != end:
                target_logger.warning("Unexpected end to command: {}".format(
                    response[0:(len(end))]))
                valid = False

        self._normalserial_last_read = response
        return {'valid': valid, 'response': response, 'bytearray': bytearray(response)}
