
import os
import platform
import subprocess
import time

from programmer_n76_icp import N76ICPProgrammer, newaeUSBICPLib
from nuvoprogpy.nuvo51icpy.nuvo51icpy import Nuvo51ICP

COMPILED_CLK_FREQ  = 16000000
ACTUAL_CLKGEN_FREQ = 16000000
USE_EXTERNAL_CLOCK = 1
SS_VER = "SS_VER_2_1"
PLATFORM = "CW308_N76E003"
CRYPTO_TARGET = "NONE"
NU51_BASE_FW_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "NuMicro8051_firmware")

def get_base_fw_dir():
	if PLATFORM == "CW308_N76E003":
		return NU51_BASE_FW_DIR
	# find the directory where the chipwhisperer python module is located
	# this is used to find the firmware directory
	cw_dir = os.path.dirname(cw.__file__)
	# ../../hardware/victims/firmware/
	cw_dir = os.path.normpath(os.path.join(cw_dir, "..", "..", "hardware", "victims", "firmware"))
	return cw_dir

def get_base_scope_fw_dir():
	# find the directory where the chipwhisperer python module is located
	# this is used to find the firmware directory
	cw_dir = os.path.dirname(cw.__file__)
	# ../../hardware/victims/firmware/
	cw_dir = os.path.normpath(os.path.join(cw_dir, "..", "..", "hardware", "capture", "chipwhisperer-lite", "sam3u_fw", "SAM3U_VendorExample", "src"))
	return cw_dir

MAKE_COMMAND = "make" if platform.system() != "Darwin" else "gmake"

def make_image(fw_dir:str):
	print(subprocess.check_output([MAKE_COMMAND, "clean"], 
					cwd=fw_dir).decode("utf-8"))	
	args = [
			MAKE_COMMAND,
			"PLATFORM={}".format(PLATFORM),
			"USE_EXTERNAL_CLOCK={}".format(USE_EXTERNAL_CLOCK), 
			"CRYPTO_TARGET={}".format(CRYPTO_TARGET), 
			"SS_VER={}".format(SS_VER), 
			"F_CPU={}".format(COMPILED_CLK_FREQ), 
			"-j"
			]
	print(subprocess.check_output(args, cwd=fw_dir).decode("utf-8"))
	fw_path = os.path.join(fw_dir, "simpleserial-glitch-{}.hex".format(PLATFORM))
	return fw_path
# get path of this file
#define REQ_TEST_THING 0x41
import chipwhisperer as cw
import logging
from chipwhisperer.logging import scope_logger

def thing():
	scope = cw.scope()
	with Nuvo51ICP(library=newaeUSBICPLib(scope)) as nuvo:
		config = nuvo.read_config()
		config.set_lock(True)
		nuvo.program_config(config)

def main_test():
	from mocks.mock_scope import MockOpenADC
	cur_path = os.path.dirname(os.path.realpath(__file__))
	fw_dir = os.path.join(cur_path, "NuMicro8051_firmware/simpleserial-glitch")
	make_image(fw_dir)
	fw_path = os.path.join(fw_dir, "simpleserial-glitch-{}.hex".format(PLATFORM))
	p = N76ICPProgrammer()
	scope_fw_dir = get_base_scope_fw_dir()
	make_image(scope_fw_dir)
	scope_fw_bin = os.path.join(scope_fw_dir, "ChipWhisperer-Lite.bin")
	p.scope = cw.scope(force= True)
	p.scope.upgrade_firmware(scope_fw_bin)
	p.scope.dis()
	p.scope = None
	time.sleep(1)
	# REQ_TEST_THING = 0x96
	p.scope = cw.scope()
	p.scope.default_setup()
	p.scope.io.nrst = None
	scope_logger.setLevel(logging.DEBUG)
	p.open()
	p.find()
	p.erase()
	p.program(fw_path)

def thing2():
	scope = cw.scope()
	with Nuvo51ICP(library=newaeUSBICPLib(scope)) as nuvo:
		dev_info = nuvo.get_device_info()
		config = nuvo.read_config()
		print(dev_info)
		config.print_config()

if __name__ == "__main__":
	main_test()