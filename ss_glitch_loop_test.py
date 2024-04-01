
from chipwhisperer.capture.targets import TargetTypes, SimpleSerial, SimpleSerial2
from chipwhisperer.capture.api.programmers import Programmer
import chipwhisperer as cw
from TestSetup import TestSetupTemplate, TestResult, TestOptions
from typing import Optional
import time
from chipwhisperer.common.utils.util import CWByteArray
NORMAL_I_VAL = 50
NORMAL_J_VAL = 50
NORMAL_CNT_VAL = NORMAL_I_VAL * NORMAL_J_VAL
BYTES_READ = 4

class SSGlitchLoopTest(TestSetupTemplate):
	def __init__(self, _scope: cw.scopes.OpenADC, target: SimpleSerial2, programmer: Optional[type[Programmer]], glitch_controller_params, options: TestOptions = None):
		super().__init__(_scope, target, programmer, glitch_controller_params, options)
		self._printed_success_warning = False

	def parse_values(self, data: list) -> int:
		return data[0] + (data[1] << 8) + (data[2] << 16) + (data[3] << 24)
	
	def prep_run(self) -> bool:
			retries = 10
			while(True):
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
						retries -= 1
						if retries == 0:
							raise Exception("Device did not respond as expected. Please check your setup.")
						print("Retrying...")
					else:
						break
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
			return TestResult.normal


# for checking if any SS target works
class SSVersionTest(TestSetupTemplate):
	VERSION_LENGTH = 1
	def __init__(self, _scope: cw.scopes.OpenADC, target: SimpleSerial2, programmer: Optional[type[Programmer]], glitch_controller_params, options: TestOptions = None):
		super().__init__(_scope, target, programmer, glitch_controller_params, options)
		self._printed_success_warning = False

	def parse_values(self, data: list) -> int:
		return data[0]
	
	def prep_run(self) -> bool:
			time.sleep(0.25)
			self.reboot_flush()
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
			self.target.simpleserial_write('v', bytearray([]))
			self._set_io_line("tio4", True)
			time.sleep(0.0001)
			self._set_io_line("tio4", False)
			if self.logger_level <= TestOptions.LOG_TRACE:
					end_time = time.time()
					self.logger.debug("Write time: %f" % (end_time - start_time))
			return True
	def get_data(self) -> Optional[CWByteArray]:
		if self.logger_level <= TestOptions.LOG_TRACE:
			start_time = time.time()
		read = self.target.simpleserial_read('r', self.VERSION_LENGTH)
		if self.logger_level <= TestOptions.LOG_TRACE:
			end_time = time.time()
			self.logger.debug("read time: %f" % (end_time - start_time))
		return read
	def check_result(self, data: CWByteArray) -> TestResult:
			if not data or len(data) != self.VERSION_LENGTH:
					if not data:
						self.logger.debug("Data is none")
					else:
						self.logger.debug("Data length is not {}: {}".format(self.VERSION_LENGTH, len(data)))
					return TestResult.reset
			version_val = self.parse_values(data)
			success_cond = version_val < 0 or version_val > 4
			if success_cond:
				self.logger.info("SUCCESS: version value: %d" % version_val)
				return TestResult.success
			return TestResult.normal


# TODO: Finish this
# class AESBootLoaderTest(TestSetupTemplate):
# 	def __init__(self, _scope: cw.scopes.OpenADC, target: SimpleSerial2, programmer: Optional[type[Programmer]], glitch_controller_params, options: TestOptions = None):
# 		super().__init__(_scope, target, programmer, glitch_controller_params, options)
# 		self._printed_success_warning = False

# 	def parse_values(self, data: list) -> int:
# 		return data[0] + (data[1] << 8) + (data[2] << 16) + (data[3] << 24)
	
# 	def prep_run(self) -> bool:
# 			self.ktp = cw.ktp.Basic()
# 			time.sleep(0.25)
# 			self.reboot_flush()
# 			if not self.iter_run():
# 				raise Exception("Failed to write to serial, please check your connections.")
# 			else:
# 				data: list = self.get_data()
# 				result = self.check_result(data)
# 				if result != TestResult.normal:
# 					# parse the data into a hex string
# 					data_len = str(len(data)) if not (data is None) else "None"
# 					data_str = " ".join("{:02x}".format(x) for x in data) if not (data is None) else "None"
# 					print("got back (len= "+ data_len +"): " + data_str)
# 					raise Exception("Device did not respond as expected. Please check your setup.")
# 			return True
# 	def after_run(self) -> None:
# 			pass
# 	def iter_run(self) -> bool:
# 			if self.logger_level <= TestOptions.LOG_TRACE:
# 					start_time = time.time()
# 			self.target.simpleserial_write('g', bytearray([]))
# 			if self.logger_level <= TestOptions.LOG_TRACE:
# 					end_time = time.time()
# 					self.logger.debug("Write time: %f" % (end_time - start_time))
# 			return True
# 	def get_data(self) -> Optional[CWByteArray]:
# 		if self.logger_level <= TestOptions.LOG_TRACE:
# 			start_time = time.time()
# 		read = self.target.simpleserial_read('r', BYTES_READ)
# 		if self.logger_level <= TestOptions.LOG_TRACE:
# 			end_time = time.time()
# 			self.logger.debug("read time: %f" % (end_time - start_time))
# 		return read
# 	def check_result(self, data: CWByteArray) -> TestResult:
# 			if not data or len(data) != BYTES_READ:
# 					if not data:
# 						self.logger.debug("Data is none")
# 					else:
# 						self.logger.debug("Data length is not 4: %d" % len(data))
# 					return TestResult.reset
# 			gcnt_val = self.parse_values(data)
# 			success_cond = (int(gcnt_val) != NORMAL_CNT_VAL)
# 			if success_cond:
# 				if not self._printed_success_warning:
# 					self.logger.warning("SUCCESS: On Success, device will return an error 0x10. This is expected behavior.")
# 					self._printed_success_warning = True
# 				self.logger.info("SUCCESS: Count value: %d" % gcnt_val)
# 				return TestResult.success
# 			return TestResult.normal

