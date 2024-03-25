from enum import Enum
import math
import time
import chipwhisperer as cw
from typing import Optional, List, Union
import csv
from chipwhisperer.capture.scopes.cwhardware.ChipWhispererGlitch import GlitchSettings
try:
    import ipywidgets as widgets  # type: ignore
except ModuleNotFoundError:
    widgets = None
import json

STANDARD_PARAMS = ["width", "offset", "ext_offset", "repeat"]
STANDARD_GROUPS = ["success", "reset", "normal", "skipped"]
def detect_encoding(csv_file_path: str) -> str:
    encoding = "utf-8"
    with open(csv_file_path, "r") as csv_file:
        read = csv_file.read(1)
        if read == "\ufeff":
            encoding = "utf-8-sig"
    return encoding

class GlitchControllerParams:
    def __init__(
        self,
        width_range: Union[list[float], float] = [-44.9, 49.8, 0.4],
        offset_range: Union[list[float], float] = [-44.9, 49.8, 0.4],
        ext_offset_range: Union[list[int], int] = [0, 8192, 1],
        repeat_range: Union[list[int], int] = [1, 50, 1],
        global_step: Union[float, int] = 0.4,
        custom_groups: Optional[list[str]] = None,
        param_order: list[str] = ["width", "offset", "ext_offset", "repeat"]
    ):
        self.global_step: Union[float, int] = global_step
        self.width_range: Union[list[float], float] = width_range
        self.offset_range: Union[list[float], float] = offset_range
        self.ext_offset_range: Union[list[int], int] = ext_offset_range
        self.repeat_range: Union[list[int], int] = repeat_range
        self.custom_groups = custom_groups
        # check if params has all the standard params
        if (set(param_order) != set(STANDARD_PARAMS)):
            params_to_remove = []
            for param in param_order:
                if param not in STANDARD_PARAMS:
                    # remove it
                    params_to_remove.append(param)
            for param in params_to_remove:
                param_order.remove(param)
            # add the params to the end of the list
            for param in STANDARD_PARAMS:
                if param not in param_order:
                    param_order.append(param)
        self.param_order = param_order


    def _fix_range(self, range: Union[list[float], list[int], float, int], int_only: bool) -> Union[list[float], list[int], float, int]:
        if hasattr(range, "__iter__"):
            range = list(range)
            min, max = (range[0], range[1]) if range[0] < range[1] else (
                range[1], range[0])
            if isinstance(range[2], list):
                step_size = range[2]
            else:
                step_size = abs(range[2]) if range[2] != 0 else (
                    abs(abs(max) - abs(min)) if max != min else abs(min))
            if int_only:
                min, max, step_size = (int(min), int(max), int(step_size))
            return [min, max, step_size]
        return range
    
    def _set_range(self, value: Union[list[float], list[int], float, int], int_only: bool, param_name: str):
        if int_only:
            # check if value is a float or an iterable containing a float
            if isinstance(value, float):
                # if it's not a round number, raise an exception
                if value != round(value):
                    raise ValueError(
                        param_name + " value must be an integer or a list of integers.")
            else: # check if value is iterable
                if hasattr(value, "__iter__"):
                    for val in list(value):
                        if val != round(val):
                            raise ValueError(
                                param_name + " value must be an integer or a list of integers.")
        if isinstance(value, int) or isinstance(value, float) or (hasattr(value, "__iter__") and len(value) == 3):
            return self._fix_range(value, int_only)
        else:
            # check if value is iterable
            if hasattr(value, "__iter__"):
                value = list(value)
                if len(value) == 2:
                    value.append(self.global_step)
                    return self._fix_range(value, int_only)
                else:
                    raise ValueError(
                        "{0} must be a single {1} value, or a list of {2} containing min, max, and (optionally) step".format(param_name, ("int" if int_only else "float"), ("ints" if int_only else "floats")))

    def _get_min(self, value: Union[list[float], list[int], float, int]) -> Union[int, float]:
        if isinstance(value, list):
            return value[0]
        return value

    def _set_min(self, curr_range: Union[list[float], list[int], float, int], new_min: Union[int, float], int_only: bool):
        if int_only:
            if isinstance(new_min , float) and new_min != round(new_min):
                raise ValueError(
                    "Value must be an integer.")
            else:
                new_min = int(new_min)
        if isinstance(curr_range, list):
            if new_min > curr_range[1]:
                raise ValueError(
                    "Min value must be less than max value.")
            curr_range[0] = new_min
            return curr_range
        else:
            if curr_range > new_min:
                return new_min
            else:
                return [new_min, curr_range, self.global_step]
    
    def _get_max(self, value: Union[list[float], list[int], float, int]) -> Union[int, float]:
        if isinstance(value, list):
            return value[1]
        return value
    
    def _set_max(self, curr_range: Union[list[float], list[int], float, int], new_max: Union[int, float], int_only: bool):
        if int_only:
            if isinstance(new_max , float) and new_max != round(new_max):
                raise ValueError(
                    "Value must be an integer.")
            else:
                new_max = int(new_max)
        if isinstance(curr_range, list):
            if new_max < curr_range[0]:
                raise ValueError(
                    "Max value must be greater than min value.")
            curr_range[1] = new_max
            return curr_range
        else:
            if curr_range < new_max:
                return new_max
            else:
                return [curr_range, new_max, self.global_step]
    
    def _get_step(self, value: Union[list[float], list[int], float, int]) -> Union[float, int]:
        if isinstance(value, list):
            return value[2]
        return self.global_step
    
    def _set_step(self, curr_range: Union[list[float], list[int], float, int], new_step: Union[int, float], int_only: bool):
        if int_only:
            if isinstance(new_step , float) and new_step != round(new_step):
                raise ValueError(
                    "Value must be an integer.")
            else:
                new_step = int(new_step)
        if isinstance(curr_range, list):
            curr_range[2] = new_step
            return curr_range
        else:
            return [curr_range, curr_range, new_step]

    @property
    def width_range(self) -> Union[list[float], float]:
        """A single value or  range of glitch widths."""
        return self._width_range

    @width_range.setter
    def width_range(self, value: Union[list[float], float]):
        self._width_range = self._set_range(value, False, "width_range")

    @property
    def width_min(self) -> float:
        return self._get_min(self._width_range)
    
    @width_min.setter
    def width_min(self, value: float):
        self._width_range = self._set_min(self._width_range, value, False)

    @property
    def width_max(self) -> float:
        return self._get_max(self._width_range)
    
    @width_max.setter
    def width_max(self, value: float):
        self._width_range = self._set_max(self._width_range, value, False)

    @property
    def width_step(self) -> float:
        return self._get_step(self._width_range)
    
    @width_step.setter
    def width_step(self, value: float):
        self._width_range = self._set_step(self._width_range, value, False)

    @property
    def offset_range(self) -> Union[list[float], float]:
        """A single value or range of glitch offsets."""
        return self._offset_range

    @offset_range.setter
    def offset_range(self, value: Union[list[float], float]):
        self._offset_range = self._set_range(value, False, "offset_range")

    @property
    def offset_min(self) -> float:
        return self._get_min(self._offset_range)
    
    @offset_min.setter
    def offset_min(self, value: float):
        self._offset_range = self._set_min(self._offset_range, value, False)

    @property
    def offset_max(self) -> float:
        return self._get_max(self._offset_range)
    
    @offset_max.setter
    def offset_max(self, value: float):
        self._offset_range = self._set_max(self._offset_range, value, False)

    @property
    def offset_step(self) -> float:
        return self._get_step(self._offset_range)
    
    @offset_step.setter
    def offset_step(self, value: float):
        self._offset_range = self._set_step(self._offset_range, value, False)
    @property
    def ext_offset_range(self) -> Union[list[int], int]:
        """A single value or range of external offset values."""
        return self._ext_offset_range

    @ext_offset_range.setter
    def ext_offset_range(self, value: Union[list[int], int]):
        self._ext_offset_range = self._set_range(value, True, "ext_offset_range")

    @property
    def ext_offset_min(self) -> int:
        return self._get_min(self._ext_offset_range)
    
    @ext_offset_min.setter
    def ext_offset_min(self, value: int):
        self._ext_offset_range = self._set_min(self._ext_offset_range, value, True)

    @property
    def ext_offset_max(self) -> int:
        return self._get_max(self._ext_offset_range)
    
    @ext_offset_max.setter
    def ext_offset_max(self, value: int):
        self._ext_offset_range = self._set_max(self._ext_offset_range, value, True)

    @property
    def ext_offset_step(self) -> int:
        return self._get_step(self._ext_offset_range)
    
    @ext_offset_step.setter
    def ext_offset_step(self, value: int):
        self._ext_offset_range = self._set_step(self._ext_offset_range, value, True)

    @property
    def repeat_range(self) -> Union[list[int], int]:
        """
        A single value or range of glitch repeat values.
        
        TODO: On Husky, the `repeat` parameter can be a list of integers, and this current scheme does not support that; if a list is passed in, it will be treated as [min, max, step]
        """
        return self._repeat_range

    @repeat_range.setter
    def repeat_range(self, value: Union[list[int], int]):
        self._repeat_range = self._set_range(value, True, "repeat_range")

    @property
    def repeat_min(self) -> int:
        return self._get_min(self._repeat_range)
    
    @repeat_min.setter
    def repeat_min(self, value: int):
        self._repeat_range = self._set_min(self._repeat_range, value, True)

    @property
    def repeat_max(self) -> int:
        return self._get_max(self._repeat_range)
    
    @repeat_max.setter
    def repeat_max(self, value: int):
        self._repeat_range = self._set_max(self._repeat_range, value, True)

    @property
    def repeat_step(self) -> int:
        return self._get_step(self._repeat_range)

    @repeat_step.setter
    def repeat_step(self, value: int):
        self._repeat_range = self._set_step(self._repeat_range, value, True)

    @property
    def global_step(self) -> Union[float, int]:
        """The global step value for all glitch parameters."""
        return self._global_step
    
    @global_step.setter
    def global_step(self, value: Union[float, int]):
        self._global_step = value

    @property
    def custom_groups(self):
        """Any: Additional groups for glitch results, besides "success", "reset", and "normal" """
        return self._custom_groups

    @custom_groups.setter
    def custom_groups(self, value):
        self._custom_groups = value

    @property
    def param_order(self):
        """The order of the glitch parameters."""
        return self._param_order
    
    @param_order.setter
    def param_order(self, order: list[str]):
        """
        Sets the order of the glitch parameters.
        """
        if (set(order) == set(STANDARD_PARAMS)):
            self._param_order = order
        else:
            raise ValueError(
                "Order must include all ranged glitch parameters or all parameters.")

    def _set_gc_range(self, gc: cw.GlitchController):
        gc.set_global_step(self.global_step)
        for name in self.param_order:
            range_val = getattr(self, name + "_range")
            if isinstance(range_val, list):
                gc.set_range(name, range_val[0], range_val[1])
                gc.set_step(name, range_val[2])
            else:
                gc.set_range(name, range_val, range_val)
                # gc.set_step(name, abs(range_val))

    def get_groups(self):
        return STANDARD_GROUPS + (self.custom_groups or [])

    def get_group_index(self, group_name):
        groups = self.get_groups()
        return groups.index(group_name)

    def get_param_index(self, param_name):
        return self._param_order.index(param_name)

    def get_skipped_steps(self, param_name, _step_size = None):
        if not (param_name in ["width", "offset"]):
            return 0
        range_val = getattr(self, param_name + "_range")
        if not isinstance(range_val, list):
            return 0
        if not ((range_val[0] < -1 and range_val[1] > -1) or (range_val[0] < 1 and range_val[1] > 1)):
            return 0
        if _step_size is None:
            _step_size = range_val[2]
        if isinstance(_step_size, list):
            steps = 0
            for step in _step_size:
                steps += self.get_skipped_steps(param_name, step)
            return steps

        steps_before_gt_neg1 = math.ceil(abs(range_val[0]) / _step_size)
        min_val = range_val[0] + (steps_before_gt_neg1 * _step_size)
        while min_val < -1:
            min_val +=_step_size
            steps_before_gt_neg1 -= 1
        steps_before_gt_neg1 += 2
        max_val = min_val
        steps_before_gt_1 = steps_before_gt_neg1
        while max_val < 1:
            max_val +=_step_size
            steps_before_gt_1 += 1
        steps_before_gt_1 -= 1
        return steps_before_gt_1 - steps_before_gt_neg1

    def is_static(self, param_name):
        val = getattr(self, param_name + "_range")
        if not isinstance(val, list) or val[0] == val[1]:
            return True
        return False

    def get_number_of_steps(self, param_name, skip_0_width_offset_range=True, _step_size = None):
        range_val = getattr(self, param_name + "_range")
        if not isinstance(range_val, list):
            return 1
        if range_val[2] == 0:
            return 1
        if _step_size is None:
            _step_size = range_val[2]
        if isinstance(_step_size, list):
            steps = 0
            for step in _step_size:
                steps += self.get_number_of_steps(param_name, _step_size = step)
            return steps
        steps_to_skip = self.get_skipped_steps(param_name, _step_size) if skip_0_width_offset_range else 0
        return ((math.floor(int((range_val[1] - range_val[0]) / _step_size))) - steps_to_skip) + 1


    def get_number_of_iters(self, skip_0_width_offset_range=True):
        """
        Returns the number of possible iterations for the glitch controller.
        For example, if width_range is [0, 10, 1] and offset_range is [0, 20, 2], then the number of iterations is 11 * 11 = 121.
        """
        params = self.param_order
        iter = 1
        for name in params:
            iter *= self.get_number_of_steps(name, skip_0_width_offset_range)
        return iter

    def generate_glitch_controller(self):
        groups = self.get_groups()
        parameters = self.param_order
        gc = cw.GlitchController(groups, parameters)
        self._set_gc_range(gc)
        # fixes the issue with `gc.add()` raising an exception if `gc.display_stats()` hasn't run beforehand
        if widgets is not None:
            gc.widget_list_groups = [widgets.IntText(value=0, description=group + " count:", disabled=True)
                                     for group in groups]
        return gc
    
    def to_json(self):
        return {
            "width_range": self.width_range,
            "offset_range": self.offset_range,
            "ext_offset_range": self.ext_offset_range,
            "repeat_range": self.repeat_range,
            "custom_groups": self.custom_groups,
            "param_order": self.param_order
        }
        
    def from_json(self, json_dict):
        if isinstance(json_dict, str):
            json_dict = json.loads(json_dict)
        self.width_range = json_dict["width_range"]
        self.offset_range = json_dict["offset_range"]
        self.ext_offset_range = json_dict["ext_offset_range"]
        self.repeat_range = json_dict["repeat_range"]
        self.custom_groups = json_dict["custom_groups"]
        self.param_order = json_dict["param_order"]
    
    @staticmethod
    def _get_idxs_from_csv_header(header_params: list[str]):
        gc_params_csv_idxes: dict[str, int] = {}
        gc_params = []
        gc_groups = []
        gc_group_csv_idxs: dict[str, int] = {}
        gc_group_rate_csv_idxs: dict[str, int] = {}
        for i, param in enumerate(header_params):
            param = param.strip()
            if param in STANDARD_PARAMS:
                gc_params.append(param)
                gc_params_csv_idxes[param] = i
            elif param.endswith("_rate"):
                gc_group_rate_csv_idxs[param] = i
            elif param != "total":
                gc_groups.append(param)
                gc_group_csv_idxs[param] = i
        return gc_params_csv_idxes, gc_group_csv_idxs, gc_group_rate_csv_idxs, gc_params, gc_groups

    @staticmethod
    def get_results_dict_and_params_from_csv(csv_file_path):
        with open(
            csv_file_path, "r", encoding=detect_encoding(csv_file_path)
        ) as csv_file:
            csv_reader = csv.reader(csv_file, delimiter=',')
            header_params = next(csv_reader)
            gc_params_csv_idxes, gc_group_csv_idxs, gc_group_rate_csv_idxs, gc_params, gc_groups = GlitchControllerParams._get_idxs_from_csv_header(header_params)
            result_dict = {}
            _gc_pcsv_items = list(gc_params_csv_idxes.items())
            int_indexes = set([i for i in range(len(_gc_pcsv_items)) if _gc_pcsv_items[i][0] in ["repeat", "ext_offset"]])
            for line in csv_reader:
                setting_list = []
                for item in _gc_pcsv_items:
                    value_str = line[item[1]]
                    value = 0
                    if (item[1] in int_indexes):
                        value = int(value_str)
                    else:
                        value = float(value_str)
                    setting_list.append(value)
                setting = tuple(setting_list)
                result_dict[setting] = {}
                for group in gc_groups:
                    count = int(line[gc_group_csv_idxs[group]])
                    result_dict[setting][group] = count
            return result_dict, gc_params

    # @staticmethod
    # def _get_results_dict_and_ranges_from_csv(csv_file_path):
    #     result_dict, gc_params = GlitchControllerParams.get_results_dict_and_params_from_csv(csv_file_path)
    #     width_idx = gc_params.index("width")
    #     offset_idx = gc_params.index("offset")
    #     ext_offset_idx = gc_params.index("ext_offset")
    #     repeat_idx = gc_params.index("repeat")
    #     first_result = next(iter(result_dict.keys()))
    #     width_min = first_result[width_idx]
    #     width_max = first_result[width_idx]
    #     width_step = None
    #     offset_min = first_result[offset_idx]
    #     offset_max = first_result[offset_idx]
    #     offset_step = None
    #     ext_offset_min = first_result[ext_offset_idx]
    #     ext_offset_max = first_result[ext_offset_idx]
    #     ext_offset_step = None
    #     repeat_min = first_result[repeat_idx]
    #     repeat_max = first_result[repeat_idx]
    #     repeat_step = None
    #     # TODO: finish this
        
    # @staticmethod
    # def get_gc_from_csv(csv_file_path):
    #     result_dict, range_dict = GlitchControllerParams._get_results_dict_and_ranges_from_csv(csv_file_path)
    #     gc_params = list(range_dict.keys())
    #     gc_groups = list(result_dict[list(result_dict.keys())[0]].keys())
    #     gc = cw.GlitchController(gc_groups, gc_params)
    #     gc.set_global_step(1)
    #     for param in gc_params:
    #         range_val = range_dict[param]
    #         if isinstance(range_val, list):
    #             gc.set_range(param, range_val[0], range_val[1])
    #             gc.set_step(param, range_val[2])
    #         else:
    #             gc.set_range(param, range_val, range_val)
    #             gc.set_step(param, abs(range_val))
    #     if widgets is not None:
    #         gc.widget_list_groups = [widgets.IntText(value=0, description=group + " count:", disabled=True)
    #                             for group in gc_groups]
    #     for result in result_dict:
    #         for group in result_dict[result]:
    #             count = result_dict[result][group]
    #             for i in range(count):
    #                 gc.add(group,result)
    #     return gc

# main             
if __name__ == "__main__":
    # test
    test = GlitchControllerParams()
    print(test.ext_offset_range)
    test.ext_offset_max = 50.0
    print(test.ext_offset_range)
    test.ext_offset_range = [0.0, 100.0, 1.0]
    print(test.ext_offset_range)
    # res_dict, params = GlitchControllerParams.get_results_dict_and_params_from_csv("/home/nikita/n76e003-fault-testing/results/test.csv")
    # test = GlitchControllerParams(param_order=params)
    # to_json = test.to_json()
    # print(to_json)
    # test2 = GlitchControllerParams()
    # test2.from_json(to_json)

    # gc = test.generate_glitch_controller()
    # for result in res_dict:
    #     for group in res_dict[result]:
    #         count = res_dict[result][group]
    #         for i in range(count):
    #             gc.add(group,result)
    # print("done")
