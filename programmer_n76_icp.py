import logging
import subprocess
from chipwhisperer.common.utils import util
from chipwhisperer.capture.scopes import ScopeTypes
from chipwhisperer.capture.scopes import CWNano
from chipwhisperer.capture.api.programmers import save_and_restore_pins, Programmer
from chipwhisperer.capture.api.cwcommon import ChipWhispererCommonInterface
from chipwhisperer.hardware.naeusb.programmer_avr import supported_avr
from chipwhisperer.hardware.naeusb.programmer_xmega import supported_xmega
from chipwhisperer.hardware.naeusb.programmer_stm32fserial import supported_stm32f
from chipwhisperer.hardware.naeusb.programmer_neorv32 import Neorv32Programmer
from chipwhisperer.capture.utils.IntelHex import IntelHex
from chipwhisperer.logging import *
from nuvoprogpy.nuvo51icpy.nuvo51icpy import Nuvo51ICP, ConfigFlags, N76E003_DEVID
from pyparsing import C

# Disables brown-out detector
NO_BROWNOUT_CONFIG = [0xFF, 0xFF, 0x73, 0xFF, 0xFF]
class N76ICPProgrammer(Programmer):
	def __init__(self, config = ConfigFlags(NO_BROWNOUT_CONFIG)):
		self.logfunc = target_logger.info
		self._erased = False
		self.config = config

	def open(self):
		pass

	def save_pin_setup(self):
		self.pin_setup['pdic'] = self.scope.io.pdic
		self.pin_setup['pdid'] = self.scope.io.pdid
		self.pin_setup['nrst'] = self.scope.io.nrst
		self.set_pins()

	def restore_pin_setup(self):
		self.scope.io.pdic = self.pin_setup['pdic']
		self.scope.io.pdid = self.pin_setup['pdid']
		self.scope.io.nrst = self.pin_setup['nrst']

	def set_pins(self):
		""" 
		We don't use the scope's pins, we use the Raspberry Pi's pins.
		Just turn them off here so they don't interfere.
		"""
		self.scope.io.pdic = None
		self.scope.io.pdid = None
		self.scope.io.nrst = None

	def setUSBInterface(self, iface):
		raise DeprecationWarning('find method now includes what setUSBInterface did')
	@save_and_restore_pins
	def find(self):
		with Nuvo51ICP() as nuvo:
			dev_info = nuvo.get_device_info()
			if dev_info.device_id != N76E003_DEVID:
				raise IOError("Device not found: {}".format(str(nuvo.get_device_info())))
			self.logfunc("Found N76E003:")
			self.logfunc(nuvo.get_device_info())
	
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
		with Nuvo51ICP() as nuvo:
			should_erase = not self.erased
			self.erased = False
			programmed = nuvo.program_aprom(file_data, config=self.config, verify=verify, erase=should_erase)
			programmed = programmed and nuvo.write_config(self.config, _skip_erase = (not should_erase))
		if not programmed:
			raise Exception("Failed to flash image. Please check your setup.")


	@save_and_restore_pins
	def erase(self):
		with Nuvo51ICP() as nuvo:
			self.erased = nuvo.mass_erase()
		if not self.erased:
			raise IOError("Failed to erase device")

	def close(self):
		pass

	def log(self, text):
		"""Logs the text and broadcasts it"""
		target_logger.info(text)
		self.newTextLog.emit(text)

	def autoProgram(self, hexfile, erase=True, verify=True, logfunc=print, waitfunc=None):
		self.logfunc = logfunc
		self.program(self, hexfile, verify=verify)

	@save_and_restore_pins
	def readConfig(self) -> ConfigFlags:
		with Nuvo51ICP() as nuvo:
			return nuvo.read_config()

	@save_and_restore_pins
	def writeConfig(self, config: ConfigFlags):
		with Nuvo51ICP() as nuvo:
			nuvo.write_config(config)
	
COMPILED_CLK_FREQ  = 16000000
ACTUAL_CLKGEN_FREQ = 16000000
USE_EXTERNAL_CLOCK = 1
SS_VER = "SS_VER_2_1"
PLATFORM = "CW308_N76E003"
CRYPTO_TARGET = "NONE"

def make_image(fw_dir:str):
	print(subprocess.check_output(["make", "clean"], 
					cwd=fw_dir).decode("utf-8"))	
	args = [
			"make",
			"PLATFORM={}".format(PLATFORM),
			"USE_EXTERNAL_CLOCK={}".format(USE_EXTERNAL_CLOCK), 
			"CRYPTO_TARGET={}".format(CRYPTO_TARGET), 
			"SS_VER={}".format(SS_VER), 
			"F_CPU={}".format(COMPILED_CLK_FREQ), 
			"-j"]
	print(subprocess.check_output(args, cwd=fw_dir).decode("utf-8"))
	fw_path = os.path.join(fw_dir, "simpleserial-glitch-{}.hex".format(PLATFORM))
	return fw_path
# get path of this file
if __name__ == "__main__":
	from mocks.mock_scope import MockOpenADC
	cur_path = os.path.dirname(os.path.realpath(__file__))
	fw_dir = os.path.join(cur_path, "NuMicro8051_firmware/simpleserial-glitch")
	make_image(fw_dir)
	fw_path = os.path.join(fw_dir, "simpleserial-glitch-{}.hex".format(PLATFORM))
	p = N76ICPProgrammer()
	p.scope = MockOpenADC()
	p.scope.con()
	p.find()
	p.erase()
	p.program(fw_path)