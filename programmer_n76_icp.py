from functools import wraps
import logging
import subprocess
import time
from chipwhisperer.capture.scopes import ScopeTypes
from chipwhisperer.capture.api.programmers import save_and_restore_pins, Programmer
from chipwhisperer.capture.utils.IntelHex import IntelHex
from chipwhisperer.logging import *
from nuvoprogpy.nuvo51icpy.nuvo51icpy import Nuvo51ICP, ConfigFlags, N76E003_DEVID
from nuvoprogpy.nuvo51icpy.libicp_iface import ICPLibInterface
from chipwhisperer.hardware.naeusb.naeusb import NAEUSB, packuint32, unpackuint32

from pyparsing import C


# Disables brown-out detector
NO_BROWNOUT_CONFIG = bytes([0xFF, 0xFF, 0x73, 0xFF, 0xFF])

class N76E003:
    signature = N76E003_DEVID
    name = "N76E003"

supported_devices = [N76E003]

REQ_NU51_ICP_PROGRAM = 0x40

# Enter programming mode
NUVO_CMD_CONNECT = 0xae
# Get Device ID
NUVO_CMD_GET_DEVICEID = 0xb1
# Read flash
NUVO_CMD_READ_FLASH = 0xa5
# Write flash
NUVO_CMD_PAGE_ERASE = 0xD5
# Exit programming mode
NUVO_CMD_RESET = 0xad

# ICP Specific
# Get Unique ID
NUVO_CMD_GET_UID = 0xb2
# Get Company ID
NUVO_CMD_GET_CID = 0xb3
# Get Unique Company ID
NUVO_CMD_GET_UCID = 0xb4
# Mass erase
NUVO_CMD_MASS_ERASE = 0xD6
# Puts the target into ICP mode, but doesn't initialize the PGM.
NUVO_CMD_ENTER_ICP_MODE = 0xe7
# Takes the target out of ICP mode, but doesn't deinitialize the PGM.
NUVO_CMD_EXIT_ICP_MODE = 0xe8
# Takes chip out of and then puts it back into ICP mode
NUVO_CMD_REENTER_ICP = 0xe9
# For getting the configuration bytes to read at consistent times during an ICP reentry.
NUVO_CMD_REENTRY_GLITCH = 0xea
# Write to ROM
NUVO_CMD_WRITE_FLASH = 0xed
# Set the programming time between bytes
NUVO_SET_PROG_TIME = 0xec
# Set the erase time for a page
NUVO_SET_PAGE_ERASE_TIME = 0xee
# Set the mass erase time
NUVO_SET_MASS_ERASE_TIME = 0xef
# Set the post mass erase time
NUVO_SET_POST_MASS_ERASE_TIME = 0xe3
# Get the Product ID
NUVO_CMD_GET_PID = 0xeb

# ChipWhisperer specific
NUVO_GET_RAMBUF = 0xe4
NUVO_SET_RAMBUF = 0xe5
NUVO_GET_STATUS = 0xe6

NUVO_ERR_OK = 0
NUVO_ERR_FAILED = 1
NUVO_ERR_INCORRECT_PARAMS = 2
NUVO_ERR_COLLISION = 3
NUVO_ERR_TIMEOUT = 4
NUVO_ERR_WRITE_FAILED = 5
NUVO_ERR_READ_FAILED = 6

# page size
NU51_PAGE_SIZE = 128
NU51_PAGE_MASK = 0xFF80


NUVO_PREFIX_LEN = 3

def packuint16(data):
    """Converts a 16-bit integer into format expected by USB firmware"""

    data = int(data)
    return [data & 0xff, (data >> 8) & 0xff]
def unpackuint16(buf, offset=0):
    """"Converts an array into a 16-bit integer"""

    pint = buf[offset]
    pint |= buf[offset+1] << 8
    return pint


class newaeUSBICPLib(ICPLibInterface):
    REQ_NU51_ICP_PROGRAM = 0x40
    PREFIX_LEN = NUVO_PREFIX_LEN
    MAX_BUFFER_SIZE = 256

    def debug_print(self, *args):
        if scope_logger.getEffectiveLevel() <= logging.DEBUG:
            self.print_func(*args)

    def __init__(self, scope: ScopeTypes, print_func=print):
        self.scope: ScopeTypes = scope
        self._usb: NAEUSB = scope._getNAEUSB()
        self.print_func = print_func

    def err_to_str(self, err):
        if err == NUVO_ERR_OK:
            return "ERR_OK"
        if err == NUVO_ERR_FAILED:
            return "ERR_FAILED"
        if err == NUVO_ERR_INCORRECT_PARAMS:
            return "ERR_INCORRECT_PARAMS"
        if err == NUVO_ERR_COLLISION:
            return "ERR_COLLISION"
        if err == NUVO_ERR_TIMEOUT:
            return "ERR_TIMEOUT"
        if err == NUVO_ERR_WRITE_FAILED:
            return "ERR_WRITE_FAILED"
        if err == NUVO_ERR_READ_FAILED:
            return "ERR_READ_FAILED"
        return "UNKNOWN"
    
    def cmd_to_str(self, wValue):
        cmd = wValue & 0xFF
        if cmd == NUVO_CMD_WRITE_FLASH:
            return "WRITE_ROM"
        if cmd == NUVO_CMD_CONNECT:
            return "CONNECT"
        if cmd == NUVO_CMD_GET_DEVICEID:
            return "GET_DEVICEID"
        if cmd == NUVO_CMD_RESET:
            return "RESET"
        if cmd == NUVO_CMD_READ_FLASH:
            return "READ_ROM"
        if cmd == NUVO_CMD_GET_UID:
            return "GET_UID"
        if cmd == NUVO_CMD_GET_CID:
            return "GET_CID"
        if cmd == NUVO_CMD_GET_UCID:
            return "GET_UCID"
        if cmd == NUVO_CMD_PAGE_ERASE:
            return "PAGE_ERASE"
        if cmd == NUVO_CMD_MASS_ERASE:
            return "MASS_ERASE"
        if cmd == NUVO_GET_RAMBUF:
            offset = (wValue >> 8) & 0xFF
            return "GET_RAMBUF [offset: {:02x}]".format(offset)
        if cmd == NUVO_SET_RAMBUF:
            offset = (wValue >> 8) & 0xFF
            return "SET_RAMBUF [offset: {:02x}]".format(offset)
        if cmd == NUVO_GET_STATUS:
            return "GET_STATUS"
        if cmd == NUVO_CMD_ENTER_ICP_MODE:
            return "ENTER_ICP_MODE"
        if cmd == NUVO_CMD_EXIT_ICP_MODE:
            return "EXIT_ICP_MODE"
        if cmd == NUVO_CMD_REENTER_ICP:
            return "REENTER_ICP"
        if cmd == NUVO_CMD_REENTRY_GLITCH:
            return "REENTRY_GLITCH"
        if cmd == NUVO_SET_PROG_TIME:
            return "SET_PROG_TIME"
        if cmd == NUVO_SET_PAGE_ERASE_TIME:
            return "SET_PAGE_ERASE_TIME"
        if cmd == NUVO_SET_MASS_ERASE_TIME:
            return "SET_MASS_ERASE_TIME"
        if cmd == NUVO_SET_POST_MASS_ERASE_TIME:
            return "SET_POST_MASS_ERASE_TIME"
        if cmd == NUVO_CMD_GET_PID:
            return "GET_PID"
        return "UNKNOWN"

    def _n51DoCmd(self, cmd, data: bytearray, checkStatus=True, rlen=0):
        """
        Send a command to the Nu51 ICP.

        :param cmd: Command to send
        :param data: Data to send
        :param checkStatus: Check the status of the command
        :param rlen: Length of the response to read (minus the prefix) (default=0)
        """
        if data is None:
            data = bytearray()
        if not isinstance(data, bytearray):
            data = bytearray(data)
        self._usb.sendCtrl(self.REQ_NU51_ICP_PROGRAM, cmd, data)
        # Check status
        status = []
        if checkStatus:
            status = self._n51GetStatus(dlen=NUVO_PREFIX_LEN + rlen)
            if status[1] != NUVO_ERR_OK:
                raise IOError("Nu51 ICP Command %s (%x) failed: err=%s (%x), timeout=%d" % (self.cmd_to_str(cmd), cmd, self.err_to_str(status[1]), status[1], status[2]))
            self.debug_print("Nu51 ICP Command %s (%x) OK" % (self.cmd_to_str(cmd), cmd))
        return status[NUVO_PREFIX_LEN:]
    def _n51DoRead(self, cmd, dlen):
        """
        Read the result of some command.
        """
        # windex selects interface, set to 0
        return self._usb.readCtrl(self.REQ_NU51_ICP_PROGRAM, cmd, dlen)

    def _n51GetStatus(self, dlen=NUVO_PREFIX_LEN):
        """
        Read the result of some command.
        """
        return self._n51DoRead(NUVO_GET_STATUS, dlen=dlen)
    def _n51GetRambuf(self, offset, dlen):
        """
        Read the ram buffer
        """
        return self._n51DoRead(NUVO_GET_RAMBUF | (offset << 8), dlen=dlen)
    def _n51SetRambuf(self, offset, data):
        """
        Set the ram buffer.
        """
        # windex selects interface, set to 0
        return self._n51DoCmd(NUVO_SET_RAMBUF | (offset << 8), data, checkStatus=True)

    def init(self, do_reset=True) -> bool:
        val = (1 if do_reset else 0)
        self.scope.io.cwe.setAVRISPMode(1)
        self._n51DoCmd(NUVO_CMD_CONNECT, bytearray([val]), checkStatus=True)
        return True

    def entry(self, do_reset=True) -> bool:
        val = (1 if do_reset else 0)
        self._n51DoCmd(NUVO_CMD_ENTER_ICP_MODE, bytearray([val]), checkStatus=True)
        return True
    
    def exit(self) -> bool:
        self._n51DoCmd(NUVO_CMD_EXIT_ICP_MODE, bytearray(), checkStatus=True)
        return True

    def reentry(self, delay1=5000, delay2=1000, delay3=10) -> bool:
        data = packuint32(delay1) + packuint32(delay2) + packuint32(delay3)
        self._n51DoCmd(NUVO_CMD_REENTER_ICP, data, checkStatus=True)
        return True

    def reentry_glitch(self, delay1=5000, delay2=1000, delay_after_trigger_high=0, delay_before_trigger_low=280) -> bool:
        data = packuint32(delay1) + packuint32(delay2) + packuint32(delay_after_trigger_high) + packuint32(delay_before_trigger_low)
        self._n51DoCmd(NUVO_CMD_REENTRY_GLITCH, data,  checkStatus=True)
        return True

    def deinit(self, leave_reset_high: bool = False) -> bool:
        val = 1 if leave_reset_high else 0
        self._n51DoCmd(NUVO_CMD_RESET, bytearray([val]), checkStatus=True)
        self.scope.io.cwe.setAVRISPMode(0)
        return True

    def read_device_id(self) -> int:
        return unpackuint32(self._n51DoCmd(NUVO_CMD_GET_DEVICEID, bytearray(), checkStatus=True, rlen=4))

    def read_pid(self) -> int:
        return unpackuint32(self._n51DoCmd(NUVO_CMD_GET_PID, bytearray(), checkStatus=True, rlen=4))

    def read_cid(self) -> int:
        return unpackuint32(self._n51DoCmd(NUVO_CMD_GET_CID, bytearray(), checkStatus=True, rlen=4))

    def read_uid(self) -> bytes:
        return self._n51DoCmd(NUVO_CMD_GET_UID, bytearray(), checkStatus=True, rlen=12)

    def read_ucid(self) -> bytes:
        return self._n51DoCmd(NUVO_CMD_GET_UCID, bytearray(), checkStatus=True, rlen=16)

    def read_flash(self, addr, length) -> bytes:
        memread = 0
        endptsize = 64
        dlen = length

        membuf = []

        while memread < dlen:

            # Read into internal buffer
            ramreadln = dlen - memread

            # Check if maximum size for internal buffer
            if ramreadln > self.MAX_BUFFER_SIZE:
                ramreadln = self.MAX_BUFFER_SIZE

            self._n51DoCmd(NUVO_CMD_READ_FLASH, packuint32(addr + memread) + packuint16(ramreadln), checkStatus=True)

            epread = 0

            # First we need to fill the page buffer in the USB Interface using smaller transactions
            while epread < ramreadln:

                epreadln = ramreadln - epread
                if epreadln > endptsize:
                    epreadln = endptsize

                # Read data out progressively
                membuf.extend(self._n51GetRambuf(epread, dlen=epreadln))
                # print epread
                epread += epreadln
            memread += ramreadln
        return bytes(membuf)

    def write_flash(self, addr, data) -> int:
        memwritten = 0
        endptsize = 64
        start = 0
        end = endptsize
        pagesize = NU51_PAGE_SIZE
        self.debug_print("Writing to address 0x{:04x}".format(addr))
        if addr % pagesize:
            self.print_func('You appear to be writing to an address that is not page aligned, you will probably write the wrong data')
        if len(data) < pagesize:
            pagesize = len(data)

        while memwritten < len(data):

            epwritten = 0
            tx_checksum = 0

            # First we need to fill the page buffer in the USB Interface using smaller transactions
            while epwritten < pagesize:

                # Check for less than full endpoint written
                if end > len(data):
                    end = len(data)

                # Get slice of data
                epdata = data[start:end]
                for byte in epdata:
                    tx_checksum+=byte
                tx_checksum &= 0xffff

                self.debug_print("%d %d %d" % (epwritten, len(epdata), memwritten))
                # Copy to USB interface buffer
                self._n51SetRambuf(epwritten, data=epdata)

                epwritten += len(epdata)

                # Check for final write indicating we are done
                if end == len(data):
                    break

                start += endptsize
                end += endptsize
            # Do write into memory type
            infoblock = []


            infoblock.extend(packuint32(addr + memwritten))
            infoblock.extend(packuint16(epwritten))

            # print "%x" % (addr + memwritten)
            # print epwritten
            rx_checksum = unpackuint16(self._n51DoCmd(NUVO_CMD_WRITE_FLASH, data=infoblock, checkStatus=True, rlen=2))
            if rx_checksum != tx_checksum:
                raise IOError("Checksum error writing to address 0x{:04x}".format(addr + memwritten))
            memwritten += epwritten
        return True

    def mass_erase(self) -> bool:
        self._n51DoCmd(NUVO_CMD_MASS_ERASE, bytearray(), checkStatus=True)
        return True

    def page_erase(self, addr) -> bool:
        self._n51DoCmd(NUVO_CMD_PAGE_ERASE, packuint32(addr), checkStatus=True)
        return True
    
    def set_program_time(self, time_us: int) -> bool:
        self._n51DoCmd(NUVO_SET_PROG_TIME, packuint32(time_us), checkStatus=True)
        return True
    
    def set_page_erase_time(self, time_us: int) -> bool:
        self._n51DoCmd(NUVO_SET_PAGE_ERASE_TIME, packuint32(time_us), checkStatus=True)
        return True
    
    def set_mass_erase_time(self, time_us: int) -> bool:
        self._n51DoCmd(NUVO_SET_MASS_ERASE_TIME, packuint32(time_us), checkStatus=True)
        return True
    
    def set_post_mass_erase_time(self, time_us: int) -> bool:
        self._n51DoCmd(NUVO_SET_POST_MASS_ERASE_TIME, packuint32(time_us), checkStatus=True)
        return True
    
        


class N76ICPProgrammer(Programmer):
    def __init__(self, logfunc=print, config_bytes: bytes = NO_BROWNOUT_CONFIG, scope = None):
        self.logfunc = logfunc
        self._erased = False
        if config_bytes is None:
            config_bytes = NO_BROWNOUT_CONFIG
        self.config_bytes = config_bytes
        self.lib = None
        self.scope = scope

    def open(self):
        self.lib = newaeUSBICPLib(self.scope, print_func=self.logfunc)

    def save_pin_setup(self):
        self.pin_setup['pdic'] = self.scope.io.pdic
        self.pin_setup['pdid'] = self.scope.io.pdid
        self.pin_setup['nrst'] = self.scope.io.nrst

    def restore_pin_setup(self):
        self.scope.io.pdic = self.pin_setup['pdic']
        self.scope.io.pdid = self.pin_setup['pdid']
        self.scope.io.nrst = self.pin_setup['nrst']

    def setUSBInterface(self, iface):
        raise DeprecationWarning('find method now includes what setUSBInterface did')
    @save_and_restore_pins
    def find(self):
        with Nuvo51ICP(library=self.lib, _enter_no_init = True, logfunc=self.logfunc, _deinit_reset_high=False) as nuvo:
            nuvo.init(check_device = False)
            dev_info = nuvo.get_device_info()
            if dev_info.is_unsupported:
                raise IOError("Device not found: {:04x}".format(dev_info.device_id))
            self.logfunc("Found device:")
            self.logfunc(dev_info)
    
    @staticmethod
    def convert_to_bin(filename:str):
        if filename.endswith(".hex"):
            # convert it to bin
            f = IntelHex(filename)
            start=f.minaddr()
            fw_data = f.tobinarray(start=start)
            return bytes(fw_data)
        return open(filename, "rb").read()

    @save_and_restore_pins
    def program(self, filename:str, memtype="flash", verify=True):
        self.lastFlashedFile = filename
        file_data = self.convert_to_bin(filename)
        programmed = False
        should_erase = not self.erased
        self.erased = False
        config: ConfigFlags = None
        with Nuvo51ICP(library=self.lib, logfunc=self.logfunc, _deinit_reset_high=False) as nuvo:
            device_info = nuvo.get_device_info()
            config = ConfigFlags.from_bytes(self.config_bytes, device_info.device_id)
            if memtype == "ldrom":
                if len(file_data) > device_info.ldrom_max_size:
                    raise Exception("LDROM size is too large for the device (>{}). Please check your setup.".format(device_info.ldrom_max_size))
                if not config.is_ldrom_boot():
                    self.logfunc("Overriding LDROM boot setting to True")
                    config.set_ldrom_boot(True)
                if not config.get_ldrom_size() < len(file_data):
                    config.set_ldrom_size(len(file_data))
                    self.logfunc("Overriding LDROM size setting to {}".format(len(file_data)))
                programmed = nuvo.program_ldrom(file_data, config, verify=verify, erase=should_erase)
                # check config
                if programmed:
                    programmed = nuvo.program_config(config, erase = (should_erase))
            else:
                programmed = nuvo.program_aprom(file_data, config=config, verify=verify, erase=should_erase)
                programmed = programmed and nuvo.program_config(config, erase = (should_erase))
        if not programmed:
            raise Exception("Failed to flash image. Please check your setup.")
        self.logfunc("Resulting device configuration:")
        self.logfunc(config.get_config_status())
        self.logfunc("Programming successful!")



    @save_and_restore_pins
    def erase(self):
        with Nuvo51ICP(library=self.lib, logfunc=self.logfunc, _deinit_reset_high=False) as nuvo:
            self.erased = nuvo.mass_erase()
        if not self.erased:
            raise IOError("Failed to erase device")

    @save_and_restore_pins
    def close(self):
        self.lib = None
        pass

    def log(self, text):
        """Logs the text and broadcasts it"""
        target_logger.info(text)
        self.newTextLog.emit(text)

    def autoProgram(self, hexfile, erase=True, verify=True, logfunc=print, waitfunc=None):
        self.logfunc = logfunc
        self.lib.print_func = logfunc
        if erase:
            self.erase()
        self.program(self, hexfile, verify=verify)

    @save_and_restore_pins
    def readConfig(self) -> ConfigFlags:
        config = None
        with Nuvo51ICP(library=self.lib, logfunc=self.logfunc) as nuvo:
            config = nuvo.read_config()
        return config

    @save_and_restore_pins
    def writeConfig(self, config: ConfigFlags):
        with Nuvo51ICP(library=self.lib, logfunc=self.logfunc) as nuvo:
            nuvo.program_config(config)
    