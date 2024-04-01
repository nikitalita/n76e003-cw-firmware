from datetime import datetime
from enum import Enum
import logging
import math
import os
import time
import json
import chipwhisperer as cw
from chipwhisperer.capture.api.programmers import Programmer
from typing import Optional, List, overload, Union, Any
from NormalSerial import NormalSerial
from glitch_params import GlitchControllerParams
from logging import Logger
from collections import Counter
# enum result:
class TestResult(Enum):
    skipped = -2
    reset = -1
    success = 1
    normal = 0

    def __str__(self):
        return self.name.lower()
    
    @classmethod
    def has_name(cls, value):
        return value in cls._member_map_


DEFAULT_PARAM_FORMAT_STRING = "width: {:.2f}, offset: {:.3f}, repeat: {}, ext_offset: {}"
def get_properties(cls):
        return [attr for attr, value in vars(cls).items()
                                 if isinstance(value, property) ]

DATE_FORMAT =  "%Y-%m-%d_%H-%M-%S"

class TestTemplateException(Exception):
    pass
class TooManyResetsException(TestTemplateException):
    pass
class DeviceUnresponsiveException(TestTemplateException):
    pass
class BreakOnSuccessException(TestTemplateException):
    pass


class TestOptions:
    LOG_CRITICAL = logging.CRITICAL
    LOG_ERROR = logging.ERROR
    LOG_WARNING = logging.WARNING
    LOG_INFO = logging.INFO
    LOG_DEBUG = logging.DEBUG
    LOG_TRACE = 5
    def __init__(self, 
                    max_iterations: Optional[int] = None,
                    iter_before_report_status = 100,
                    iter_before_small_break = 500,
                    iter_before_big_break = 5000,
                    iter_before_very_big_break = 50000,
                    max_consec_resets_per_bad_setting = 100,
                    max_total_resets = 0,
                    max_total_dry_run_resets = 10,
                    very_big_break_seconds = 60,
                    big_break_seconds = 5,
                    small_break_seconds = 1,
                    enable_high_power = True,
                    enable_low_power = True,
                    hs2_output = 'clkgen',
                    should_break_on_success = False,
                    target_reset_io = 'nrst',
                    target_reset_io_high_is_on = True,
                    target_let_nrst_float_after_reset = True,
                    target_reset_wait = 0.05,
                    use_0_width_offset = False,
                    long_trigger_high_is_reset = True,
                    should_block_and_check_for_reset = True,
                    tries_per_setting = 1,
                    no_save = False,
                    no_arm_scope_during_glitch = False,
                    no_arm_scope_during_capture = False,
                    silence_target_warnings = True,
                    results_dir = "./results",
                    logger_level = logging.INFO,
                    fw_image_path: Optional[str] = None,
                    programmer_args: dict[str, Any] = None, 
                    no_program = False
                    ):
        """
        
        Args:
          - max_iterations (`Optional[int]`) [default = `None`]: The maximum number of iterations to run.
          - iter_before_report_status (`int`) [default = `100`]: The number of iterations before the status is reported.
          - iter_before_small_break (`int`) [default = `500`]: The number of iterations before a small break is taken.
          - iter_before_big_break (`int`) [default = `5000`]: The number of iterations before a big break is taken.
          - iter_before_very_big_break (`int`) [default = `50000`]: The number of iterations before a very big break is taken.
          - max_consec_resets_per_bad_setting (`int`) [default = `100`]: The maximum number of *consecutive* resets before a particular setting is skipped. 0 to Disable.
          - max_total_resets (`int`) [default = `0`]: The maximum number of total resets before the test is aborted. 0 to Disable.
          - max_total_dry_run_resets (`int`) [default = `10`]: The maximum number of total resets in dry run before the test is aborted.
          - very_big_break_seconds (`int`) [default = `120`]: The number of seconds that a very big break takes.
          - big_break_seconds (`int`) [default = `10`]: The number of seconds that a big break takes.
          - small_break_seconds (`int`) [default = `2`]: The number of seconds that a small break takes.
          - enable_high_power (`bool`) [default = `True`]: Whether to enable high power glitching.
          - enable_low_power (`bool`) [default = `True`]: Whether to enable low power glitching.
          - hs2_output (`str`) [default = `'clkgen'`]: The HS2 output during glitching attempts.
          - should_break_on_success (`bool`) [default = `True`]: Whether to break on success.
          - target_reset_io (`str`) [default = `'nrst'`]: The target reset io pin.
          - target_reset_io_high_is_on (`bool`) [default = `True`]: Whether the target reset io is high.
          - target_let_nrst_float_after_reset (`bool`) [default = `True`]: Whether to let the target reset io float after reset.
          - target_reset_wait (`float`) [default = `0.05`]: The length of time in seconds to wait when a reset is detected.
          - use_0_width_offset (`bool`) [default = `False`]: Whether to use 0 width or offset settings (avoiding possible double glitch).
          - long_trigger_high_is_reset (`bool`) [default = `True`]: Whether a long trigger high is reset.
          - should_block_and_check_for_reset (`bool`) [default = `True`]: Whether to block and check for reset.
          - tries_per_setting (`int`) [default = `1`]: The number of tries per setting.
          - no_save (`bool`) [default = `False`]: Whether to disable saving the session to disk.
          - no_arm_scope_during_glitch (`bool`) [default = `False`]: Whether to disable arming the scope during glitch.
          - no_arm_scope_during_capture (`bool`) [default = `False`]: Whether to disable arming the scope during capture.
          - silence_target_warnings (`bool`) [default = `True`]: Whether to silence target warnings emitted when getting data (e.g. SimpleSerial2 "Unexpected length" warnings)
          - results_dir (`[type]`) [default = `'./results'`]: The results directory.
          - logger_level (`int`) [default = `TestOptions.LOG_INFO`]: The logger level. Can be one of `TestOptions.LOG_TRACE`, `TestOptions.LOG_DEBUG`, `TestOptions.LOG_INFO`, `TestOptions.LOG_WARNING`, `TestOptions.LOG_ERROR`, `TestOptions.LOG_CRITICAL`.
          - fw_image_path (`Optional[str]`) [default = `None`]: The firmware image path.
          - programmer_args (`dict[str, Any]`) [default = `None`]: Additional programmer arguments.
          - no_program (`bool`) [default = `False`]: Whether to disable programming the target.
        """
        self.max_iterations = max_iterations
        self.iter_before_report_status = iter_before_report_status
        self.iter_before_small_break = iter_before_small_break
        self.iter_before_big_break = iter_before_big_break
        self.iter_before_very_big_break = iter_before_very_big_break
        self.max_consec_resets_per_bad_setting = max_consec_resets_per_bad_setting
        self.max_total_resets = max_total_resets
        self.max_total_dry_run_resets = max_total_dry_run_resets
        self.very_big_break_seconds = very_big_break_seconds
        self.big_break_seconds = big_break_seconds
        self.small_break_seconds = small_break_seconds
        self.enable_high_power = enable_high_power
        self.enable_low_power = enable_low_power
        self.hs2_output = hs2_output
        self.should_break_on_success = should_break_on_success
        self.target_reset_io = target_reset_io
        self.target_reset_io_high_is_on = target_reset_io_high_is_on
        self.target_let_nrst_float_after_reset = target_let_nrst_float_after_reset
        self.target_reset_wait = target_reset_wait
        self.use_0_width_offset = use_0_width_offset
        self.long_trigger_high_is_reset = long_trigger_high_is_reset
        self.should_block_and_check_for_reset = should_block_and_check_for_reset
        self.tries_per_setting = tries_per_setting
        self.no_save = no_save
        self.no_arm_scope_during_glitch = no_arm_scope_during_glitch
        self.no_arm_scope_during_capture = no_arm_scope_during_capture
        self.silence_target_warnings = silence_target_warnings
        self.results_dir = results_dir
        self.logger_level = logger_level
        self.fw_image_path = fw_image_path
        self.programmer_args = programmer_args if programmer_args else {}
        self.no_program = no_program

    def set_options(self, test_options):
        for key, value in test_options.__dict__.items():
            if hasattr(self, key) and key != "self" and key != self and not (isinstance(key, str) and key.startswith("__")):
                setattr(self, key, value)

class TestSetupTemplate(TestOptions):
    def __init__(self, scope: cw.scopes.ScopeTypes, target: cw.targets.TargetTypes, programmer_type: Optional[type[Programmer]], glitch_params: GlitchControllerParams, options: TestOptions = None):
        """
        Args:
            - scope (`cw.scopes.ScopeTypes`): The scope.
            - target (`cw.targets.TargetTypes`): The target.
            - glitch_params (`GlitchControllerParams`): The glitch parameters.
            - options (`TestOptions`) [default = `None`]: The test options.
        """
        super().__init__()
        self.scope: cw.scopes.ScopeTypes = scope
        # check if scope is a scope
        self.target: cw.targets.TargetTypes = target
        self.programmer_type: Optional[type[Programmer]] = programmer_type
        self.glitch_params = glitch_params
        self.gc: cw.GlitchController = glitch_params.generate_glitch_controller()
        if options:
            self.set_options(options)
        self.logger = None
        self.name = self.__class__.__name__
        self.logger = Logger(self.name)
        self._total_run_tries = 0
        self._scope_type = type(self.scope)
        self._target_type = type(self.target)
        self._strmhandler = logging.StreamHandler()
        self._strmhandler.setLevel(self.logger_level)
        self._target_logger = logging.getLogger("ChipWhisperer Target")
        self.logger.addHandler(self._strmhandler)
        self._reset_run_vars()
    
    def to_json(self):
        # only return the attributes in TestOptions, AND self.glitch_params
        opts = TestOptions()
        jsonable_dict = {key: value for key, value in self.__dict__.items() if not (key.startswith('_')) and (key in opts.__dict__)}
        jsonable_dict["glitch_params"] = self.glitch_params.to_json()
        return jsonable_dict
    
    def from_json(self, json_dict: dict):
        if isinstance(json_dict, str):
            json_dict = json.loads(json_dict)
        for key, value in json_dict.items():
            if key == "glitch_params":
                self.glitch_params = GlitchControllerParams()
                self.glitch_params.from_json(value)
                self.gc = self.glitch_params.generate_glitch_controller()
            else:
                if hasattr(self, key):
                    setattr(self, key, value)
                    
                    
    def load_glitch_session(self, session_dir_path):
        # get last part of session_dir_path
        session_name = os.path.basename(session_dir_path)
        # get the json file
        json_file = os.path.join(session_dir_path, session_name + ".json")
        with open(json_file, 'r') as file:
            json_dict = json.load(file)
            self.from_json(json_dict)
        csv_file = os.path.join(session_dir_path, session_name + ".csv")
        result_dict: dict[tuple, dict[str, int]] 
        params: list[str]
        result_dict, params = GlitchControllerParams().get_results_dict_and_params_from_csv(csv_file)
        result_dict_items = list(result_dict.items())
        for rditem in result_dict_items:
            result = rditem[0]
            val = rditem[1]
            for item in val.items():
                count = item[1]
                group = item[0]
                for i in range(count):
                    self.gc.add(group, result)
                if count > 0 and group == 'success':
                    self._successful_settings.append(list(result))


    @property
    def name(self):
        return self._name
    
    @name.setter
    def name(self, value):
        if self.logger:
            self.logger.name = value
        self._name = value
  

    def _set_io_line(self, line, val):
        setattr(self.scope.io, line, val)

    def reconnect(self):
        try:
            if self.scope and self.target:
                if self.scope_is_connected():
                    self.target.dis()
                    self.scope.dis()
                    time.sleep(1)
                self.scope.con()
                self.target.con(self.scope)
            else:
                raise Exception("No scope!!")
        except:
            self.logger.warn(
                "INFO: Caught exception on reconnecting to target - attempting to reconnect to scope first.")
            self.logger.warn("INFO: This is a work-around when USB has died without Python knowing. Ignore errors above this line.")
            if not self._scope_type or not self._target_type:
                raise Exception("No scope or target type set!")
            self.scope = cw.scope(self._scope_type)
            self.target = cw.target(self.scope, self._target_type)

    def _block_and_check_for_reset(self, retry=False):
        if not self.scope.clock.adc_freq:  # Not locking onto the clock, device probably reset
            return False
        ret = self.scope.capture()
        if ret:
            if retry:
                self.logger.warn('timeout! retrying...')
                self.scope.arm()
                self.iter_run()
                ret = self.scope.capture()
            if ret:
                return False
        return True

    def reset_target(self):
        # set the scope.io line specified by self.target_reset_io to low, then high
        # this is the same as pressing the reset button on the target
        setattr(self.scope.io, self.target_reset_io,
                (not self.target_reset_io_high_is_on))
        time.sleep(self.target_reset_wait)
        if self.target_let_nrst_float_after_reset:
            setattr(self.scope.io, self.target_reset_io, None)
        else:
            setattr(self.scope.io, self.target_reset_io, self.target_reset_io_high_is_on)
        time.sleep(self.target_reset_wait)


    def print_scope_status(self):
        # iterate through all the properties on io
        # Do not print it if it is not a property

        for top_level in ["io", "trigger", "glitch", "adc", "clock"]:
            iter = 0
            self.logger.info("*** scope.{}:".format(top_level))
            items = getattr(self.scope, top_level)._dict_repr().items()
            for key, value in items:
                iter += 1
                # convert any bytearray values to a hex string
                if isinstance(value, bytearray):
                    value = "[" + " ".join("{:02x}".format(x)
                                           for x in value) + "]"

                self.logger.info("- %-15s %-20s" % (key + ":", str(value)))
            self.logger.info("\n")

    def print_relevant_scope_glitch_status(self):
        self.logger.info("*** SCOPE SETTINGS:")
        self.logger.info("  - gain.gain:             %d" % self.scope.gain.gain)
        self.logger.info("  - clock.adc_src:         %s" % self.scope.clock.adc_src)
        self.logger.info("  - clock.adc_freq:        %d" % self.scope.clock.adc_freq)
        self.logger.info("  - clock.clkgen_freq:     %d" % self.scope.clock.clkgen_freq)
        if self.scope._is_husky or self.scope._is_husky_plus:
            self.logger.info("  - clock.adc_mul:         %d" % self.scope.clock.adc_mul)
        self.logger.info("  - IO PINS:")
        self.logger.info("    * tio1:  %10s     * tio2:  %10s     * tio3:  %10s" % (self.scope.io.tio1, self.scope.io.tio2, self.scope.io.tio3))
        self.logger.info("    * tio4:  %10s     * pdic:  %10s     * pdid:  %10s" % (self.scope.io.tio4, self.scope.io.pdic, self.scope.io.pdid))
        self.logger.info("    * glitch_hp:          %s" %
              ("ENABLED" if self.scope.io.glitch_hp else "DISABLED"))
        self.logger.info("    * glitch_lp:          %s" %
              ("ENABLED" if self.scope.io.glitch_lp else "DISABLED"))
        self.logger.info("    * hs2:                %s" % self.scope.io.hs2)
        self.logger.info("  - glitch.trigger_src:    %s" % self.scope.glitch.trigger_src)
        if self.scope.glitch.trigger_src == "ext_single":
            self.logger.info("  - glitch.arm_timing:     %s" %
                  self.scope.glitch.arm_timing)
        self.logger.info("  - trigger.triggers:      %s" % self.scope.trigger.triggers)
        self.logger.info("  - glitch.clk_src:        %s" % self.scope.glitch.clk_src)
        gloutputstr = "  - glitch.output:         %s " % self.scope.glitch.output
        if self.scope.glitch.output == "clock_only":
            self.logger.info(gloutputstr + "- Output only the original input clock")
        elif self.scope.glitch.output == "glitch_only":
            self.logger.info(gloutputstr + "- Output only the glitch pulses - do not use the clock")
        elif self.scope.glitch.output == "clock_or":
            self.logger.info(gloutputstr + "- Output is high if either the clock or glitch are high")
        elif self.scope.glitch.output == "clock_xor":
            self.logger.info(gloutputstr + "- Output is high if clock and glitch are different")
        elif self.scope.glitch.output == "enable_only":
            self.logger.info(gloutputstr + "- Output is high for glitch.repeat cycles (YOU PROBABLY DON'T WANT THIS IF ONLY VOLTAGE GLITCHING)")

    def glitch_enable(self):
        self.scope.io.glitch_lp = self.enable_low_power
        self.scope.io.glitch_hp = self.enable_high_power
        if self.scope._is_husky:
            self.scope.glitch.enabled = True
        self.scope.io.hs2 = self.hs2_output

    def glitch_disable(self):
        # if self.scope_is_connected():
        #     self.scope.io.glitch_lp = False
        #     self.scope.io.glitch_hp = False
        #     if self.scope._is_husky:
        #         self.scope.glitch.enabled = False
        if self.scope_is_connected():
            self.scope.glitch_disable()
        else:
            self.logger.error("Scope not set! Cannot disable glitch module.")

    def reboot_flush(self):
        self.target.flush()
        self.reset_target()
        self.target.flush()

    def get_param_format_string(self, params) -> str:
        param_format_args = []
        for i, param in enumerate(params):
            param_format = param + ": "
            if param == "width" or param == "offset":
                param_format += "{:.2f}"
            else:
                param_format += "{}"
            param_format_args.append(param_format)
        return ", ".join(param_format_args)

    def stringify_settings(self, glitch_settings=None):
        if not glitch_settings:
            return (DEFAULT_PARAM_FORMAT_STRING.format(self.scope.glitch.width, self.scope.glitch.offset, self.scope.glitch.repeat, self.scope.glitch.ext_offset))
        else:
            return (self._param_format_string.format(glitch_settings[0], glitch_settings[1], glitch_settings[2], glitch_settings[3]))

    def print_result(self, glitch_settings, result: str, reason="", run_num=0):
        result_fmt = "%s.........[%s]%s" % (self.stringify_settings(glitch_settings), str(result).upper(), reason)
        if run_num > 0:
            result_fmt = "[%d] " % run_num + result_fmt
        self.logger.info(result_fmt)

    def detect_bad_setting(self, previous_bad_settings) -> dict[str, Union[int, float]]:
        if self.max_consec_resets_per_bad_setting == 0:
            return None
        # find which width and reset occurred the most in the previous bad settings
        # get all the widths from the previous bad settings
        widths = [setting[self._width_idx] for setting in previous_bad_settings]
        c = Counter(widths)
        # get the width that occurred the most
        max_width = c.most_common(1)[0][0]
        repeats = [setting[self._repeat_idx] for setting in previous_bad_settings]
        c = Counter(repeats)
        max_repeat = c.most_common(1)[0][0]
        return {"width": max_width, "repeat": max_repeat}

    def report_result(self, glitch_settings, result: Union[TestResult, str], reason="", silent=False, run_num=0):
        # switch on result
        if not silent:
            if ((result != TestResult.skipped and result != TestResult.normal) or
                (result == TestResult.skipped and self.logger_level <= TestOptions.LOG_TRACE) 
                or (result == TestResult.normal and self.logger_level <= TestOptions.LOG_DEBUG)):
                self.print_result(glitch_settings, result, reason, run_num=run_num)
        if result == TestResult.normal:
            self.gc.results.add("normal", glitch_settings)
            self.gc.group_counts[self._normal_idx] += 1
        elif result == TestResult.reset:
            self.gc.results.add("reset", glitch_settings)
            self.gc.group_counts[self._reset_idx] += 1
        elif result == TestResult.success:
            self.gc.results.add("success", glitch_settings)
            self.gc.group_counts[self._success_idx] += 1
            self._successful_settings.append(list(glitch_settings))
        elif result == TestResult.skipped:
            self.gc.results.add("skipped", glitch_settings)
            self.gc.group_counts[self._skipped_idx] += 1
        else:
            self.gc.results.add(result, glitch_settings)
            self.gc.group_counts[self.gc.groups.index(result)] += 1

    def _check_bad_glitch_setting(self, glitch_setting) -> Optional[str]:
        width = glitch_setting[self._width_idx]
        repeat = glitch_setting[self._repeat_idx]
        offset = glitch_setting[self._offset_idx]
        if not self.use_0_width_offset:
            if -1 < width < 1:
                return "width = 0"
            if -1 < offset < 1:
                return "offset = 0"
        if width in self._bad_widths:
            repeat_thresh = self._width_repeat_thresholds[width]
            if repeat >= repeat_thresh:
                return f"width = {width}, repeat >= {repeat_thresh}"
        return None

    def _set_glitch_settings(self, glitch_setting):
        if self._first_iter:
            self.scope.glitch.width = glitch_setting[self._width_idx]
            self.scope.glitch.offset = glitch_setting[self._offset_idx]
            self.scope.glitch.repeat = glitch_setting[self._repeat_idx]
            self.scope.glitch.ext_offset = glitch_setting[self._ext_offset_idx]
            self._first_iter = False
        else:
            if not self._width_is_static:
                self.scope.glitch.width = glitch_setting[self._width_idx]
            if not self._offset_is_static:
                self.scope.glitch.offset = glitch_setting[self._offset_idx]
            if not self._repeat_is_static:
                self.scope.glitch.repeat = glitch_setting[self._repeat_idx]
            if not self._ext_offset_is_static:
                self.scope.glitch.ext_offset = glitch_setting[self._ext_offset_idx]
        return True
    
    def _take_a_break(self, seconds):
        self.logger.info("*** taking a break for %d seconds..." % (seconds))
        time.sleep(seconds)
        return True

    def report_status(self, glitch_settings=None):
        self._report_status(glitch_settings, self._current_run_tries,
                            self.glitch_params.get_number_of_iters() * self.tries_per_setting)

    def _report_status(self, glitch_settings, num_tries: int, total_tries: int):
        time_elapsed = time.time() - self._start_time
        time_m_s_str = "%dm%02ds" % divmod(time_elapsed, 60)
        if num_tries > 0 and time_elapsed > 10:
            remaining_tries = total_tries - num_tries
            very_big_breaks_taken = num_tries // self.iter_before_very_big_break
            big_breaks_taken = num_tries // self.iter_before_big_break - very_big_breaks_taken
            small_breaks_taken = num_tries // self.iter_before_small_break - big_breaks_taken - very_big_breaks_taken
            time_on_tries = time_elapsed - (self.very_big_break_seconds * very_big_breaks_taken) - (self.big_break_seconds * big_breaks_taken) - (self.small_break_seconds * small_breaks_taken)
            very_big_breaks_remaining = remaining_tries // self.iter_before_very_big_break  
            big_breaks_remaining = remaining_tries // self.iter_before_big_break - very_big_breaks_remaining
            small_breaks_remaining = remaining_tries // self.iter_before_small_break - big_breaks_remaining - very_big_breaks_remaining
            break_second = (self.very_big_break_seconds * very_big_breaks_remaining) + (self.big_break_seconds * big_breaks_remaining) + (self.small_break_seconds * small_breaks_remaining)
            estimated_time_remaining = (time_on_tries / num_tries) * (remaining_tries) + break_second
            est_m_s_str = "%dm%02ds" % divmod(estimated_time_remaining, 60)
            self.logger.info("* STATUS [%d / %d] (%s / ETR: %s): %s" % (num_tries, total_tries,
                time_m_s_str, est_m_s_str, self.get_current_counts()))
        else:
            self.logger.info("* STATUS [%d / %d] (%s, Est. unknown): %s" % (num_tries, total_tries, time_m_s_str, self.get_current_counts()))
        self.logger.info(" - Next params: %s\n" %
              self.stringify_settings(glitch_settings))

    # returns a string containing the current counts

    def get_current_counts(self) -> str:
        cnt_str = ""
        total = sum(self.gc.group_counts)
        for i in range(0, len(self.gc.groups)):
            count = self.gc.group_counts[i]
            cnt_str += "%s: %d" % (self.gc.groups[i], self.gc.group_counts[i])
            if total > 0 and count > 0:
                rate = count / total
                cnt_str += " (%.1f%%)" % (rate * 100)
            if i != len(self.gc.groups) - 1:
                cnt_str += ", "
        return cnt_str

    def should_take_break(self) -> int:
        if self._current_run_tries == 0:
            return 0
        if self._current_run_tries % self.iter_before_very_big_break == 0:
            return self.very_big_break_seconds
        if self._current_run_tries % self.iter_before_big_break == 0:
            return self.big_break_seconds
        elif self._current_run_tries % self.iter_before_small_break == 0:
            return self.small_break_seconds
        return 0
    # User defined functions

    # This is called before the run is started
    # Do whatever you need to do to setup the target here
    # Returns True is setup is successful
    # Returns False if not

    def prep_run(self) -> bool:
        """
        prep_run()
        ------
        This is called before the run is started
        Do whatever you need to do to setup the target here
        You can optionally raise a TargetConnectionError here for a stack trace

        #### Returns:
            bool
                Returns True is setup is successful
                Returns False if not

        """        
        return True

    def after_run(self) -> None:
        """
        After the run is complete, this is called
        Clean up anything you need to here
        """
        pass

    def iter_run(self) -> bool:
        """
        Run the test; whatever this does, it should end up triggering a trigger line set in `scope.trigger.triggers`
        """
        self._set_io_line("tio4", True)
        time.sleep(0.0001)
        self._set_io_line("tio4", False)
        time.sleep(0.1)
        return True

    def get_data(self) -> Any:
        """
        This retrieves the data from the target
        
        This will be passed into check_result below
        """
        return "Normal"

    def check_result(self, data: Any) -> Union[TestResult, str]:
        """
        This is where you check the result of the test
        - Return `TestResult.normal` if the data is what we would expect from an unglitched run
        - Return `TestResult.reset` if the data is bad and you want to reset the target
        - Return `TestResult.success` if the data indicates a successful glitch
        - Return a string if you want to add this result to a custom group (e.g. `"interesting"`)
          - Make sure to add these to your `GlitchControllerParams`
        """
        return TestResult.normal

    def inc_run_tries(self):
        self._current_run_tries += 1
        self._total_run_tries += 1

    def print_glitch_ranges(self):
        self.logger.info("*** Glitch ranges:")
        ranges = ""
        single_values = ""
        for param in self.glitch_params.param_order:
            parm_range = getattr(self.glitch_params, param + "_range")
            if isinstance(parm_range, list):
                ranges += ((" - %10s: min = %5.1f     max = %5.1f    step = %5.1f\n" %
                           (param, parm_range[0], parm_range[1], parm_range[2])))
            else:
                single_values += ((" - %10s: %s\n" % (param,
                                  str(getattr(self.glitch_params, param + "_range")))))
        self.logger.info(" - tries per setting: %d" % self.tries_per_setting)
        self.logger.info(ranges + single_values)

    def print_final_results(self):
        self.logger.info("******** Final results:")
        if (self._total_run_tries != self._current_run_tries):
            self.logger.info(" - Total attempts of all runs: %d" % self._total_run_tries)
        self.logger.info(" - Number of run attempts: %d" % self._current_run_tries)
        self.logger.info(" - Total time: %.1fs\n" % (time.time() - self._start_time))
        # Error checking here because we cannot raise an exception...
        if not self.gc or not (self.gc.groups and len(self.gc.groups) == len(self.gc.group_counts)):
            self.logger.error("No glitch controller results found!")
            return
        total = sum(self.gc.group_counts)
        for i in range(len(self.gc.groups)):
            group_name = self.gc.groups[i]
            group_count = self.gc.group_counts[i]
            group_rate = group_count / total if total > 0 else 0
            self.logger.info(" - {:10s}: {:10d} ({:0.1f}%)".format(group_name, group_count, group_rate * 100))
        if len(self._successful_settings) > 0:
            # print the parameters for each successful glitch
            self.logger.info("\nSuccessful glitch settings:\n")
            for glitch_setting in self._successful_settings:
                self.logger.info(" - %s" % self.stringify_settings(glitch_setting))
            

    def print_clock_status(self):
        # print out all the properties of scope.clock
        # get the type of the clock
        clktyp = type(self.scope.clock)
        for prop in get_properties(clktyp):
            try:
                if prop[0] != '_':
                    self.logger.info(prop + " = " + str(getattr(self.scope.clock, prop)))
            except:
                pass

    def _reacquire_clock(self):
        retries = 10
        if self.scope.clock.adc_src.startswith("extclk"):
            # this will force the adc to reaquire the clock rate
            self.scope.clock.adc_src = self.scope.clock.adc_src
            self.scope.clock.reset_dcms()
            time.sleep(1)
        while not self.scope.clock.adc_locked or not self.scope.clock.clkgen_locked:
            if retries == 0:
                    self.logger.error("***** Error! Could not lock ADC clock! *****")
                    self.logger.error("Scope status: ")
                    self.print_scope_status()
                    self.logger.error("***** Can't proceed without locked ADC, exiting....")
                    raise Exception("Could not lock ADC clock!")
            self.logger.info("Clock not locked. Retrying...")
            retries -= 1
            # this will force the adc to reaquire the clock rate
            self.scope.clock.adc_src = self.scope.clock.adc_src
            self.scope.clock.reset_dcms()
            time.sleep(1)
        self.logger.info("ADC clock locked at %d Hz." %
                  (self.scope.clock.adc_freq))
    
    def setup_run_log(self, run_name=""):
            if not run_name:
                run_name = self.name
            date = datetime.fromtimestamp(self._start_time).strftime(DATE_FORMAT) if self._start_time else datetime.now().strftime(DATE_FORMAT)
            filename = run_name + "_" + str(date)
            log_dir = os.path.join(self.results_dir, filename)
            if not self.make_dir_and_check_writable(log_dir):
                raise OSError(f"Log directory {log_dir} is not writable")
            filehndlr = logging.FileHandler(os.path.join(log_dir, filename + ".log"), mode='w')
            filehndlr.setLevel(self.logger_level)
            self.logger.addHandler(filehndlr)

    def _reset_run_vars(self):
        # Not really state, just for performance
        self._param_format_string: str = self.get_param_format_string(self.glitch_params.param_order)
        self._skipped_idx = self.gc.groups.index("skipped")
        self._success_idx = self.gc.groups.index("success")
        self._reset_idx = self.gc.groups.index("reset")
        self._normal_idx = self.gc.groups.index("normal")
        self._width_idx = self.glitch_params.get_param_index("width")
        self._offset_idx = self.glitch_params.get_param_index("offset")
        self._ext_offset_idx = self.glitch_params.get_param_index("ext_offset")
        self._repeat_idx = self.glitch_params.get_param_index("repeat")
        self._width_is_static = self.glitch_params.is_static("width")
        self._offset_is_static = self.glitch_params.is_static("offset")
        self._ext_offset_is_static = self.glitch_params.is_static("ext_offset")
        self._repeat_is_static = self.glitch_params.is_static("repeat")
        
        # Runtime state
        self._current_run_tries = 0
        self._start_time = time.time()
        self._successful_settings = []
        self._first_iter = True
        self._run_name = ""
        self._dry_run = False

        self._width_repeat_thresholds: dict[float, int] = {}
        self._bad_widths: set[float] = set()

    def program_target(self):
        if self.programmer_type and self.fw_image_path:
            self.logger.info("*** Programming target with %s...", self.fw_image_path)
            cw.program_target(self.scope, self.programmer_type, self.fw_image_path, **self.programmer_args)
            self.reboot_flush()
        else:
            self.logger.warn("*** No programmer type or firmware image path set, skipping programming...")

    def setup_run(self, run_name = "", _no_log = False):
        self._reset_run_vars()
        self._run_name = run_name
        if not self.no_save and not self.make_dir_and_check_writable(self.results_dir):
            raise OSError("Results directory is not writable")
        if not _no_log and not self.no_save:
            self.setup_run_log(run_name)
        if not self.no_program:
            self.program_target()
        else:
            self.logger.warn("*** Not programming target...")
        self.scope.errors.sam_led_setting = "Default"

    def scope_is_connected(self):
        return self.scope and self.scope.connectStatus and self.scope._is_connected
    def scope_is_armed(self):
        STATUS_ARM_MASK    = 0x01
        return self.scope_is_connected() and hasattr(self.scope, "sc") and self.scope.sc.getStatus() & STATUS_ARM_MASK

    def _teardown_run(self):
        self.glitch_disable()
        if self.scope_is_armed():
            self.scope.capture()
        self.print_final_results()
        if self._strmhandler:
            self.logger.handlers = [self._strmhandler]
        else:
            self.logger.handlers = []

    def setup_capture(self, capture_name = ""):
        self.setup_run(capture_name, True)
        self._capture_mode = True
        self.glitch_disable()

    def _teardown_capture(self):
        self._teardown_run()
        self._capture_mode = False

    def capture_sequence(self, total_attempts=1, capture_name = None):
        if capture_name is None:
            capture_name = self.name
        else:
            capture_name = capture_name
        traces = []
        try:
            total_resets = 0
            self.setup_capture(capture_name)
            self._capture_mode = True
            self._dry_run = True
            self.glitch_disable()  # make sure it's disabled
            self.logger.info("******** Starting capture run...")
            self.logger.info("*** Total number of iterations: %d\n" % total_attempts)
            self.reboot_flush()
            self._reacquire_clock()
            self.prep_run()
            self._reacquire_clock()
            for num_tries in range(total_attempts):
                last_state = self.scope.adc.state
                # If this returns false, it's either a 0 width setting that we already ran, or it's a bad setting
                if self.long_trigger_high_is_reset and last_state:
                    # can detect crash here (fast) before timing out (slow)
                    self.logger.info("Trigger still high!")
                    # Device is slow to boot?
                    self.reboot_flush()
                    total_resets += 1

                if num_tries % self.iter_before_report_status == 0:
                    self.logger.info("*** STATUS [%d / %d] (%.1fs): resets = %d" % (num_tries,
                          total_attempts, time.time() - self._start_time, total_resets))
                self.scope.arm()
                # test
                if not self.iter_run():
                    raise Exception("Error in iter_run()")

                if self.should_block_and_check_for_reset and not self._block_and_check_for_reset(False):
                    total_resets += 1
                    self.logger.info("Detected reset during capture!!")
                    self.reboot_flush()
                    continue
                traces.append(self.scope.get_last_trace())
                if self.silence_target_warnings:
                    prev_level = self._target_logger.getEffectiveLevel()
                    self._target_logger.setLevel(logging.ERROR)
                data = self.get_data()
                result = self.check_result(data)
                if self.silence_target_warnings:
                    self._target_logger.setLevel(prev_level)

                if result == TestResult.reset:
                    total_resets += 1
                    self.reboot_flush()
                if total_resets > self.max_total_resets:
                    self.logger.info("*** STATUS [%d / %d] (%.1fs): resets = %d" % (num_tries,
                          total_attempts, time.time() - self._start_time, total_resets))
                    self.logger.info("Too many resets, exiting...")
                    break
                if self.should_take_break() > 0:
                    if not self._take_a_break(self.should_take_break()):
                        # Too many resets
                        break
            self.logger.info("Done!")
        except KeyboardInterrupt:
            self.logger.info("Interrupted by user")
        except Exception as e:
            self.logger.error("Exception occurred during capture run: %s", str(e))
            self._teardown_capture()
            if not self.no_save:
                self.write_capture_results_to_disk(traces, capture_name)
            self.der_blinken_lights()
            self.after_run()
            # if it's not ours, raise
            if not isinstance(e, TooManyResetsException) and not isinstance(e, DeviceUnresponsiveException) and not isinstance(e, BreakOnSuccessException):
                raise e
            else:
                # otherwise, return
                return

            raise e
        self._teardown_capture()
        if not self.no_save:
            self.write_capture_results_to_disk(traces, capture_name)
        # we don't call this above because it can raise an exception
        self.after_run()
        return traces

    def _check_if_dir_is_writable(self, dir):
        if not os.path.exists(dir):
            return False
        effective_ids = False
        follow_symlinks = False
        if os.supports_effective_ids:
            effective_ids = True
        if os.supports_follow_symlinks:
            follow_symlinks = True
        if not os.access(dir, os.W_OK, effective_ids=effective_ids, follow_symlinks=follow_symlinks):
            return False
        return True

    def make_dir_and_check_writable(self, dir):
        # check if absolute
        if not os.path.isabs(dir):
            dir = os.path.join(os.getcwd(), dir)
        if not os.path.exists(dir):
            # Split the dir into parent and subdir and recursively check if parent is writable
            parent_dir = os.path.dirname(dir)
            while not os.path.exists(parent_dir):
                old_parent_dir = parent_dir
                parent_dir = os.path.dirname(parent_dir)
                # if parent dir is root, we can't go up any further
                if parent_dir == old_parent_dir:
                    break
            if not self._check_if_dir_is_writable(parent_dir):
                return False
            os.makedirs(dir)
        return self._check_if_dir_is_writable(dir)

    def _make_results_file_name(self, name, date, dir, ext, overwrite = False):
        filebase = name + "_" + date
        base = os.path.join(dir, filebase)
        filepath = base + ext
        iter = 0
        if not overwrite:
            while os.path.exists(filepath):
                iter+=1
                filepath = base + "_" + iter + ext
                if iter > 100000:
                    return os.path.join(dir, "WHATTHEHELLDIDYOUDO" + ext)
        return filepath

    def save_glitch_session(self, name = ""):
        if name == "":
            name = self.name
        date = datetime.fromtimestamp(self._start_time).strftime(DATE_FORMAT) if self._start_time else datetime.now().strftime(DATE_FORMAT)
        self.logger.info("Saving glitching session...")
        # can't raise exception here because we're in a teardown
        run_res_dir = os.path.abspath(os.path.join(self.results_dir, name + "_" + date))
        if not self.make_dir_and_check_writable(run_res_dir):
            self.logger.error("ERROR: Cannot write glitch results to directory %s" % run_res_dir)
            return
        csvfilepath = self._make_results_file_name(name, date, run_res_dir, ".csv", overwrite = True)
        jsonfilepath = self._make_results_file_name(name, date, run_res_dir, ".json", overwrite = True)
        csvfilepath_tmp = csvfilepath + ".tmp"
        jsonfilepath_tmp = jsonfilepath + ".tmp"
        with open(jsonfilepath_tmp, "w") as f:
            f.write(json.dumps(self.to_json(), indent=4))
        if os.path.exists(jsonfilepath):
            os.remove(jsonfilepath)
        os.rename(jsonfilepath_tmp, jsonfilepath)
        if not self.gc or not self.gc.results or not self.gc.results._result_dict:
            self.logger.error("ERROR: No glitch results to write")
            return
        lines = []
        header = ",".join(self.gc.parameters) + "," + ",".join(["%s,%s_rate" % (group, group) for group in self.gc.groups]) + ",total" + "\n"
        lines.append(header)
        for setting, group_count_dict in self.gc.results._result_dict.items():
            group_str = ",".join([str(group_count_dict[group]) +"," +str(group_count_dict[group+"_rate"]) for group in self.gc.groups])
            string = ",".join([str(x) for x in setting]) + "," + group_str + "," + str(group_count_dict["total"])
            lines.append(string + "\n")
        with open(csvfilepath_tmp, "w") as f:
            f.writelines(lines)
        if os.path.exists(csvfilepath):
            os.remove(csvfilepath)
        os.rename(csvfilepath_tmp, csvfilepath)
        self.logger.info("Glitching session saved to %s" % run_res_dir)
        

    def write_capture_results_to_disk(self, traces, name = ""):
        if not traces:
            self.logger.error("ERROR: No traces to write")
            return
        if name == "":
            name = self.name
        date = datetime.fromtimestamp(self._start_time).strftime(DATE_FORMAT) if self._start_time else datetime.now().strftime(DATE_FORMAT)
        basename = name + "_" + date
        tracesdir = os.path.join(self.results_dir, "traces")
        # can't raise exception here because we're in a teardown
        if not self.make_dir_and_check_writable(tracesdir):
            self.logger.error("ERROR: Cannot write glitch results to directory %s" % tracesdir)
            return
        project_path = os.path.join(tracesdir, basename)
        _project = cw.create_project(project_path)
        for i in range(0, len(traces)):
            trace = traces[i]
            _project.traces.append(cw.Trace(trace, "", "", i))
        _project.save()
        _project.close()
        _project = None
        self.logger.info("Traces saved to %s" % project_path + ".cwp")

    def run_sequence(self, name = "", dry_run = False):
        last_setting = None
        reset_settings = []
        # for checking if device is responsive
        MAX_CONSEC_TIMEOUT = 20
        MAX_CONSEC_RESETS = min(self.max_consec_resets_per_bad_setting, 100) if self.max_consec_resets_per_bad_setting > 0 else 100
        consecutive_resets = 0
        consecutive_timeouts = 0
        last_width = None
        reported_bad_skip: str = ""
        run_name: str
        dry_run_resets = 0
        total_resets = 0
        total_skipped = 0
        should_exit = False
        if name == "":
            name = self.name
            run_name = self.name + ("_dry_run" if dry_run else "")
        else:
            run_name = name + ("_dry_run" if dry_run else "")
        try:
            self.setup_run(run_name)
            self._dry_run = dry_run
            if not dry_run:
                self.glitch_enable()
            else:
                self.glitch_disable()
            self._reacquire_clock()
            self.logger.info(f"******** Test run configuration '{run_name}'" + (" (DRY RUN)" if dry_run else "") + ":")
            self.logger.info("")
            self.print_relevant_scope_glitch_status()
            self.logger.info("")
            self.print_glitch_ranges()
            total_iters = self.glitch_params.get_number_of_iters(False) * self.tries_per_setting
            self.logger.info("*** Total number of iterations: %d\n" % (total_iters))
            self.logger.info("******** Prepping run...")
            self.reboot_flush()
            self.prep_run()
            self._reacquire_clock()
            self.logger.info("******** Starting test run...{}".format(" (DRY RUN)" if dry_run else ""))
            def handle_reset(setting, reason):
                if setting:
                    self.report_result(setting, TestResult.reset, reason, run_num=self._current_run_tries + total_skipped)
                    reset_settings.append(list(setting))
                self.reboot_flush()
                nonlocal total_resets, consecutive_resets
                total_resets += 1
                consecutive_resets += 1
            def check_responsive(): # after too many consecutive timeouts
                nonlocal consecutive_resets, consecutive_timeouts, reset_settings
                # target may be unresponsive, test if a non-glitching run works
                self.reboot_flush()
                if not self.iter_run():
                    raise Exception("Error in iter_run()")
                data = self.get_data()
                result = self.check_result(data)
                if result == TestResult.reset:
                    self.logger.warn("***** Target is unresponsive, attempting reconnect...")
                    self.reconnect()
                    time.sleep(1)
                    self.glitch_disable()
                    self.reboot_flush()
                    if not self.iter_run():
                        raise Exception("Error in iter_run()")
                    data = self.get_data()
                    result = self.check_result(data)
                    if result == TestResult.reset:
                        self.logger.error("***** Target is still unresponsive, exiting...")
                        raise DeviceUnresponsiveException("Target is unresponsive")
                    # don't clear resets
                else: # possible bad setting
                    if self.max_consec_resets_per_bad_setting > 0 and consecutive_resets >= self.max_consec_resets_per_bad_setting:
                        bad_settings = self.detect_bad_setting(reset_settings)
                        if bad_settings:
                            bad_width = bad_settings['width']
                            bad_repeat_thresh = bad_settings['repeat']
                            self._bad_widths.add(bad_width)
                            self._width_repeat_thresholds[bad_width] = bad_repeat_thresh
                            self.logger.warn("***** Detected bad setting:  width = {0}, repeat >= {1}, skipping these settings for the rest of the run...".format(bad_width, bad_repeat_thresh))
                            reset_settings.clear()
                            consecutive_resets = 0
                            consecutive_timeouts = 0
            for glitch_setting in self.gc.glitch_values():                
                width = glitch_setting[self._width_idx]
                offset = glitch_setting[self._offset_idx]
                # TODO: FIX THIS HACK
                if not last_width:
                    last_width = glitch_setting[self._width_idx]
                elif width != last_width:
                    last_width = width
                    reset_settings.clear()

                for i in range(0, self.tries_per_setting):
                    last_state = self.scope.adc.state
                    if self.long_trigger_high_is_reset and last_state:
                        # can detect crash here (fast) before timing out (slow)
                        # Device is slow to boot?
                        handle_reset(last_setting, "Trigger still high")
                    if consecutive_resets >= MAX_CONSEC_RESETS or consecutive_timeouts >= MAX_CONSEC_TIMEOUT:
                        check_responsive()
                    # If this is None, the setting is good
                    _bad_setting = self._check_bad_glitch_setting(glitch_setting)
                    if not (_bad_setting is None):
                        if reported_bad_skip != _bad_setting:
                            self.logger.info("* Skipping bad setting: {0}".format(_bad_setting))
                            reported_bad_skip = _bad_setting
                        self.report_result(glitch_setting, TestResult.skipped, "Bad setting", run_num=self._current_run_tries + total_skipped)
                        total_skipped += 1
                        continue
                    if i == 0 and not self._set_glitch_settings(glitch_setting):
                        self.logger.warn("Setting glitch setting failed: %s" % str(glitch_setting))
                        continue
                    
                    last_setting = glitch_setting
                    if self._current_run_tries % self.iter_before_report_status == 0:
                        self._report_status(
                            glitch_setting, self._current_run_tries + total_skipped, total_iters) 
                    self.inc_run_tries()
                    self.scope.arm()
                    # test
                    if not self.iter_run():
                        raise Exception("Error in iter_run()")

                    if self.should_block_and_check_for_reset and not self._block_and_check_for_reset(False):
                        consecutive_timeouts += 1
                        self._reacquire_clock()
                        handle_reset(glitch_setting, " Scope timed out")
                        continue
                    consecutive_timeouts = 0
                    if self.silence_target_warnings:
                        prev_level = self._target_logger.getEffectiveLevel()
                        self._target_logger.setLevel(logging.ERROR)
                    data = self.get_data()
                    self.glitch_disable()

                    result = self.check_result(data)
                    if self.silence_target_warnings:
                        self._target_logger.setLevel(prev_level)
                    if result == TestResult.reset:
                        handle_reset(glitch_setting, "")
                        if dry_run:
                            self.logger.info("Getting resets on dry run (%d/%d)!!" % (dry_run_resets, self.max_total_dry_run_resets))
                            dry_run_resets += 1
                            if dry_run_resets >= self.max_total_dry_run_resets:
                                self.logger.info("***** Too many resets on dry run, exiting...")
                                raise TooManyResetsException("Too many resets")

                    else:
                        consecutive_resets = 0
                        reset_settings.clear()
                        self.report_result(glitch_setting, result, run_num=self._current_run_tries + total_skipped)
                        if result == TestResult.success:
                            self.logger.debug("Success data: ")
                            self.logger.debug(str(data) if hasattr(data, "__str__") else data)
                            if self.should_break_on_success:
                                self.logger.warn("SUCCESSFUL RESULT FOUND!! Breaking...")
                                raise BreakOnSuccessException("SUCCESSFUL RESULT! Breaking...")

                    if self.max_total_resets > 0 and total_resets > self.max_total_resets:
                        self._report_status(glitch_setting, self._current_run_tries + total_skipped, total_iters)
                        self.logger.info("***** Too many resets, exiting...")
                        raise TooManyResetsException("Too many resets")
                    if self.should_take_break() > 0:
                        if self.should_take_break() >= self.big_break_seconds and not self.no_save:
                            self.save_glitch_session(self._run_name)
                        if not self._take_a_break(self.should_take_break()):
                            # Too many resets
                            raise TooManyResetsException("Too many resets")

                    if not dry_run:
                        self.glitch_enable()
                    # end of tries_per_setting loop
                if should_exit:
                    break
                #end of setting loop

            self.logger.info("Done!")
        except KeyboardInterrupt:
            self.logger.info("Interrupted by user")
        except Exception as e: # So we keep the stack trace
            self._teardown_run()
            if not self.no_save:
                self.save_glitch_session(self._run_name)
            self.der_blinken_lights()
            self.after_run()
            # if it's not ours, raise
            if not isinstance(e, TooManyResetsException) and not isinstance(e, DeviceUnresponsiveException) and not isinstance(e, BreakOnSuccessException):
                raise e
            else:
                return
        self._teardown_run()
        if not self.no_save:
            self.save_glitch_session(self._run_name)
        self.after_run()

    def der_blinken_lights(self):
        if self.scope_is_connected():
            # this gives nice flashing lights on the CW to indicate something is up and the user should check it
            self.scope.errors.sam_led_setting = "Debug"


# if __name__ == "__main__":
#     scope = cw.scope()
#     scope.default_setup(False)
#     scope.io.glitch_hp = False
#     scope.io.glitch_lp = False
#     target: NormalSerial = cw.target(scope, NormalSerial)
#     width = [40.5, 49.6, 0.4]
#     offset = [40, 49, 1]
#     ext_offset = 5
#     repeat = 10
#     params = GlitchControllerParams(width, offset, ext_offset, repeat)
#     test = TestSetupTemplate(scope, target, params)
#     test.print_glitch_ranges()
#     test.should_block_and_check_for_reset = True
#     test.enable_high_power = False
#     test.enable_low_power = False
#     test.no_save = True
#     test.run_sequence("dry_run", True)

if __name__ == "__main__":
    if "success" == TestResult.success:
        print("success")
    print("done")