import sys
import binascii

import time 
import logging
import os
from collections import namedtuple
from chipwhisperer.capture.targets import TargetTypes, SimpleSerial, SimpleSerial2
import numpy as np
import chipwhisperer as cw
from tqdm import trange
from NormalSerial import NormalSerial
from mocks.mock_scope import MockOpenADC
from NormalSerial import NormalSerial
from TestSetup import TestSetupTemplate, TestResult, TestOptions
from chipwhisperer.common.utils.util import CWByteArray
from chipwhisperer.capture.targets import TargetTypes, SimpleSerial, SimpleSerial2
from typing import Optional
from glitch_params import GlitchControllerParams
from nuvoprogpy.nuvo51icpy import Nuvo51ICP, ConfigFlags
import subprocess


SCOPETYPE = 'OPENADC'
PLATFORM = 'CW308_STM32F3'
SS_VER = 'SS_VER_2_1'


NORMAL_I_VAL = 50
NORMAL_J_VAL = 50
NORMAL_CNT_VAL = NORMAL_I_VAL * NORMAL_J_VAL
BYTES_READ = 4
class NuvoSerialTest(TestSetupTemplate):
	def __init__(self, _scope: cw.scopes.OpenADC, target: SimpleSerial2, glitch_controller_params, options: TestOptions = None):
		super().__init__(_scope, target, glitch_controller_params, options)
		self._printed_success_warning = False

	def parse_values(self, data: list) -> int:
		return data[0] + (data[1] << 8) + (data[2] << 16) + (data[3] << 24)
	
	def prep_run(self) -> bool:
			time.sleep(0.25)
			self.target.flush()

			if not self.iter_run():
				raise Exception("Failed to write to serial, please check your connections.")
			else:
				data: list = self.get_data()
				result = self.check_result(data)
				if result != TestResult.normal:
					# parse the data into a hex string
					data_len = str(len(data)) if not (data is None) else "None"
					data_str = " ".join("{:02x}".format(x) for x in data) if not (data is None) else "None"
					print("got back (len= "+ data_len +"): " + data_str)
					raise Exception("Device did not respond as expected. Please check your setup.")
			return True
	def after_run(self) -> None:
			pass
	def iter_run(self) -> bool:
			if self.logger_level <= TestOptions.LOG_TRACE:
					start_time = time.time()
			self.target.simpleserial_write('g', bytearray([]))
			if self.logger_level <= TestOptions.LOG_TRACE:
					end_time = time.time()
					self.logger.debug("Write time: %f" % (end_time - start_time))
			return True
	def get_data(self) -> Optional[CWByteArray]:
		if self.logger_level <= TestOptions.LOG_TRACE:
			start_time = time.time()
		read = self.target.simpleserial_read('r', BYTES_READ)
		if self.logger_level <= TestOptions.LOG_TRACE:
			end_time = time.time()
			self.logger.debug("read time: %f" % (end_time - start_time))
		return read
	def check_result(self, data: CWByteArray) -> TestResult:
			if not data or len(data) != BYTES_READ:
					if not data:
						self.logger.debug("Data is none")
					else:
						self.logger.debug("Data length is not 4: %d" % len(data))
					return TestResult.reset
			gcnt_val = self.parse_values(data)
			success_cond = (int(gcnt_val) != NORMAL_CNT_VAL)
			if success_cond:
				if not self._printed_success_warning:
					self.logger.warning("SUCCESS: On Success, device will return an error 0x10. This is expected behavior.")
					self._printed_success_warning = True
				self.logger.info("SUCCESS: Count value: %d" % gcnt_val)
				return TestResult.success
			return TestResult.success if success_cond else TestResult.normal


scope: cw.scopes.OpenADC = None
target: SimpleSerial2 = None
prog: cw.programmers.Programmer = None
mock: bool = False

def target_setup(target):
	if scope._is_husky is False:
		if PLATFORM == "CWLITEXMEGA":
			scope.clock.clkgen_freq = 32E6
			if SS_VER=='SS_VER_2_1':
				target.baud = 230400*32/7.37
			else:
				target.baud = 38400*32/7.37
		elif (PLATFORM == "CWLITEARM") or ("F3" in PLATFORM):
			scope.clock.clkgen_freq = 24E6
			if SS_VER=='SS_VER_2_1':
				target.baud = 230400*24/7.37
			else:
				target.baud = 38400*24/7.37
			time.sleep(0.1)



def mock_reconnect():
	global scope
	global target
	global prog
	scope = MockOpenADC()
	scope.con()
	target = cw.target(scope, cw.targets.SimpleSerial2)
	prog = None

def really_reconnect():
	global scope
	global target
	global prog
	try:
		if scope and not scope.connectStatus:
			scope.con()
	except NameError:
		scope = cw.scope()

	target_type = cw.targets.SimpleSerial2

	try:
		target = cw.target(scope, target_type)
	except:
		print("INFO: Caught exception on reconnecting to target - attempting to reconnect to scope first.")
		print("INFO: This is a work-around when USB has died without Python knowing. Ignore errors above this line.")
		scope = cw.scope()
		target = cw.target(scope, target_type)
	print("INFO: Found ChipWhisperer😍")
	prog = None
	if "STM" in PLATFORM or PLATFORM == "CWLITEARM" or PLATFORM == "CWNANO":
		prog = cw.programmers.STM32FProgrammer
	elif PLATFORM == "CW303" or PLATFORM == "CWLITEXMEGA":
		prog = cw.programmers.XMEGAProgrammer
	elif "neorv32" in PLATFORM.lower():
		prog = cw.programmers.NEORV32Programmer
	elif PLATFORM == "CW308_SAM4S" or PLATFORM == "CWHUSKY":
		prog = cw.programmers.SAM4SProgrammer
	else:
		prog = None
  

def reconnect(type = SimpleSerial2):
	global scope
	global target
	global mock
	try:
		scope.dis()
		target.dis()
	except:
		pass
	if mock:
		mock_reconnect()
		return
	really_reconnect()
	scope.default_setup(False)
	time.sleep(1)
	target_setup(target)

def reset_target(scope):
	if PLATFORM == "CW303" or PLATFORM == "CWLITEXMEGA":
		scope.io.pdic = 'low'
		time.sleep(0.1)
		scope.io.pdic = 'high_z' #XMEGA doesn't like pdic driven high
		time.sleep(0.1) #xmega needs more startup time
	elif "neorv32" in PLATFORM.lower():
		raise IOError("Default iCE40 neorv32 build does not have external reset - reprogram device to reset")
	elif PLATFORM == "CW308_SAM4S" or PLATFORM == "CWHUSKY":
		scope.io.nrst = 'low'
		time.sleep(0.25)
		scope.io.nrst = 'high_z'
		time.sleep(0.25)
	else:  
		scope.io.nrst = 'low'
		time.sleep(0.05)
		scope.io.nrst = 'high_z'
		time.sleep(0.05)

def reboot_flush():
	reset_target(scope)
	target.flush()

def flash_target(fw_path):
	fw_dir = os.path.dirname(fw_path)
	args = ["make", "PLATFORM={}".format(PLATFORM), "CRYPTO_TARGET=NONE", "SS_VER={}".format(SS_VER), "-j"]
	subprocess.check_output(args, 
						cwd=fw_dir)
	fw_path = os.path.join(fw_dir, "simpleserial-glitch-{}.hex".format(PLATFORM))
	cw.program_target(scope, prog, fw_path)
	if SS_VER=="SS_VER_2_1":
		target.reset_comms()


def glitch_run(name, params, tries_per_setting, rom_file: str = "", options: TestOptions = None, dry_run = False):
	reconnect()
	print(scope)
	time.sleep(1)
	scope.glitch.output = "glitch_only" # glitch_out = clk ^ glitch
	scope.glitch.trigger_src = "ext_single" # glitch only after scope.arm() called
	scope.glitch.clk_src = "clkgen" # glitch clk source

	# params = GlitchControllerParams(36.0, [0.4, 6.8, 0.4], [54,70,1], 11)
	test = NuvoSerialTest(scope, target, params, options)
	print(test.name)
	test.tries_per_setting = tries_per_setting
	test._debug = False
	if mock:
		print("**** MOCK TEST ****")
		print("Skipping flashing....")
		name = "mock_" + name
		scope.reset_rate = 0.0
		scope.success_rate = 1
		print("Reset rate: %f" % scope.reset_rate)
		print("Success rate: %f" % scope.success_rate)
	elif rom_file == "":
		print("Skipping ROM flashing...")
		reboot_flush()
	else:
		print("flashing ROM: %s" % rom_file)
		flash_target(rom_file)
		reboot_flush()
		if test.prep_run():
			print("Device responded as expected, ready to test!")

	test.run_sequence(name, dry_run)
	return test.gc


mock = False
CWLITEXMEGA_WAIT = 0.1
CWLITEXMEGA_RESET_PIN = "pdic"
OTHER_WAIT = 0.05

options = TestOptions()
options.small_break_seconds = 1
options.big_break_seconds = 5
options.iter_before_small_break = 1000
options.iter_before_big_break = 10000
options.max_total_resets = 10000000
options.should_break_on_success = False
options.max_consec_resets_per_bad_setting = 0
options.target_reset_io = "nrst" if PLATFORM != "CWLITEXMEGA" else CWLITEXMEGA_RESET_PIN
options.target_reset_wait = OTHER_WAIT if PLATFORM != "CWLITEXMEGA" else CWLITEXMEGA_WAIT
params = GlitchControllerParams()

if PLATFORM=="CWLITEXMEGA":
	params.width_range = [43.5, 47.8, 0.4]
	params.offset_range = [-48, -10, 0.4]
	params.ext_offset_range = [7, 10, 1]
	params.repeat_range = 11
elif PLATFORM == "CWLITEARM":
	#should also work for the bootloader memory dump
	params.width_range = [34, 36, 0.4]
	params.offset_range = [-40, 10, 0.4]
	params.ext_offset_range = [6, 7, 1]
	params.repeat_range = 7
elif PLATFORM == "CW308_STM32F3":
    # successful result found:  - width: 49.60, offset: -36.40, ext_offset: 9, repeat: 9
	# width: 49.60, offset: -40.00, ext_offset: 9, repeat: 9.........[SUCCESS]     
	# width: 49.60, offset: -37.20, ext_offset: 10, repeat: 9.........[RESET]    
	#  - width: 49.60, offset: -21.80, ext_offset: 6, repeat: 7
	#  - width: 49.60, offset: -21.80, ext_offset: 6, repeat: 7
	#  - width: 49.60, offset: -21.80, ext_offset: 6, repeat: 7
	#  - width: 49.60, offset: -21.80, ext_offset: 6, repeat: 7
	#  - width: 49.60, offset: -21.80, ext_offset: 6, repeat: 7
	#  - width: 49.60, offset: -21.80, ext_offset: 6, repeat: 7
	params.width_range = [47.6, 49.6, 0.4]
	params.offset_range = [-40.0, 10, 0.4]
	params.ext_offset_range = [6, 13, 1]
	params.repeat_range = [7, 9, 1]

	params.width_range = 49.6
	params.offset_range = [-40, 10, 0.4]
	params.ext_offset_range = [6, 13, 1]
	params.repeat_range = [7, 9, 1]
	# params.width_range = [47.6, 49.6, 0.4]
	# params.offset_range = [-19, -21.8, 0.4]
	# params.ext_offset_range = [9, 12, 1]
	# params.repeat_range = 5

mock = True

test_name = "stm32f-glitch-loop-dialing-in"
FW_DIR = "/home/nikita/chipwhisperer/hardware/victims/firmware/simpleserial-glitch"
fw_path = os.path.join(FW_DIR, "simpleserial-glitch-{}.hex".format(PLATFORM))
gc = glitch_run(test_name,
                params,
				1,
				fw_path,
				options,
    			dry_run=False)
# gc.display_stats()