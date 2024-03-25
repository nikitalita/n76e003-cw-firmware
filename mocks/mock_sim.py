import random
from typing import Callable, Optional, final
class MockSim:
        
    def __init__(self, trigger_callback: Callable[[bool], int]):
        self.trigger_callback = trigger_callback


    @property
    def trigger_callback(self) -> Callable[[bool], int]:
        """
        Trigger callback function.

        The sim calls this when it would normally set the trigger high.
        
        in the form of `callback(bool) -> int`.
        Parameter is the trigger state; True means high, False means low.
        - returning -1 means that the result should be a reset
        - returning 0 means that the result should be normal
        - returning 1 means that the result should be a successful glitch
        """
        return self._trigger_callback

    @trigger_callback.setter
    def trigger_callback(self, trigger_callback: Callable[[bool], int]):
        self._trigger_callback = trigger_callback

    def read_from_target(self, length = 0, timeout = 0):
        return bytearray()
    def send_to_target(self, data):
        pass
    def in_waiting(self):
        return 0
    def reset(self):
        pass
