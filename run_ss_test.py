import json
import math
import platform
import subprocess
import sys
import binascii

import time 
import logging
import os
from collections import namedtuple
from typing import Optional
from chipwhisperer.capture.targets import TargetTypes, SimpleSerial, SimpleSerial2
from chipwhisperer.capture.api.programmers import Programmer
from matplotlib import rc
import numpy as np
import chipwhisperer as cw
from tqdm import trange
from NormalSerial import NormalSerial
from mocks.mock_scope import MockOpenADC
from ss_glitch_loop_test import SSGlitchLoopTest, SSVersionTest
from TestSetup import TestOptions, TestSetupTemplate
from programmer_n76_icp import N76ICPProgrammer

# Default is 16mhz, max for both compiled and max is 16.6mhz; it's not stable at higher frequencies
# Compiled clock rate = what the firmware uses when calculating the baud rates
COMPILED_CLK_FREQ  = 7372800
# What we use for the clkgen
ACTUAL_CLKGEN_FREQ = 16000000
# ACTUAL_CLKGEN_FREQ = 24000000
# Baud rate for the firmware
COMPILED_BAUD_RATE = 115200
 # The scope adc doesn't lock when using ext_clock due to the N76E003's internal oscillator having high variance, so it's recommended set this to 1 to have the N76E003 use CLKIN as the clock source
USE_EXTERNAL_CLOCK = 1
# SS_VER_1_x is only supported when using no crypto targets; not enough memory.
SS_VER = "SS_VER_2_1"
PLATFORM = "CW308_N76E003"
# PLATFORM = "CW308_MS5132K_AT20"
# Only crypto target supported is TINYAES128C
CRYPTO_TARGET = "NONE"
# Build and then flash the scope firmware (so that we get the NuMicro8051 programming support)
UPGRADE_SCOPE_FW = True

# dry_run: Building and flashing the firmware, using a real scope and target, setting the all settings,
# but not turning on glitching
DRY_RUN = True
# mock: using the mock scope in `mocks`; simulated scope, simulated target
MOCK = False


def set_gpio(scope: cw.scopes.OpenADC):
	scope.io.nrst = None
	scope.io.pdic = None
	scope.io.pdid = None
	scope.io.tio3 = None

	scope.io.hs2 = "clkgen"
	scope.io.tio1 = "serial_rx"
	scope.io.tio2 = "serial_tx"
	scope.io.tio4 = None

def fb_setup(scope: cw.scopes.OpenADC):
	# scope.gain.gain = 30
	# scope.gain.mode = "high"
	# scope.gain.db = 24.8359375
	# Initial Setup 
	set_gpio(scope)
	scope.trigger.triggers = "tio4"
	# scope.clock.clkgen_div = 52
	# scope.clock.clkgen_mul = 9
	scope.adc.basic_mode = "rising_edge"
	scope.adc.samples = 24000
	scope.adc.offset = 0
	scope.clock.adc_src = "clkgen_x4"
	# scope.glitch.arm_timing = "no_glitch"
	scope.glitch.trigger_src = "ext_single"
	scope.glitch.clk_src = "clkgen"
	scope.glitch.output = "glitch_only"

# at 16mhz, the baud rate tends to have a high error rate due to 16mhz not being a good factor for baud rates
# e.g. 115200 baud rate is actually 111111 baud rate at 16mhz
# we need to calculate what the actual baud rate is with the compiled clock frequency
def calc_UART0_timer3_actual_baud_rate(compiled_fsys):
    SMOD = 1
    TH3_PRESCALE = 1
	# RH, RL values for the serial timer
    RH_RL = (65536 - round(math.floor(compiled_fsys/16)/COMPILED_BAUD_RATE))
    timer3_actual_baud_rate = 2**SMOD/32 * compiled_fsys/(TH3_PRESCALE*(65536-RH_RL))
    return timer3_actual_baud_rate

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
		elif PLATFORM == "CW308_N76E003" or PLATFORM == "CW308_MS5116K_AT20" or PLATFORM == "CW308_MS5132K_AT20" or PLATFORM == "CW308_N76S003":
			# TODO: remove this in final version
			# earlier versions of the boards (pre 1.2) had these swapped, and that is what I'm currently testing with
			# set `_using_earlier_board` to `False` if you are using the latest version of the board
			_using_earlier_board = os.environ.get("USING_EARLIER_BOARD", False)
			if _using_earlier_board:
				print("USING EARLIER BOARD WITH SWAPPED TX AND RX!!!")
				scope.io.tio1 = "serial_tx"
				scope.io.tio2 = "serial_rx"
			else:
				print("SERIAL LINES: scope.io.tio1 = serial_rx, scope.io.tio2 = serial_tx")
				scope.io.tio1 = "serial_rx"
				scope.io.tio2 = "serial_tx"
			scope.clock.clkgen_freq = ACTUAL_CLKGEN_FREQ
			calced_baud_rate = calc_UART0_timer3_actual_baud_rate(COMPILED_CLK_FREQ)
			print("calculated baud rate with compiled clock {}: {}".format(COMPILED_CLK_FREQ, calced_baud_rate))
			target_baud_rate = calced_baud_rate * ACTUAL_CLKGEN_FREQ / COMPILED_CLK_FREQ
			print("Target baud rate: {}".format(round(target_baud_rate)))
			if target_baud_rate > 250000:
				raise ValueError("Target baud rate is too high for platform (compiled baud rate: {}, target baud rate: {})".format(PLATFORM, COMPILED_BAUD_RATE, target_baud_rate))
			target.baud = round(target_baud_rate)
			if not USE_EXTERNAL_CLOCK:
				scope.clock.adc_src = "extclk_x4"
				# scope.clock.clkgen_src = "extclk"
				# scope.clock.clkgen_div = 2
				scope.io.hs2 = "disabled"
				scope.glitch.clk_src = "target"
				scope.clock.extclk_freq = COMPILED_CLK_FREQ
				print("*** Using external clock, disabling HS2 ***")
				print("Clock: ", scope.clock)
		else:
			target.baud = 115200

def get_programmer_type():
	if "STM" in PLATFORM or PLATFORM == "CWLITEARM" or PLATFORM == "CWNANO":
		return cw.programmers.STM32FProgrammer
	elif PLATFORM == "CW303" or PLATFORM == "CWLITEXMEGA":
		return cw.programmers.XMEGAProgrammer
	elif "neorv32" in PLATFORM.lower():
		return cw.programmers.NEORV32Programmer
	elif PLATFORM == "CW308_SAM4S" or PLATFORM == "CWHUSKY":
		return cw.programmers.SAM4SProgrammer
	elif PLATFORM == "CW308_N76E003" or PLATFORM == "CW308_MS5116K_AT20" or PLATFORM == "CW308_MS5132K_AT20" or PLATFORM == "CW308_N76S003":
		return N76ICPProgrammer
	else:
		return None
	
def get_base_fw_dir():
	# find the directory where the chipwhisperer python module is located
	# this is used to find the firmware directory
	cw_dir = os.path.dirname(cw.__file__)
	# ../../hardware/victims/firmware/
	cw_dir = os.path.normpath(os.path.join(cw_dir, "..", "..", "hardware", "victims", "firmware"))
	if PLATFORM == "CW308_N76E003" or PLATFORM == "CW308_MS5116K_AT20" or PLATFORM == "CW308_MS5132K_AT20" or PLATFORM == "CW308_N76S003":
		return os.path.join(cw_dir, "numicro8051")
	return cw_dir


def get_base_scope_fw_dir():
	# find the directory where the chipwhisperer python module is located
	# this is used to find the firmware directory
	cw_dir = os.path.dirname(cw.__file__)
	cw_dir = os.path.normpath(os.path.join(cw_dir, "..", "..", "hardware", "capture", "chipwhisperer-lite", "sam3u_fw", "SAM3U_VendorExample", "src"))
	return cw_dir


def upgrade_scope_firmware():
	global scope
	scope_fw_dir = get_base_scope_fw_dir()
	# check if the naeusb directory exists
	if not os.path.exists(scope_fw_dir):
		raise IOError("Firmware directory not found: {}".format(scope_fw_dir))
	if not os.path.exists(os.path.join(scope_fw_dir, "naeusb")):
		raise IOError("naeusb directory not found in firmware directory (Did you initialize submodules?): {}".format(scope_fw_dir))
	if not os.path.exists(os.path.join(scope_fw_dir, "naeusb", "n51_icp.c")):
		raise IOError("Firmware is not the correct version (are you on the correct chipwhisperer branch?): {}".format(scope_fw_dir))
	make_image(scope_fw_dir)
	scope_fw_bin = os.path.join(scope_fw_dir, "ChipWhisperer-Lite.bin")
	try:
		scope.dis()
		scope = None
	except:
		pass
	finally:
		scope = cw.scope(force= True)
	if scope and scope.connectStatus and scope._getCWType() != "cwlite":
		raise IOError("Only ChipWhisperer Lite is supported right now!")
	scope.upgrade_firmware(scope_fw_bin)
	scope.dis()
	scope = None
	time.sleep(1)


scope: cw.scopes.OpenADC = None
target: SimpleSerial = None
prog: type[Programmer] = None

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
	if UPGRADE_SCOPE_FW:
		upgrade_scope_firmware()
	try:
		if scope and not scope.connectStatus:
			scope.con()
	except NameError:
		scope = cw.scope()
	if SS_VER.startswith("SS_VER_1_"):
		target_type = cw.targets.SimpleSerial
	else:
		target_type = cw.targets.SimpleSerial2

	try:
		target = cw.target(scope, target_type)
	except:
		print("INFO: Caught exception on reconnecting to target - attempting to reconnect to scope first.")
		print("INFO: This is a work-around when USB has died without Python knowing. Ignore errors above this line.")
		scope = cw.scope()
		target = cw.target(scope, target_type)
	print("INFO: Found ChipWhisperer😍")
	prog = get_programmer_type()

def reconnect(run_setup = True):
	global scope
	global target
	try:
		scope.dis()
		target.dis()
	except:
		pass
	if MOCK:
		mock_reconnect()
	else:
		really_reconnect()
	if run_setup:
		scope.default_setup(False)
		time.sleep(1)
		fb_setup(scope)
		target_setup(target)
	else:
		time.sleep(1)
# if "VSCODE_CWD" in os.environ or "VSCODE_PID" in os.environ:
# 	os.environ["PANEL_COMMS"] = "vscode"


from glitch_params import GlitchControllerParams
from nuvoprogpy.nuvo51icpy import Nuvo51ICP, ConfigFlags

def device_reset():
	scope.io.nrst = 'low'
	time.sleep(0.05)
	scope.io.nrst = None
	time.sleep(0.05)

def reboot_flush():
	target.flush()
	device_reset()
	target.flush()

def test_locking_clock_freq(scope: cw.scopes.OpenADC):
	for j in range(-1, 2):
		if j == 0:
			continue
		for i in range(0, 20):
			scope.clock.clkgen_freq = ACTUAL_CLKGEN_FREQ + (i * 4000 * j)
			time.sleep(1)
			print("Testing clock frequency %.2f, div %d, mul %d...." % (scope.clock.clkgen_freq, scope.clock.clkgen_div, scope.clock.clkgen_mul))
			if scope.clock.adc_locked:
				print("LOCKED")
			else:
				print("not locked")

MAKE_COMMAND = "make" if platform.system() != "Darwin" else "gmake"

def make_image(fw_dir:str, target_name:str = ""):
	# get the last part of fw_dir
	fw_base = target_name if target_name else os.path.basename(fw_dir)
	print(subprocess.check_output([MAKE_COMMAND, "clean"], 
					cwd=fw_dir).decode("utf-8"))	
	use_external_clock = 1 if USE_EXTERNAL_CLOCK else 0
	args = [
            MAKE_COMMAND,
            "PLATFORM={}".format(PLATFORM),
            "USE_EXTERNAL_CLOCK={}".format(use_external_clock), 
			"EXT_CLK={}".format(ACTUAL_CLKGEN_FREQ),
            "CRYPTO_TARGET={}".format(CRYPTO_TARGET), 
            "SS_VER={}".format(SS_VER), 
            "F_CPU={}".format(COMPILED_CLK_FREQ), 
			"BAUD_RATE={}".format(COMPILED_BAUD_RATE),
            "-j"
            ]
	print(subprocess.check_output(args, cwd=fw_dir).decode("utf-8"))
	fw_path = os.path.join(fw_dir, "{}-{}.hex".format(fw_base, PLATFORM))
	return fw_path

def capture_run(fw_dir: str = "", name = "", options: TestOptions = None):
	"""
	Capturing traces, no glitching
	"""
	reconnect()
	time.sleep(1)
	params = GlitchControllerParams()
	test = SSGlitchLoopTest(scope, target, prog, params, options)

	if MOCK:
		print("**** MOCK TEST ****")
		print("Skipping flashing....")
		name = "mock_" + name
		scope.reset_rate = 1.0
		print("Reset rate: %f" % scope.reset_rate)
	if fw_dir == "":
		print("Skipping ROM flashing...")
	else:
		print("*** Building ROM: %s" % fw_dir)
		test.fw_image_path = make_image(fw_dir)

	data = test.capture_sequence(500, name)
	mean_data = np.mean(data, axis = 0)
	return data, mean_data

def glitch_run(name, 
			   test_type: type[TestSetupTemplate], 
			   width_range,
			   offset_range,
			   ext_offset_range,
			   repeat_range,
			   tries_per_setting, 
			   param_order, 
			   fw_dir: str = "", 
			   options: TestOptions = None, 
			   target_name:str = ""):
	reconnect()
	time.sleep(1)
	params = GlitchControllerParams(width_range, offset_range, ext_offset_range, repeat_range, param_order=param_order)
	test = test_type(scope, target, prog, params, options)
	print(test.name)
	test.tries_per_setting = tries_per_setting
	# mock: using the mock scope in `mocks`; simulated scope, simulated target
	if not USE_EXTERNAL_CLOCK:
		print ("*** Using internal clock, disabling HS2 ***")
		test.hs2_output = "disabled"
	if MOCK:
		print("**** MOCK TEST ****")
		print("Skipping flashing....")
		name = "mock_" + name
		scope.reset_rate = 0.4
		test.no_save = True
		print("Reset rate: %f" % scope.reset_rate)
	elif fw_dir == "" or not prog:
		print("Skipping ROM flashing...")
		test.reboot_flush()
	else:
		print("*** Building ROM: %s" % fw_dir)
		test.fw_image_path = make_image(fw_dir, target_name)
	# dry_run: Building and flashing the firmware, using a real scope and target, setting the all settings,
	# but not turning on glitching
	if DRY_RUN:
		test.no_save = True
		print("Dry run, not saving results.")
	test.run_sequence(name, DRY_RUN)
	if DRY_RUN:
		print("*** END OF DRY RUN, NO GLITCHES WERE PERFORMED")
	if MOCK:
		print("**** END MOCK TEST ****")
	return test.gc


# NOTES:
# width = repeat viable
#35.2 = 41 - 50
#35.6 = 28 - 32
#36 = 22 - 28
#36.4 = 18 - 22
#36.8 = 14 - 17
#37.2 = 11 - 14
#37.6 = 9 - 11
#38 = 7 - 9
#38.4 = 4 - 5
#38.8 = 4 - 5
#39.2 = 4
#39.6 = 4
# widths larger than this aren't viable

# the following look interesting:
# offset_range: [1.0, 10.0, 0.4]
# offset_range = [24.4, 30.8, 0.4]

def run_ss_glitch_loop_test():
	global CRYPTO_TARGET
	CRYPTO_TARGET = "NONE"
	fw_dir = ""
	fw_dir = os.path.join(get_base_fw_dir(), "simpleserial-glitch")
	target_name = "simpleserial-glitch"
	# rom_image_path = ""
	options = TestOptions()
	options.max_total_dry_run_resets = 10000
	options.small_break_seconds = 1
	options.iter_before_small_break = 1000
	options.max_consec_resets_per_bad_setting = 100
	test_name = "testwststs"
	width_range = 37.6
	offset_range = [2.0, 8.1, 0.4]
	ext_offset_range = [4, 25, 1]
	repeat_range = 9
	param_order=["width", "repeat", "offset", "ext_offset"]
	tries_per_setting = 200
	gc = glitch_run(test_name,
				 	SSGlitchLoopTest,
					width_range,
					offset_range,
					ext_offset_range,
					repeat_range,
					tries_per_setting,
					param_order,
					fw_dir,
					options,
					target_name = target_name)
	return gc

def run_ss_version_test(fw_name = "simpleserial-aes-bootloader", target_name = "simpleserial-bootloader"):
	global CRYPTO_TARGET
	CRYPTO_TARGET = "TINYAES128C"
	fw_dir = ""
	fw_dir = os.path.join(get_base_fw_dir(), fw_name)
	target_name = target_name
	make_image(fw_dir, target_name)
	options = TestOptions()
	options.small_break_seconds = 1
	options.iter_before_small_break = 1000
	options.max_consec_resets_per_bad_setting = 100
	test_name = "test_version"
	width_range = 37.6
	offset_range = [2.0, 8.1, 0.4]
	ext_offset_range = [4, 25, 1]
	repeat_range = 9
	param_order=["width", "repeat", "offset", "ext_offset"]
	tries_per_setting = 200
	gc = glitch_run(test_name,
				 	SSVersionTest,
					width_range,
					offset_range, 
					ext_offset_range,
					repeat_range, 
					tries_per_setting,
					param_order,
					fw_dir,
					options,
					target_name = target_name)
	return gc


def get_scope_status(scope):
	stat_str = ""
	for top_level in ["io", "trigger", "glitch", "adc", "clock"]:
		iter = 0
		stat_str+=("*** scope.{}:\n".format(top_level))
		items = getattr(scope, top_level)._dict_repr().items()
		for key, value in items:
			iter += 1
			# convert any bytearray values to a hex string
			if isinstance(value, bytearray):
				value = "[" + " ".join("{:02x}".format(x)
										for x in value) + "]"

			stat_str+=("- %-15s %-20s" % (key + ":", str(value)))
			if iter % 3 == 0:
				stat_str+=("\n")
		if iter % 3 != 0:
			stat_str+="\n"
		stat_str+="\n"
	return stat_str

PAGE_ERASE_AP       = 0x22 # 00:1:0:0010, Page erase APROM
BYTE_READ_AP        = 0x00 # 00:0:0:0000, Byte read APROM
BYTE_PROGRAM_AP     = 0x21 # 00:1:0:0001, Program APROM
BYTE_READ_ID        = 0x0C # 00:0:0:1100, Device ID
PAGE_ERASE_CONFIG   = 0xE2 # 11:1:0:0010, Erase Config
BYTE_READ_CONFIG    = 0xC0 # 11:0:0:0000, Read Config
BYTE_PROGRAM_CONFIG = 0xE1 # 11:1:0:0001, Program Config
READ_UID            = 0x04 # 00:0:0:0100, Unique ID
PAGE_ERASE_LD       = 0x62 # 01:1:0:0010, Page erase LDROM
BYTE_PROGRAM_LD     = 0x61 # 01:1:0:0001, Byte program LDROM
BYTE_READ_LD        = 0x40 # 01:0:0:0000, Byte read LDROM
READ_CID            = 0x0B # 00:0:0:1011, Company ID



def test_get_rctrim_values():
	reconnect(False)
	target_setup(target)
	fw_name = "simpleserial-n76-test"
	fw_dir = os.path.join(get_base_fw_dir(), fw_name)
	target_name = fw_name
	fw_path = make_image(fw_dir, target_name)
	cw.program_target(scope, prog, fw_path)
	scope.io.target_pwr = False
	print("hard reset...")
	time.sleep(5)
	scope.io.target_pwr = True
	reboot_flush()
	scope.try_wait_clkgen_locked(10, 1)
	print(scope.clock)
	cmd = BYTE_READ_ID
	length = 4
	start = 0
	in_data = bytearray([cmd, start & 0xff, (start >> 8) & 0xff, length])

	data = None
	retries = 0
	while data is None:
		retries += 1
		if retries > 10:
			raise ValueError("Failed to read device id")
		target.simpleserial_write('n', in_data)
		data = target.simpleserial_read('r', length)
			
	# data is a 9-bit value, little-endian
	print("data: ", data)
	device_id = data[0] | (data[1] << 8) 
	print("device_id: {:02x}".format( device_id))
	data = None
	retries = 0
	while data is None:
		retries += 1
		if retries > 10:
			raise ValueError("Failed to read device id")
		target.simpleserial_write('x', bytearray())
		RC_TRIM_LEN = 12
		ret = target.simpleserial_read_witherrors('r', RC_TRIM_LEN)
		data = ret['payload']
	current_rc_trim_vals = data[0] << 1 | (data[1] & 0x01)
	rctrimVals30_31 = data[2] << 1 | (data[3] & 0x01)
	rctrimVals32_33 = data[4] << 1 | (data[5] & 0x01)
	rctrimVals34_35 = data[6] << 1 | (data[7] & 0x01)
	rctrimVals36_37 = data[8] << 1 | (data[9] & 0x01)
	rctrimVals38_39 = data[10] << 1 | (data[11] & 0x01)
	print("current_rc_trim_vals: ", current_rc_trim_vals)
	print("rctrimVals30_31 (16mhz): ", rctrimVals30_31)
	print("rctrimVals32_33 (??): ", rctrimVals32_33)
	print("rctrimVals34_35 (??): ", rctrimVals34_35)
	print("rctrimVals36_37 (??): ", rctrimVals36_37)
	print("rctrimVals38_39 (24mhz): ", rctrimVals38_39)
	target.simpleserial_write('b', bytearray()) # blink forever

run_ss_glitch_loop_test()
# run_ss_version_test("simpleserial-n76-test", "simpleserial-n76-test")
# test_get_rctrim_values()
# test_scope()
# gc.display_stats()
# print(get_base_fw_dir())