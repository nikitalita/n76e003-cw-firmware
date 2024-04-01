
import os
import platform
import subprocess
import time

from programmer_n76_icp import N76E003, N76ICPProgrammer, newaeUSBICPLib
from nuvoprogpy.nuvo51icpy.nuvo51icpy import Nuvo51ICP, ConfigFlags, N8051ConfigFlags

COMPILED_CLK_FREQ  = 7372800
ACTUAL_CLKGEN_FREQ = 24000000
USE_EXTERNAL_CLOCK = 1
COMPILED_BAUD_RATE = 115200
SS_VER = "SS_VER_2_1"
PLATFORM = "CW308_MS5132K_AT20"
CRYPTO_TARGET = "NONE"
NU51_BASE_FW_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "numicro8051")

n8051_boards = ["CW308_N76E003", "CW308_N76S003_AT20", "CW308_MS5116K_AT20", "CW308_MS5132K_AT20"]

def get_base_fw_dir():
	# find the directory where the chipwhisperer python module is located
	# this is used to find the firmware directory
	cw_dir = os.path.dirname(cw.__file__)
	# ../../hardware/victims/firmware/
	cw_dir = os.path.normpath(os.path.join(cw_dir, "..", "..", "hardware", "victims", "firmware"))
	if PLATFORM in n8051_boards:
		return os.path.join(cw_dir, "numicro8051")
	return cw_dir

def get_base_scope_fw_dir():
	# find the directory where the chipwhisperer python module is located
	# this is used to find the firmware directory
	cw_dir = os.path.dirname(cw.__file__)
	# ../../hardware/victims/firmware/
	cw_dir = os.path.normpath(os.path.join(cw_dir, "..", "..", "hardware", "capture", "chipwhisperer-lite", "sam3u_fw", "SAM3U_VendorExample", "src"))
	return cw_dir

MAKE_COMMAND = "make" if platform.system() != "Darwin" else "gmake"

def make_image(fw_dir:str, target_name:str = "", platform:str = PLATFORM):
	# get the last part of fw_dir
	fw_base = target_name if target_name else os.path.basename(fw_dir)
	print(subprocess.check_output([MAKE_COMMAND, "clean"], 
					cwd=fw_dir).decode("utf-8"))	
	use_external_clock = 1 if USE_EXTERNAL_CLOCK else 0
	args = [
            MAKE_COMMAND,
            "PLATFORM={}".format(platform),
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

def upgrade_scope_firmware():
	global scope
	scope_fw_dir = get_base_scope_fw_dir()
	make_image(scope_fw_dir)
	scope_fw_bin = os.path.join(scope_fw_dir, "ChipWhisperer-Lite.bin")
	try:
		scope.dis()
		scope = None
	except Exception as e:
		print(e)
	finally:
		scope = cw.scope(force= True)
	if scope and scope.connectStatus and scope._getCWType() != "cwlite":
		raise IOError("Only ChipWhisperer Lite is supported right now!")
	scope.upgrade_firmware(scope_fw_bin)
	scope.dis()
	scope = None
	time.sleep(1)


def main_test():
	from mocks.mock_scope import MockOpenADC
	fw_dir = os.path.join(get_base_fw_dir(), "blink-forever")
	make_image(fw_dir)
	fw_path = os.path.join(fw_dir, "blink-forever-{}.hex".format(PLATFORM))
	p = N76ICPProgrammer()
	# upgrade_scope_firmware()
	# REQ_TEST_THING = 0x96
	p.scope = cw.scope()
	p.scope.default_setup()
	p.scope.io.nrst = None
	# scope_logger.setLevel(logging.DEBUG)
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

		# config.set_brownout_detect(False)
		# nuvo.program_config(config)
		# new_config = nuvo.read_config()
		# print("\n\n*** New Config ***")
		# new_config.print_config()

def program_blink_forever():
	scope = cw.scope()
	base_fw_dir = get_base_fw_dir()
	fw_dir = os.path.join(base_fw_dir, "blink-forever")
	blink_aprom = make_image(fw_dir)
	blink_aprom = blink_aprom.replace(".hex", ".bin")
	blink_aprom_data = N76ICPProgrammer.convert_to_bin(blink_aprom)
	with Nuvo51ICP(library=newaeUSBICPLib(scope)) as icp:
		icp.mass_erase()
		icp.program_aprom(blink_aprom_data, erase=False)
		config = icp.read_config()
		dev_info = icp.get_device_info()
		print(dev_info)
		config.print_config()

def program_good_stuff():
	bootloader_plat = PLATFORM.replace("CW308_", "").replace("_AT20", "")
	bootloader_dir = "~/nuvoprog/bootloader"
	bootloader_ldrom = make_image(bootloader_dir, platform=bootloader_plat)
	bootloader_ldrom = os.path.join(bootloader_dir, "bootloader-{}.hex".format(bootloader_plat))
	scope = cw.scope()
	base_fw_dir = get_base_fw_dir()
	fw_dir = os.path.join(base_fw_dir, "blink-forever")
	blink_aprom = make_image(fw_dir)
	blink_aprom = blink_aprom.replace(".hex", ".bin")
	bootloader_ldrom = bootloader_ldrom.replace(".hex", ".bin")
	blink_aprom_data = N76ICPProgrammer.convert_to_bin(blink_aprom)
	bootloader_ldrom_data = N76ICPProgrammer.convert_to_bin(bootloader_ldrom)
	with Nuvo51ICP(library=newaeUSBICPLib(scope)) as icp:
		config = N8051ConfigFlags()
		config.set_ldrom_boot(True)
		config.set_ldrom_size_kb(2)
		config.set_brownout_detect(False)
		config.set_brownout_reset(False)
		config.set_brownout_inhibits_IAP(False)

		icp.mass_erase()
		icp.program_all(blink_aprom_data, bootloader_ldrom_data, config, _erase=False)
		config = icp.read_config()
		dev_info = icp.get_device_info()
		print(dev_info)
		config.print_config()




if __name__ == "__main__":
	program_blink_forever()
	# program_good_stuff()
