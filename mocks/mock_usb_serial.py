
import io
from lzma import is_check_supported
import math
import os
import re
from chipwhisperer import target_logger
from chipwhisperer.hardware.firmware import cwlite as fw_cwlite
from chipwhisperer.hardware.firmware import cw1200 as fw_cw1200
from chipwhisperer.hardware.firmware import cw305  as fw_cw305
from chipwhisperer.hardware.firmware import cwnano  as fw_nano
from chipwhisperer.hardware.firmware import cwhusky as fw_cwhusky
import usb1 # type: ignore

from chipwhisperer.capture.api.cwcommon import ChipWhispererCommonInterface
try:
    from .mock_sim import MockSim
except:
    from mock_sim import MockSim
from chipwhisperer.hardware.naeusb.serial import USART
from typing import List, Dict, Optional, Union
from chipwhisperer.hardware.naeusb.naeusb import NEWAE_PIDS, NEWAE_VID, CWFirmwareError, SAM_FW_FEATURES, SAM_FW_FEATURE_BY_DEVICE, packuint32, unpackuint32, packuint16, LEN_ADDR_HDR_SIZE, set_len_addr, make_len_addr, NAEUSB_CTRL_IO_MAX, NAEUSB_CTRL_IO_THRESHOLD, _check_sam_feature
# check if we are in typing
import typing
if typing.TYPE_CHECKING:
    from .mock_scope import MockOpenADC # type: ignore
from chipwhisperer.logging import naeusb_logger, scope_logger
from chipwhisperer.hardware.firmware.cwlite import getsome as cwlite_getsome
from chipwhisperer.common.utils import util

default_reg_data = {
  "ADCFREQ_ADDR": {
    "addr": 8,
    "value": [0, 0, 0, 0]
  },
  "ADCREAD_ADDR": {
    "addr": 3,
    "value": [172] # followed by 64999 0's
  },
  "ADVCLOCK_ADDR": {
    "addr": 6,
    "value": [226, 1, 0, 0]
  },
  "CLOCKGLITCH_OFFSET": {
    "addr": 25,
    "value": [0, 0, 0, 0]
  },
  "CLOCKGLITCH_SETTINGS": {
    "addr": 51,
    "value": [0, 0, 0, 0, 0, 0, 0, 0]
  },
  "CW_EXTCLK_ADDR": {
    "addr": 38,
    "value": [3]
  },
  "CW_IOREAD_ADDR": {
    "addr": 59,
    "value": [3, 3, 3, 3, 3, 3, 3, 3]
  },
  "CW_IOROUTE_ADDR": {
    "addr": 55,
    "value": [ 1, 2, 0, 0, 0, 0, 0, 0]
  },
  "CW_TRIGMOD_ADDR": {
    "addr": 40,
    "value": [0]
  },
  "CW_TRIGSRC_ADDR": {
    "addr": 39,
    "value": [32]
  },
  "DECIMATE_ADDR": {
    "addr": 15,
    "value": [0, 0]
  },
  "ECHO_ADDR": {
    "addr": 4,
    "value": [0]
  },
  "EXTFREQ_ADDR": {
    "addr": 5,
    "value": [0, 0, 0, 0]
  },
  "GAIN_ADDR": {
    "addr": 0,
    "value": [0]
  },
  "GLITCH_RECONFIG_RB_ADDR": {
    "addr": 56,
    "value": [0, 0, 0, 0]
  },
  "GLITCHCYCLES_CNT": {
    "addr": 19,
    "value": [0, 0, 0, 0]
  },
  "IODECODETRIG_CFG_ADDR": {
    "addr": 57,
    "value": [0, 0, 0, 0, 0, 0, 0, 0]
  },
  "IODECODETRIG_DATA_ADDR": {
    "addr": 58,
    "value": [0, 0, 0, 0, 0, 0, 0, 0]
  },
  "OFFSET_ADDR": {
    "addr": 26,
    "value": [0, 0, 0, 0]
  },
  "PHASE_ADDR": {
    "addr": 9,
    "value": [0, 0]
  },
  "PRESAMPLES_ADDR": {
    "addr": 17,
    "value": [0, 0, 0, 0]
  },
  "RECONFIG_REG": {
    "addr": 52,
    "value": [0, 0, 0, 0]
  },
  "RETSAMPLES_ADDR": {
    "addr": 18,
    "value": [0, 0, 0, 0]
  },
  "SAD_REFDATA_ADDR": {
    "addr": 54,
    "value": [0, 0, 0, 0]
  },
  "SAD_STATUSCFG_ADDR": {
    "addr": 53,
    "value": [0, 0, 0, 0]
  },
  "SAMPLES_ADDR": {
    "addr": 16,
    "value": [80, 95, 0, 0]
  },
  "SETTINGS_ADDR": {
    "addr": 1,
    "value": [0]
  },
  "STATUS_ADDR": {
    "addr": 2,
    "value": [10]
  },
  "SYSTEMCLK_ADDR": {
    "addr": 7,
    "value": [0, 216, 184, 5]
  },
  "TRIGGER_DUR_ADDR": {
    "addr": 20,
    "value": [31, 249, 194, 0]
  },
  "VERSION_ADDR": {
    "addr": 10,
    "value": [1, 64, 0, 0, 0, 0]
  }
}
CHIPWHISPERER_LITE_PID = 0xACE2
CWLITE_HW_TYPE = 8
CWLITE_HW_VER = 0
CWLITE_REGISTER_VERSION = 1
DEFAULT_CPU = 7384615

def pack_u16(val):
    return bytes([val & 0xff, (val >> 8) & 0xff])
def pack_u32(val):
    return bytes([val & 0xff, (val >> 8) & 0xff, (val >> 16) & 0xff, (val >> 24) & 0xff])

def unpack_u32(data: bytes, i : int) -> int:
    return data[i] | (data[i + 1] << 8) | (data[i + 2] << 16) | (data[i + 3] << 24)
def unpack_u16(data: bytes, i : int) -> int:
    return data[i] | (data[i + 1] << 8)
SIZE_OF_FPGA_BLOCK = 4096
FIFO_SIZE = 32576
SYNC_BYTE = 0xAC

from typing import Tuple, Optional

SETTINGS_RESET     = 0x01
SETTINGS_GAIN_HIGH = 0x02
SETTINGS_GAIN_LOW  = 0x00
SETTINGS_TRIG_HIGH = 0x04
SETTINGS_TRIG_LOW  = 0x00
SETTINGS_ARM       = 0x08
SETTINGS_WAIT_YES  = 0x20
SETTINGS_WAIT_NO   = 0x00
SETTINGS_TRIG_NOW  = 0x40

STATUS_ARM_MASK    = 0x01
STATUS_FIFO_MASK   = 0x02
STATUS_EXT_MASK    = 0x04
STATUS_DCM_MASK    = 0x08
STATUS_DDRCAL_MASK = 0x10
STATUS_DDRERR_MASK = 0x20
STATUS_DDRMODE_MASK= 0x40

# NOTE: PIN_READ_TIO* and GPIO_PIN_TIO* are 1:1
PIN_READ_TIO1 = 0
PIN_READ_TIO2 = 1
PIN_READ_TIO3 = 2
PIN_READ_TIO4 = 3
PIN_READ_MOSI = 4
PIN_READ_MISO = 5
PIN_READ_PDIC = 6
PIN_READ_PDID = 7
PIN_READ_NRST = 8
PIN_READ_SCK = 9

XIO_PIN_START = 4

PIN_FPA = 0x01 # husky only
PIN_TNRST = 0x02
PIN_RTIO1 = 0x04
PIN_RTIO2 = 0x08
PIN_RTIO3 = 0x10
PIN_RTIO4 = 0x20
MODE_OR = 0x00
MODE_AND = 0x01
MODE_NAND = 0x02

# husky only
PIN_USERIO0 = 0x0100
PIN_USERIO1 = 0x0200
PIN_USERIO2 = 0x0400
PIN_USERIO3 = 0x0800
PIN_USERIO4 = 0x1000
PIN_USERIO5 = 0x2000
PIN_USERIO6 = 0x4000
PIN_USERIO7 = 0x8000


XIO_MODE_HIGHZ = 0
_XIO_MODE_ENABLE = 1 << 0
_XIO_MODE_STATE = 1 << 1
XIO_MODE_LOW = _XIO_MODE_ENABLE
XIO_MODE_HIGH = _XIO_MODE_ENABLE | _XIO_MODE_STATE
_XIO_MODE_MASK = XIO_MODE_HIGH

TIO_MODE_HIGHZ = 0
TIO_MODE_STX = 0b00000001
TIO_MODE_SRX = 0b00000010
TIO_MODE_USIO = 0b00000100
TIO_MODE_USII = 0b00001000
TIO_MODE_USINOUT = 0b00011000
TIO_MODE_STXRX = 0b00100010
_TIO_MODE_GPIO_MODE = 0b10000000
_TIO_MODE_GPIO_STATE = 0b01000000
TIO_MODE_GPIO_LOW = _TIO_MODE_GPIO_MODE
TIO_MODE_GPIO_HIGH = _TIO_MODE_GPIO_MODE | _TIO_MODE_GPIO_STATE

SAMPLES_PER_BYTE = 0.75
SAMPLES_PER_WORD = 3
_glitch_triggers = [
    "manual",
    "ext_continuous",
    "continuous",
    "ext_single"
]

class CwLiteStateMachine(object):
    ADDR_TRIGSRC_SIZE = 1
    _addr_to_alias:dict[int, str] = {}
    _alias_to_val:dict[str, str] = {}
    _adc_data: bytearray = bytearray()
    _is_armed: bool = False
    _was_triggered_manually: bool = False
    # husky only
    # _trigger_edges_required: int = 1
    # _trigger_edges_seen: int = 0
    def __init__(self, registers: Optional[io.BytesIO] = None):
        self._slurp_registers(registers)
        self._was_triggered_manually = False

    def _get_status(self, num_bytes: int = 1) -> bytearray:
        status = STATUS_DCM_MASK # TODO: figure out when to enable or disable this
        if self._is_armed:
            status |= STATUS_ARM_MASK
        if self._get_retsamples() > 0:
            status |= STATUS_FIFO_MASK
        if self._was_triggered_manually or self.is_state_trigger_cond(self._get_pins_state()):
            status |= STATUS_EXT_MASK
        return bytearray([status])

    def _set_triggered_adc_data(self, num_bytes: int):
        num_bytes = num_bytes
        num_presamples = unpack_u32(self._alias_to_val["PRESAMPLES_ADDR"], 0)
        NON_TRIGGER_MASK = 3 << 30
        non_trigger_bytes = pack_u32(NON_TRIGGER_MASK) * (math.ceil(num_presamples / SAMPLES_PER_WORD))
        post_trigger_bytes = bytearray([0]*(num_bytes - len(non_trigger_bytes)))
        value = non_trigger_bytes + post_trigger_bytes
        self._adc_data += value
        if len(self._adc_data) > FIFO_SIZE:
            self._adc_data = self._adc_data[len(self._adc_data) - FIFO_SIZE:]


    def _get_adc_data(self, num_bytes: int) -> bytearray:
        actual_bytes = num_bytes-1 # num_bytes includes the sync byte
        value = bytearray([SYNC_BYTE]) + self._adc_data[:actual_bytes]
        if len(value) < num_bytes:
            value += bytearray([0]*(num_bytes-len(value)))
        self._adc_data = self._adc_data[actual_bytes:]
        return value

    def _get_retsamples(self):
        return len(self._adc_data)

    def is_state_trigger_cond(self,state):
        required_state = 0
        pins, mode = self._get_trigger_pins()
        if pins & PIN_TNRST:
            required_state |= 1 << PIN_READ_NRST
        if pins & PIN_RTIO1:
            required_state |= 1 << PIN_READ_TIO1
        if pins & PIN_RTIO2:
            required_state |= 1 << PIN_READ_TIO2
        if pins & PIN_RTIO3:
            required_state |= 1 << PIN_READ_TIO3
        if pins & PIN_RTIO4:
            required_state |= 1 << PIN_READ_TIO4
        # that's all the pins the Lite supports

        if mode == MODE_OR:
            if required_state & state:
                return True
        elif mode == MODE_AND:
            if required_state & state == required_state:
                return True
        elif mode == MODE_NAND:
            if not required_state & state:
                return True
        return False


    def _check_triggered(self, new_state: int, check_prev: bool = True):
        if not self._is_armed:
            return
        if not self.is_state_trigger_cond(new_state):
            return
        # if it was already in a trigger state, don't trigger again
        if check_prev and self.is_state_trigger_cond(self._get_pins_state()):
            return
        # true
        self._set_triggered()

    def _get_trigger_type(self):
        # CLOCKGLITCH_SETTINGS
        resp = self._alias_to_val["CLOCKGLITCH_SETTINGS"]
        return (resp[5] & 0x0C) >> 2
    @property
    def is_manual_glitching(self):
        return self._get_trigger_type() == 0
    @property
    def is_ext_continuous_glitching(self):
        return self._get_trigger_type() == 1
    @property
    def is_continuous_glitching(self):
        return self._get_trigger_type() == 2
    @property
    def is_ext_single_glitching(self):
        return self._get_trigger_type() == 3

    def _set_triggered(self):
        # TODO: Support other trigger types other than ext_single
        # disarm
        self._is_armed = False
        # set the number of trigger edges seen
        # husky only
        # self._trigger_edges_seen += 1

        # populate the samples to return
        # samples = unpack_u32(self._alias_to_val["SAMPLES_ADDR"])
        # ret_sample = math.ceil(samples * SAMPLES_PER_BYTE) + 1 + 256 # 1 sync byte + padding
        ret_sample = FIFO_SIZE
        self._set_triggered_adc_data(ret_sample)

    def _raw2pins(self, raw):
        pins = raw[0] & 0x3F
        if self.ADDR_TRIGSRC_SIZE == 2:
            pins += (raw[1] << 8)
        mode = raw[0] >> 6
        return(pins, mode)

    def _get_trigger_pins(self):
        resp = self._alias_to_val["CW_TRIGSRC_ADDR"]
        pins, mode = self._raw2pins(resp)
        return(pins, mode)

    def _get_pin_state(self, pin_num):
        result = unpack_u16(self._alias_to_val["CW_IOREAD_ADDR"], 0)
        return (result >> pin_num) & 0x01
    def _get_pins_state(self):
        result = unpack_u16(self._alias_to_val["CW_IOREAD_ADDR"], 0)
        return result
    
    def _set_cw_ioroute(self, data: bytearray):
        current_state = self._get_pins_state()
        new_state = current_state
        for pin_num in range(len(data)):
            new_pin_state = 0
            if pin_num >= XIO_PIN_START:
                if data[pin_num] & XIO_MODE_HIGH == XIO_MODE_HIGH:
                    new_pin_state = 1
            else:
                if data[pin_num] & TIO_MODE_GPIO_HIGH == TIO_MODE_GPIO_HIGH:
                    new_pin_state = 1
                    _val = _val
            _val = (new_state & ~(1 << pin_num)) | (new_pin_state << pin_num)
            new_state = (new_state & ~(1 << pin_num)) | (new_pin_state << pin_num)
        self._check_triggered(new_state)
        new_ioread_data = pack_u16(new_state)
        self._alias_to_val["CW_IOREAD_ADDR"][0] = new_ioread_data[0]
        self._alias_to_val["CW_IOREAD_ADDR"][1] = new_ioread_data[1]
        self._alias_to_val["CW_IOROUTE_ADDR"] = data

    def _get_adc_src(self):
        result = self._alias_to_val["ADVCLOCK_ADDR"]
        result[0] = result[0] & 0x07
        if result[0] & 0x04:
            dcminput = "extclk"
        else:
            dcminput = "clkgen"

        if result[0] & 0x02:
            dcmout = 1
        else:
            dcmout = 4

        if result[0] & 0x01:
            source = "extclk"
        else:
            source = "dcm"
        return (source, dcmout, dcminput)

    def _getClkGenMul(self):
        result = self._alias_to_val["ADVCLOCK_ADDR"]
        val = result[1]
        val += 1
        return val

    def _getClkGenDiv(self):
        result = self._alias_to_val["ADVCLOCK_ADDR"]
        val = result[2]
        val += 1
        return val

    def _calc_adc_freq(self):
        source, dcmout, dcminput = self._get_adc_src()
        sysfreq = unpack_u32(self._alias_to_val["SYSTEMCLK_ADDR"], 0)
        if dcminput == "clkgen":
            inpfreq = sysfreq
        else: # ext
            inpfreq = unpack_u32(self._alias_to_val["EXTFREQ_ADDR"], 0)
        mul = self._getClkGenMul()
        div = self._getClkGenDiv()
        samplefreq = float(sysfreq) / float(pow(2,23))
        return (((inpfreq * mul) / div) * dcmout) / samplefreq

    def _set_settings(self, data: bytearray):
        settings: int = data[0]
        was_armed = self._is_armed
        if settings & SETTINGS_RESET:
            self._is_armed = False
            self._was_triggered_manually = False
        if settings & SETTINGS_ARM and self._was_triggered_manually == False:
            self._is_armed = True
        else:
            self._is_armed = False
        # only if status indicates it was already armed
        if settings & SETTINGS_TRIG_NOW and (was_armed):
            self._set_triggered()
            self._was_triggered_manually = True
        else:
            self._was_triggered_manually = False
        self._alias_to_val["SETTINGS_ADDR"][0] = settings

    def _set_trigsrc(self, data):
        self._alias_to_val["CW_TRIGSRC_ADDR"] = data
        self._check_triggered(self._get_pins_state(), False)

    def set_initial(self):
        for addr in self._addr_to_alias:
            alias = self._addr_to_alias[addr]
            value = default_reg_data[alias]['value']
            if alias == "VERSION_ADDR":
                version_data = [0]*6
                version_data[1] = (CWLITE_HW_TYPE << 3) | CWLITE_HW_VER
                version_data[0] = (CWLITE_REGISTER_VERSION & 0xF)
                value = version_data
            self._alias_to_val[alias] = bytearray(value)

    def get_addr(self, alias:str) -> int:
        for addr in self._addr_to_alias:
            if self._addr_to_alias[addr] == alias:
                return addr
        return None

    def _check_reg(self, addr: Union[str,int]) -> str:
        if isinstance(addr, int):
            if addr not in self._addr_to_alias:
                target_logger.error("Register 0x{:02x} not found".format(addr))
                return None
            addr = self._addr_to_alias[addr]
        if addr not in self._addr_to_alias.values():
            target_logger.error("Register {} not found".format(addr))
            return None
        return addr

    def get_register(self, addr: Union[str, int], num_bytes: int) -> bytearray:
        num_bytes = int(num_bytes)
        addr = self._check_reg(addr)
        if not addr:
            return bytearray([0]*num_bytes)
        
        # special registers
        if addr == "ADCREAD_ADDR":
            value = self._get_adc_data(num_bytes)
        elif addr == "RETSAMPLES_ADDR":
            value = packuint32(self._get_retsamples())
        elif addr == "ADCFREQ_ADDR":
            value = packuint32(int(self._calc_adc_freq()))
        elif addr == "EXTFREQ_ADDR":
            value = packuint32(DEFAULT_CPU)
        elif addr == "STATUS_ADDR":
            value = self._get_status()
        # husky only
        # elif addr == "EDGE_TRIGGER_COUNT":
        #     value = packuint16(self._trigger_edges_seen)
        else:
            value = self._alias_to_val[addr]

        if addr == "ADVCLOCK_ADDR":
            # set the 0x40 bit (dcmADCLocked) and the 0x20 bit (dcmCLKGENLocked) to 1 in value[0]
            # set the 0x80 bit (ADVCLOCK_ADDR present) on value[0]
            value[0] = value[0] | 0x60 | 0x80
            # set the 0x02 bit (finished loading value) in value[3]
            value[3] = value[3] | 0x02

        if num_bytes > len(value):
            target_logger.warn("Register 0x{:02x} ({}) is only {} bytes long, but requested {}".format(self.get_addr(addr), addr, len(value), num_bytes))
            # extend it to however long we need
            value += bytearray([0]*(num_bytes-len(value)))
        return value[:num_bytes]

    def set_register(self, addr: int, value: bytearray):
        addr = self._check_reg(addr)
        if not addr:
            return
        # copy in case it's a memory reference
        value = bytearray(value)
        if addr == "RECONFIG_REG":
            # PartialReconfiguration uses this as a test
            if value[0] == 0x1A and len(value) == 1:
                return
        elif addr == "SETTINGS_ADDR":
            self._set_settings(value)
            return
        elif addr == "CW_IOROUTE_ADDR":
            self._set_cw_ioroute(value)
        elif addr == "CW_TRIGSRC_ADDR":
            self._set_trigsrc(value)
        # husky only
        # elif addr == "EDGE_TRIGGER_COUNT":
        #     self._trigger_edges_required = unpack_u16(value, 0)
        elif len(self._alias_to_val[addr]) > len(value) and addr != "RECONFIG_REG":
            target_logger.error("Setting register 0x{:02x} ({}) with {} bytes, but it's only {} bytes long".format(self.get_addr(addr), addr, len(value), len(self._alias_to_val[addr])))
            # concatenate the new value with the old value
            self._alias_to_val[addr] = bytearray(value) + self._alias_to_val[addr][len(value):]
        else:
            self._alias_to_val[addr] = value

    def _slurp_registers(self, register_data):
        """ Parse Verilog register defines file so we can access register address
        definitions by name.

        """
        self.verilog_define_matches = 0

        if type(register_data) == io.BytesIO:
            registers = io.TextIOWrapper(register_data)
        else:
            if not os.path.isfile(register_data):
                scope_logger.error('Cannot find %s' % register_data)
            registers = open(register_data, 'r', encoding='utf-8')
        define_regex_base  =   re.compile(r'`define')
        define_regex_reg   =   re.compile(r'`define\s+?REG_')
        define_regex_radix =   re.compile(r'`define\s+?(\w+).+?\'([bdh])([0-9a-fA-F]+)')
        define_regex_noradix = re.compile(r'`define\s+?(\w+?)\s+?(\d+)')
        block_offset = 0
        for define in registers:
            if define_regex_base.search(define):
                reg = define_regex_reg.search(define)
                match = define_regex_radix.search(define)
                if match:
                    self.verilog_define_matches += 1
                    if match.group(2) == 'b':
                        radix = 2
                    elif match.group(2) == 'h':
                        radix = 16
                    else:
                        radix = 10
                    addr_str = match.group(1)
                    # not registers, just values
                    if addr_str == "CLOCKGLITCH_OFFSET_LEN" or addr_str == "REGISTER_VERSION":
                        continue

                    addr_num = int(match.group(3),radix) + block_offset
                    self._addr_to_alias[addr_num] = addr_str
                    scope_logger.debug('_slurp_registers: setting %s to %d' % (match.group(1), int(match.group(3),radix) + block_offset))
                else:
                    match = define_regex_noradix.search(define)
                    if match:
                        self.verilog_define_matches += 1
                        addr_str = match.group(1)
                        if addr_str == "CLOCKGLITCH_OFFSET_LEN" or addr_str == "REGISTER_VERSION":
                            continue
                        addr_num = int(match.group(2),10) + block_offset
                        self._addr_to_alias[addr_num] = addr_str
                        scope_logger.debug('_slurp_registers: setting %s to %d' % (match.group(1), int(match.group(2),10) + block_offset))
                    else:
                        scope_logger.warning("Couldn't parse line: %s", define)
        registers.close()
        scope_logger.debug("Found %d Verilog register definitions." % self.verilog_define_matches)
    

class MockCWLiteUSBDevice:
    def __init__(self):
        self._registers_data = None
        self._mock_load_state_machine()

    def getProductId(self):
        return CHIPWHISPERER_LITE_PID
    def getSerialNumber(self):
              #'50203220343043543030322037313039'
        return '00000000000000000000000000000000'
    def getBusNumber(self):
        return 69
    def getDeviceAddress(self):
        return 69
    def getProduct(self):
        return 'ChipWhisperer Lite'
    def mock_getFWVersion(self):
        fw_ver = list(fw_cwlite.fwver)
        fw_ver.append(0)
        return fw_ver
    def _mock_load_state_machine(self):
        self._registers_data = cwlite_getsome("registers.v")
        if not isinstance(self._registers_data, io.BytesIO):
            self._registers_data = io.BytesIO(self._registers_data)
        self.state_machine = CwLiteStateMachine(self._registers_data)
        self.state_machine.set_initial()
    def mock_getRegister(self, addr: int, num_bytes: int):
        return self.state_machine.get_register(addr, num_bytes)
    def mock_setRegister(self, addr: int, value: bytearray):
        self.state_machine.set_register(addr, value)
    # def mock_reset(self):
    #     self._mock_load_state_machine()



class MockNAEUSBBackend:
    def __init__(self):
        self.device = None
    def open(self, serial_number : Optional[str]=None, idProduct : Optional[List[int]]=None, 
        connect_to_first : bool =False, hw_location : Optional[Tuple[int, int]]=None) -> Optional[usb1.USBDeviceHandle]:
        self.device = MockCWLiteUSBDevice()
        return self.device
    def close(self):
        self.device = None
    @property
    def pid(self):
        if not self.device:
            return None
        return self.device.getProductId()

from chipwhisperer.hardware.naeusb.programmer_avr import AVRISP

class NAEUSBIface:
    CMD_FW_VERSION = 0x17
    CMD_CDC_SETTINGS_EN = 0x31

    CMD_READMEM_BULK = 0x10
    CMD_WRITEMEM_BULK = 0x11
    CMD_READMEM_CTRL = 0x12
    CMD_WRITEMEM_CTRL = 0x13
    CMD_MEMSTREAM = 0x14
    CMD_WRITEMEM_CTRL_SAM3U = 0x15
    CMD_SMC_READ_SPEED = 0x27

    CMD_FW_BUILD_DATE = 0x40

    # FPGA commands
    CMD_FPGA_STATUS = 0x15
    CMD_FPGA_PROGRAM = 0x16

    CMD_AVR_PROGRAM = 0x21

    # BITORDER_DEFAULT = 0x00
    # BITORDER_REVERSE = 0x01
    # BITORDER_REVERSE16 = 0x02

    # PROG_MODE_SERIAL = 0x00
    # PROG_MODE_PARALLEL = 0x01
    # PROG_MODE_PARALLEL16 = 0x02


    def __init__(self):
        self.usbtx = MockNAEUSBBackend()
        self.is_connected = False
        self.MPSSE_enabled = False
        self.mock_target_sim: MockSim = None
        self.scope: ChipWhispererCommonInterface = None

    def set_smc_speed(self, val : int):
        raise Exception("Not implemented!")
    def set_husky_tms_wr(self, num):
        raise Exception("Not implemented!")
    def get_serial_ports(self) -> Optional[List[Dict[str, int]]]:
        """ something like `[{'port': '/dev/ttyACM0', 'interface': 1}]` """
        raise Exception("Not implemented!")

    def clear_sam_errors(self):
        raise Exception("Not implemented!")
    def check_sam_errors(self):
        raise Exception("Not implemented!")
    def enterBootloader(self, forreal : bool=False):
        raise Exception("Not implemented!")
    
    
    def reset(self):
        raise Exception("Not implemented!")
    def read(self, dlen : int, timeout : int=2000) -> bytearray:
        raise Exception("Not implemented!")
    def writeBulkEP(self, data : bytearray, timeout = None):
        raise Exception("Not implemented!")
    
    # unused
    def cmdReadStream_getStatus(self) -> Tuple[int, int, int]:
        raise Exception("Not implemented!")
    
    #implemented

    def get_cdc_settings(self) -> list:
        raise Exception("Not implemented!")
        # if self.check_feature("CDC"):
        #     return [0, 0, 0, 0]

    def set_cdc_settings(self, port : Tuple=(1, 1, 0, 0)):
        raise Exception("Not implemented!")

    def cmdReadMem(self, addr : int, dlen : int) -> bytearray:
        raise Exception("Not implemented!")
    def cmdWriteMem(self, addr : int, data : bytearray):
        raise Exception("Not implemented!")

    def set_led_settings(self, setting=0):
        raise Exception("Not implemented!")

    def get_led_settings(self) -> int:
        raise Exception("Not implemented!")

    def flushInput(self):
        raise Exception("Not implemented!")
    def initStreamModeCapture(self, dlen : int, dbuf_temp : bytearray, timeout_ms : int=1000,
        is_husky : bool=False, segment_size : int=0):
        raise Exception("Not implemented!")
    def cmdReadStream_isDone(self, is_husky : bool=False) -> bool:
        raise Exception("Not implemented!")
    def cmdReadStream(self, is_husky : bool=False) -> Tuple[int, int]:
        raise Exception("Not implemented!")
    def sendCtrl(self, cmd : int, value : int=0, data : bytearray=bytearray()):
        raise Exception("Not implemented!")
    def readCtrl(self, cmd : int, value : int=0, dlen : int=0) -> bytearray:
        raise Exception("Not implemented!")

    def cmdReadStream_size_of_fpgablock(self) -> int:
        return 4096
    def cmdReadStream_bufferSize(self, dlen : int):
        num_samplebytes = int(math.ceil(float(dlen) * 4 / 3))
        num_blocks = int(math.ceil(float(num_samplebytes) / 4096))
        num_totalbytes = num_samplebytes + num_blocks
        num_totalbytes = int(math.ceil(float(num_totalbytes) / 4096) * 4096)
        return num_totalbytes

    def con(self, idProduct : Tuple[int]=(0xACE2,), connect_to_first : bool=False, 
        serial_number : Optional[str]=None, hw_location : Optional[Tuple[int, int]]=None, **kwargs) -> int:
        self.is_connected = True
        self.usbtx.open(serial_number, idProduct, connect_to_first, hw_location)
        self.snum = self.usbtx.device.getSerialNumber()
        return self.usbtx.device.getProductId()

    def close(self):
        self.usbtx.close()
        self._clear_mock_target()
        self.is_connected = False
    def usbdev(self):
        raise AttributeError("Do Not Call Me")
    def check_feature(self, feature, raise_exception=False):
        prod_id = self.usbtx.device.getProductId()
        fw_ver = self.readFwVersion()
        fw_ver_str = '{}.{}.{}'.format(fw_ver[0], fw_ver[1], fw_ver[2])
        ret =  _check_sam_feature(feature, fw_ver_str, prod_id)
        if not ret:
            naeusb_logger.info("Feature {} not available".format(feature))
            if raise_exception:
                raise CWFirmwareError("Feature {} not available. FW {} required (have {})".format(feature, SAM_FW_FEATURE_BY_DEVICE[prod_id][feature], fw_ver_str))
        return ret
    def feature_list(self):
        feature_list = []
        for feature in SAM_FW_FEATURES:
            if self.check_feature(feature):
                feature_list.append(feature)
        return feature_list
    def get_fw_build_date(self) -> str:
        return "2024-01-01"
    
    def readFwVersion(self) -> bytearray:
        return self.usbtx.device.mock_getFWVersion()

    def get_possible_devices(self, idProduct : List[int]) -> usb1.USBDevice:
        return [self.usbtx.device]
    def is_MPSSE_enabled(self):
        if self.check_feature("MPSSE_ENABLED"):
            return self.MPSSE_enabled
    def enable_MPSSE(self):
        if self.check_feature("MPSSE_ENABLED"):
            self.MPSSE_enabled = True
    def hw_location(self):
        return (self.usbtx.device.getBusNumber(), self.usbtx.device.getDeviceAddress())

    # Mock functions
    def _set_mock_target(self, target: MockSim):
        self.mock_target_sim = target  
    
    def _clear_mock_target(self):
        self.mock_target_sim = None
    
    def _set_mock_scope(self, scope: ChipWhispererCommonInterface):
        self.scope = scope
    
    def _clear_mock_scope(self):
        self.scope = None

    def _trigger_scope(self):
        raise Exception("Not implemented!")


class MockNAEUSB(NAEUSBIface):


    stream = False

    fwversion_latest = [0, 11]
    SETTINGS_TRIG_NOW = 0x40 # setting when triggered
    SETTINGS_ADDR = 1 # register for trigger
    def __init__(self):
        super().__init__()
        self.is_open = False
        self.serial_baud = 0
        self.is_capturing = False
        self._max_num_samples = 0
        self._led_settings = 0
        self.cdc_settings = (1, 1, 0, 0)

    # only used for the FPGA programmer; not necessary to implement
    def writeBulkEP(self, data : bytearray, timeout = None):
        pass

    def flushInput(self):
        pass
    def set_led_settings(self, setting=0):
        self._led_settings = setting
    def get_led_settings(self) -> int:
        return self._led_settings
    def get_cdc_settings(self) -> List:
        return self.cdc_settings
    def set_cdc_settings(self, port : Tuple=(1, 1, 0, 0)):
        self.cdc_settings = port


    # Only used by Husky/Pro
    def _get_retsamples(self, is_husky = False):
        return unpack_u32(self.usbtx.device.mock_getRegister("RETSAMPLES_ADDR", 4), 0)
    def _check_still_capturing(self, is_husky = False):
        if self.is_capturing:
            ret_samples = self._get_retsamples(is_husky)
            if ret_samples >= self._max_num_samples:
                self.is_capturing = False
    def initStreamModeCapture(self, dlen : int, dbuf_temp : bytearray, timeout_ms : int=1000,
        is_husky : bool=False, segment_size : int=0):
        self._max_num_samples = dlen
        self.is_capturing = True
    def cmdReadStream_isDone(self, is_husky : bool=False) -> bool:
        self._check_still_capturing(is_husky)
        if self.is_capturing:
            return False
        return True
    def cmdReadStream(self, is_husky : bool=False) -> Tuple[int, int]:
        self._check_still_capturing(is_husky)
        return self._get_retsamples(), self.is_capturing

    # getting/setting registers
    def cmdReadMem(self, addr : int, dlen : int) -> bytearray:
        return self.usbtx.device.mock_getRegister(addr, dlen)
    def cmdWriteMem(self, addr : int, data : bytearray):
        self.usbtx.device.mock_setRegister(addr, data)


    def readCtrl(self, cmd : int, value : int=0, dlen : int=0) -> bytearray:
        if cmd == USART.CMD_USART0_CONFIG: # used by the uart interface to determine the numwaiting of the target
            value = value & 0xFF
            if value == USART.USART_CMD_NUMWAIT:
                return bytearray([self.mock_target_sim.in_waiting()])
            elif value == USART.USART_CMD_NUMWAIT_TX:
                return bytearray([0])
        elif cmd == USART.CMD_USART0_DATA:
            return bytearray(self.mock_target_sim.read_from_target(dlen))
        elif cmd == self.CMD_FPGA_STATUS: # Used by the FPGA interface to check if this is programmed
            return bytearray([0xff, 0xff, 0xff, 0xff]) # all true
        elif cmd == self.CMD_FPGA_PROGRAM:
            target_logger.warn("FPGA programming not implemented")
        else:
            raise Exception("Not implemented!")
        return bytearray([0])
    
    def sendCtrl(self, cmd : int, value : int=0, data : bytearray=bytearray()):
        if cmd == USART.CMD_USART0_CONFIG:
            value = value & 0xFF
            if value == USART.USART_CMD_INIT:
                self.serial_baud = unpack_u32(data, 0)
                return
            elif value == USART.USART_CMD_ENABLE:
                self.is_open = True
                return
            elif value == USART.USART_CMD_DISABLE:
                self.is_open = False
                return
        elif cmd == USART.CMD_USART0_DATA:
            self.mock_target_sim.send_to_target(data)
            return
        return

if __name__ == "__main__":
    thing = MockCWLiteUSBDevice()
    print(str(thing.state_machine))
