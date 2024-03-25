#!/usr/bin/python
# HIGHLEVEL_CLASSLOAD_FAIL_FUNC_WARN
# -*- coding: utf-8 -*-
#
# Copyright (c) 2013-2022, NewAE Technology Inc
# All rights reserved.
#
# Authors: Colin O'Flynn
#
# Find this and more at newae.com - this file is part of the chipwhisperer
# project, http://www.chipwhisperer.com
#
#=================================================
from chipwhisperer.capture.scopes import OpenADC
from chipwhisperer.capture.scopes.cwhardware.ChipWhispererFWLoader import CWLite_Loader, CW1200_Loader, CWHusky_Loader
from chipwhisperer.capture.scopes.cwhardware.ChipWhispererFWLoader import FWLoaderConfig
from chipwhisperer.logging import *
from chipwhisperer.hardware.naeusb.fpga import FPGA
from chipwhisperer.hardware.naeusb.serial import USART
from chipwhisperer.capture.scopes.cwhardware import ChipWhispererDecodeTrigger, ChipWhispererExtra, \
     ChipWhispererSAD, ChipWhispererHuskyClock
from chipwhisperer.capture.scopes.cwhardware.ChipWhispererHuskyMisc import XilinxDRP, XilinxMMCMDRP, LEDSettings, HuskyErrors, \
        USERIOSettings, XADCSettings, LASettings, ADS4128Settings
from chipwhisperer.capture.scopes._OpenADCInterface import OpenADCInterface, HWInformation, GainSettings, TriggerSettings, ClockSettings
from chipwhisperer.capture.api.cwcommon import ChipWhispererSAMErrors

try:
    from chipwhisperer.capture.trace import TraceWhisperer
    from chipwhisperer.capture.trace.TraceWhisperer import UARTTrigger
except Exception as e:
    tracewhisperer_logger.info("Could not import TraceWhisperer: {}".format(e))
    TraceWhisperer = None # type: ignore
from chipwhisperer.common.utils import util
import time
import numpy as np

# Mock stuff
from chipwhisperer.capture.targets import SimpleSerial2
from chipwhisperer.capture.targets._base import TargetTemplate
from .mock_sim import MockSim
from .mock_ss2_sim import SimpleSerial2TargetSim 
import inspect
from .mock_usb_serial import MockNAEUSB

CODE_READ              = 0x80
CODE_WRITE             = 0xC0

class dummy_object(object):
    def __hasattr__(self):
        return True
    def __getattr__(self, __name):
        if __name in self.__dict__:
            return self.__dict__[__name]
        return dummy_object()
    def __setattr__(self, __name, __value) -> None:
        self.__dict__[__name] = __value
    def _dict_repr(self):
        # remove all the private attributes
        return {k: v for k, v in self.__dict__.items() if not k.startswith('_')}

class _dict_repr_obj(object):
    def _dict_repr(self):
        # remove all the private attributes
        return {k: v for k, v in self.__dict__.items() if not k.startswith('_')}

class MockOpenADCInterface(OpenADCInterface):
    """
    Mock version of OpenADCInterface

    just overriding triggerNow so that it doesn't wait between setting and clearing the trigger
    """
    SETTINGS_TRIG_NOW = 0x40
    STATUS_ARM_MASK = 0x01
    @property
    def is_armed(self):
        val = self.getStatus() & self.STATUS_ARM_MASK
        return val
    def triggerNow(self):
        initial = self.settings(True)
        self.setSettings(initial | self.SETTINGS_TRIG_NOW)
        # time.sleep(0.05) no wait, this is a mock
        self.setSettings(initial & ~self.SETTINGS_TRIG_NOW)



class MockProgrammer:
    """
    Mock version of programmer
    
    No testing going on here, just stubs so that calls to the programmer don't fail
    """
    def __init__(self):
        self.newTextLog = util.Signal()
        self._scope = None
    def open(self):
        pass
    @property
    def scope(self):
        if self._scope:
            return self._scope
        return None
    @scope.setter
    def scope(self, value):
        self._scope = value
    def save_pin_setup(self):
        pass
    def restore_pin_setup(self):
        pass
    def writeFuse(self, value, lfuse):
        pass
    def readFuse(self, value):
        return 0
    def eraseChip(self, memtype="flash"):
        return True
    def enablePDI(self, enabled):
        pass
    def open_and_find(self, log_func=None):
        return self.find()
    def open_port(self, baud=0):
        return True
    def enableSlowClock(self, enabled=False):
        pass
    def set_pins(self):
        pass
    def setUSBInterface(self, iface):
        pass
    def enableISP(self, enabled=True):
        pass
    def find(self, slow_delay=False):
        return [0,0,0], 0
    def program(self, filename, memtype="flash", verify=True):
        return True
    def erase(self, memtype="flash"):
        return True
    def close(self):
        pass
    def log(self, text):
        """Logs the text and broadcasts it"""
        target_logger.info(text)
        self.newTextLog.emit(text)
    def autoProgram(self, hexfile, erase, verify, logfunc, waitfunc):
        return True

class MockScopeType(util.DisableNewAttr):
    """ 
    Mock version of OpenADCInterface_NAEUSBChip
    """
    _name = "NewAE USB (CWLite/CW1200)"

    def __init__(self):
        super().__init__()
        self.ser = MockNAEUSB()

        self.fpga = FPGA(self.ser)
        self.xmega = MockProgrammer()
        self.avr = MockProgrammer()
        self.usart = USART(self.ser)
        self.serialstm32f = MockProgrammer()

        self.scope = None
        self.last_id = None
        self.registers = None

        self.cwFirmwareConfig = {
            0xACE2:FWLoaderConfig(CWLite_Loader()),
            0xACE3:FWLoaderConfig(CW1200_Loader()),
            0xACE5:FWLoaderConfig(CWHusky_Loader())
        }

    def con(self, sn=None, idProduct=None, bitstream=None, force=False, prog_speed=1E6, registers=None, **kwargs):
        if idProduct:
            nae_products = [idProduct]
        else:
            nae_products = [0xACE2, 0xACE3, 0xACE5]
        found_id = self.ser.con(idProduct=nae_products, serial_number=sn, **kwargs)
        if force:
            scope_logger.error("Attempting to program! FPGA programming not implemented")
        #     self.fpga.eraseFPGA()
        #     scope_logger.debug("Forcing new firmware")
        #     time.sleep(0.5)

        if found_id != self.last_id:
            scope_logger.info("Detected ChipWhisperer with USB ID %x - switching firmware loader" % found_id)
        self.last_id = found_id

        self.getFWConfig().setInterface(self.fpga)
        if not registers:
            self.registers = self.getFWConfig().loader._registers
        else:
            self.registers = registers

        try:
            if bitstream is None:
                if not self.fpga.isFPGAProgrammed():
                    scope_logger.error("Attempting to program! FPGA programming not implemented")
                    # self.fpga.FPGAProgram(self.getFWConfig().loader.fpga_bitstream(), prog_speed=prog_speed)
            else:
                scope_logger.error("Attempting to program! FPGA programming not implemented")
                # with open(bitstream, "rb") as bsdata:
                #     self.fpga.FPGAProgram(bsdata, prog_speed=prog_speed)
        except:
            self.ser.close()
            raise

    def reload_fpga(self, bitstream, prog_speed=1E6):
        if bitstream is None:
            raise NotImplementedError("Oops I forgot about that")
        scope_logger.error("Attempting to program! FPGA programming not implemented")
        return

        bsdate = time.ctime(os.path.getmtime(bitstream))
        scope_logger.debug("FPGA: Using file %s"%bitstream)
        scope_logger.debug("FPGA: File modification date %s"%bsdate)

        bsdata = open(bitstream, "rb")

        try:
            self.fpga.FPGAProgram(bsdata, prog_speed=prog_speed)
        except:
            self.ser.close()
            raise

    def dis(self):
        if not self.ser is None:
            self.ser.close()
            self.ser = None
        else:
            scope_logger.error("Scope already disconnected!")

    def __del__(self):
        if not self.ser is None:
            self.ser.close()
            self.ser = None

    def getFWConfig(self):
        try:
            return self.cwFirmwareConfig[self.last_id]
        except KeyError as e:
            return FWLoaderConfig(CWLite_Loader())

    def get_name(self):
        return self._name




class MockOpenADC(OpenADC):
    """Mock OpenADC scope object.

    This implements a mock OpenADC scope.
    This only supports mocking a Chipwhisperer Lite for now.

     *  :attr:`scope.gain <chipwhisperer.capture.scopes._OpenADCInterface.GainSettings>`
     *  :attr:`scope.adc <chipwhisperer.capture.scopes._OpenADCInterface.TriggerSettings>`
     *  :attr:`scope.clock <chipwhisperer.capture.scopes._OpenADCInterface.TriggerSettings>`
     *  :attr:`scope.io <chipwhisperer.capture.scopes.cwhardware.ChipWhispererExtra.GPIOSettings>`
     *  :attr:`scope.trigger <chipwhisperer.capture.scopes.cwhardware.ChipWhispererExtra.TriggerSettings>`
     *  :attr:`scope.glitch (Lite/Pro) <chipwhisperer.capture.scopes.cwhardware.ChipWhispererGlitch.GlitchSettings>`
     *  :meth:`scope.default_setup <.OpenADC.default_setup>`
     *  :meth:`scope.con <.OpenADC.con>`
     *  :meth:`scope.dis <.OpenADC.dis>`
     *  :meth:`scope.arm <.OpenADC.arm>`
     *  :meth:`scope.get_last_trace <.OpenADC.get_last_trace>`
     *  :meth:`scope.get_serial_ports <.ChipWhispererCommonInterface.get_serial_ports>`

    Inherits from :class:`chipwhisperer.capture.api.cwcommon.ChipWhispererCommonInterface`
    """

    _name = "ChipWhisperer/OpenADC"

    def __init__(self):
        # self.qtadc = openadc_qt.OpenADCQt()
        # self
        super().__init__()
        self.enable_newattr()

        # Bonus Modules for ChipWhisperer
        self.advancedSettings = None
        self.advancedSAD = None
        self.digitalPattern = None

        self._is_connected = False
        self.data_points = []
        self._is_husky = False
        self._is_husky_plus = False

        # self.scopetype = OpenADCInterface_NAEUSBChip(self.qtadc)
        self.connectStatus = True
        # self.disable_newattr()
        # Mock attributes
        self.waiting_for_trigger_high = False
        self.trigger_state = False
        self.current_mock_targets: list[MockSim] = []
        self.reset_rate = 0.0
        self.success_rate = 0.0
    
    # mock functions
    @property
    def reset_rate(self) -> float:
        """
        The probability that a test run will randomly result in a reset during glitching.
        
        Defaults to 0.0.
        """
        return self._reset_rate
    @reset_rate.setter
    def reset_rate(self, rate: float):
        self._reset_rate = rate
        
    @property
    def success_rate(self) -> float:
        """
        The probability that a test run will randomly result in a successful glitch.
        
        Defaults to 0.0.
        """
        return self._success_rate
    @success_rate.setter
    def success_rate(self, rate: float):
        self._success_rate = rate

    def mock_trigger_callback(self, high: bool) -> int:
        if high:
            self.waiting_for_trigger_high = False
        was_armed = self.sc.is_armed == 1
        if high:
            self.sc.triggerNow()
        if high and was_armed and ((self.io.glitch_hp or self.io.glitch_lp or (self._is_husky and self.glitch.enabled)) or self.io.hs2 == 'glitch'):
            res = np.random.rand()
            if res < self.success_rate:
                return 1
            if res < self.reset_rate:
                return -1
        return 0
        

    def _get_usart(self) -> USART:
        # get the current stack trace
        stack = inspect.stack()
        if stack[1].function == "con" and stack[2].function == 'con' and 'self' in stack[2].frame.f_locals:
            if isinstance(stack[2].frame.f_locals['self'], SimpleSerial2):
                mock_target = SimpleSerial2TargetSim(self.mock_trigger_callback)
                self.current_mock_targets.append(mock_target)
                self.scopetype.usart._usb._set_mock_target(mock_target)
            elif issubclass(stack[2].frame.f_locals['self'].__class__, TargetTemplate):
                raise NotImplementedError("Target simulators besides SS2 not implemented yet")
        return self.scopetype.usart

    def con(self, sn=None, idProduct=None, bitstream=None, force=False, prog_speed=10E6, **kwargs):
        """Connects to attached chipwhisperer hardware (Lite, Pro, or Husky)

        Args:
            sn (str): The serial number of the attached device. Does not need to
                be specified unless there are multiple devices attached.
            idProduct (int): The product ID of the ChipWhisperer. If None, autodetects product ID. Optional.
            bitstream (str): Path to bitstream to program. If None, programs default bitstream. Optional.
            force (bool): Force reprogramming of bitstream. If False, only program bitstream if no bitstream
                is currently programmed. Optional.

        Returns:
            True if connection is successful, False otherwise

        .. versionchanged:: 5.5
            Added idProduct, bitstream, and force parameters.
        """
        self._read_only_attrs = []
        self._saved_sn = sn

        # MOCK
        # self.scopetype = OpenADCInterface_NAEUSBChip()
        self.scopetype = MockScopeType()

        self.scopetype.con(sn, idProduct, bitstream, force, prog_speed, **kwargs)
        # MOCK
        # self.sc = OpenADCInterface(self.scopetype.ser, self.scopetype.registers) # important to instantiate this before other FPGA components, since this does an FPGA reset
        self.sc = MockOpenADCInterface(self.scopetype.ser, self.scopetype.registers)
        self.hwinfo = HWInformation(self.sc)
        cwtype = self._getCWType()
        if cwtype in ["cwhusky", "cwhusky-plus"]:
            self.sc._is_husky = True
        self.sc._setReset(True)
        self.sc._setReset(False)

        self.adc = TriggerSettings(self.sc)
        self.gain = GainSettings(self.sc, self.adc)

        self.pll = None
        self.advancedSettings = ChipWhispererExtra.ChipWhispererExtra(cwtype, self.scopetype, self.sc)
        self.glitch_drp1 = None
        self.glitch_drp2 = None
        self.la_drp = None
        self.glitch_mmcm1 = None
        self.glitch_mmcm2 = None
        self.la_mmcm = None
        self.trace = None

        util.chipwhisperer_extra = self.advancedSettings

        if cwtype == "cw1200":
            self.SAD = ChipWhispererSAD.ChipWhispererSAD(self.sc)
            self.decode_IO = ChipWhispererDecodeTrigger.ChipWhispererDecodeTrigger(self.sc)

        if cwtype in ["cwhusky", "cwhusky-plus"]:
            # self.pll = ChipWhispererHuskyClock.CDCI6214(self.sc)
            self._fpga_clk = ClockSettings(self.sc, hwinfo=self.hwinfo, is_husky=True)
            self.glitch_drp1 = XilinxDRP(self.sc, "CG1_DRP_DATA", "CG1_DRP_ADDR", "CG1_DRP_RESET")
            self.glitch_drp2 = XilinxDRP(self.sc, "CG2_DRP_DATA", "CG2_DRP_ADDR", "CG2_DRP_RESET")
            self.la_drp = XilinxDRP(self.sc, "LA_DRP_DATA", "LA_DRP_ADDR", "LA_DRP_RESET")
            self.glitch_mmcm1 = XilinxMMCMDRP(self.glitch_drp1)
            self.glitch_mmcm2 = XilinxMMCMDRP(self.glitch_drp2)
            self.la_mmcm = XilinxMMCMDRP(self.la_drp)
            self.ADS4128 = ADS4128Settings(self.sc)
            self.clock = ChipWhispererHuskyClock.ChipWhispererHuskyClock(self.sc, \
                self._fpga_clk, self.glitch_mmcm1, self.glitch_mmcm2, self.ADS4128)
            self.XADC = XADCSettings(self.sc)
            self.LEDs = LEDSettings(self.sc)
            self.LA = LASettings(oaiface=self.sc, mmcm=self.la_mmcm, scope=self)
            if TraceWhisperer:
                try:
                    trace_reg_select = self.sc._address_str2int('TW_TRACE_REG_SELECT')
                    main_reg_select = self.sc._address_str2int('TW_MAIN_REG_SELECT')
                    self.trace = TraceWhisperer(husky=True, target=None, scope=self, trace_reg_select=trace_reg_select, main_reg_select=main_reg_select)
                    self.UARTTrigger = UARTTrigger(scope=self, trace_reg_select=3, main_reg_select=2)
                except Exception as e:
                    scope_logger.info("TraceWhisperer unavailable " + str(e))
            self.userio = USERIOSettings(self.sc, self.trace)
            self.SAD = ChipWhispererSAD.HuskySAD(self.sc)
            self.errors = HuskyErrors(self.sc, self.XADC, self.adc, self.clock, self.trace)
            self._is_husky = True
            self.adc._is_husky = True
            self.gain._is_husky = True
            self._fpga_clk._is_husky = True
            self.sc._is_husky = True
            self.adc.bits_per_sample = 12
            if cwtype == "cwhusky-plus":
                self._is_husky_plus = True
                self.LA._is_husky_plus = True
        else:
            self.clock = ClockSettings(self.sc, hwinfo=self.hwinfo)
            self.errors = ChipWhispererSAMErrors(self._getNAEUSB())

        if cwtype == "cw1200":
            self.adc._is_pro = True
        if cwtype == "cwlite":
            self.adc._is_lite = True
        if self.advancedSettings:
            self.io = self.advancedSettings.cwEXTRA.gpiomux
            self.trigger = self.advancedSettings.cwEXTRA.triggermux
            self.glitch = self.advancedSettings.glitch.glitchSettings
            if cwtype in ['cwhusky', 'cwhusky-plus']:
                # TODO: cleaner way to do this?
                self.glitch.pll = self.clock.pll
                self.clock.pll._glitch = self.glitch
                self.advancedSettings.glitch.pll = self.clock.pll
                self.trigger = self.advancedSettings.cwEXTRA.huskytrigger
            if cwtype == "cw1200":
                self.trigger = self.advancedSettings.cwEXTRA.protrigger

        if cwtype in ["cwhusky", "cwhusky-plus"]:
            # these are the power-up defaults, but just in case e.g. test script left these on:
            self.adc.test_mode = False
            self.ADS4128.mode = 'normal'
            self.glitch.enabled = False
            self.LA.enabled = False

        self._get_usart().init() # init serial port on connection

        module_list = [x for x in self.__dict__ if isinstance(self.__dict__[x], util.DisableNewAttr)]
        self.add_read_only(module_list)
        self.disable_newattr()
        self._is_connected = True
        self.connectStatus = True

        return True

    def dis(self):
        """Disconnects the current scope object.

        Returns:
            True if the disconnection was successful, False otherwise.
        """
        self._read_only_attrs = [] # disable read only stuff
        if self.scopetype is not None:
            self.scopetype.dis()
            if self.advancedSettings is not None:
                self.advancedSettings = None
                util.chipwhisperer_extra = None

            if self.advancedSAD is not None:
                self.advancedSAD = None

            if self.digitalPattern is not None:
                self.digitalPattern = None

        if hasattr(self.scopetype, "ser") and hasattr(self.scopetype.ser, "_usbdev"):
            self.sc.usbcon = None

        self.enable_newattr()
        self._is_connected = False
        self.connectStatus = False
        
        # Mock
        self.current_mock_targets = []
        return True


    def adc_test(self, samples=131070, reps=3, verbose=False):
        return "pass"
