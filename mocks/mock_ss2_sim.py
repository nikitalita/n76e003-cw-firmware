# -*- coding: utf-8 -*-
#
# Copyright (c) 2014-2021, NewAE Technology Inc
# All rights reserved.
#
# Find this and more at newae.com - this file is part of the chipwhisperer
# project, http://www.chipwhisperer.com . ChipWhisperer is a registered
# trademark of NewAE Technology Inc in the US & Europe.
#
#    This file is part of chipwhisperer.
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.
#==========================================================================


import random
import time
import os
from typing import Callable
from chipwhisperer.logging import *
from chipwhisperer.capture.targets import SimpleSerial2

from .mock_sim import MockSim

SERIAL_MAX_WRITE = 58

FRAME_BYTE = 0x00
# typedef enum ss_err_cmd {
# 	SS_ERR_OK,
# 	SS_ERR_CMD,
# 	SS_ERR_CRC,
# 	SS_ERR_TIMEOUT,
#     SS_ERR_LEN,
#     SS_ERR_FRAME_BYTE
# } ss_err_cmd;
SS_ERR_OK = 0
SS_ERR_CMD = 1
SS_ERR_CRC = 2
SS_ERR_TIMEOUT = 3
SS_ERR_LEN = 4
SS_ERR_FRAME_BYTE = 5

MOCK_SS_RESET = -1
MOCK_SS_NO_MSG = -2

RESET_RESULT = -1
SUCCESS_RESULT = 1
NORMAL_RESULT = 0



RESET_BUF = [ord(x) for x in "rRESET   \n"]
SS_VER_2_1 = 3
NON_RESET_CMDS = ['v', 'w', 't']

class SimpleSerial2TargetSim(MockSim):
    def check_version(self, cmd, scmd, length, data):
        self.send_response('r', [SS_VER_2_1])
        return SS_ERR_OK
    
    def get_commands(self, cmd, scmd, length, data):
        self.send_response('r', [ord(x) for x in self.cmds.keys()])
        return SS_ERR_OK

    def glitch_loop(self, cmd, scmd, length, data):
        cnt = 0
        res = self.trigger_callback(True)
        if res == RESET_RESULT:
            return self.reset()
        elif res == SUCCESS_RESULT:
            cnt = 1
        for i in range(50):
            for j in range(50):
                cnt += 1
        self.trigger_callback(False)
        res = [cnt & 0xFF, (cnt >> 8) & 0xFF, (cnt >> 16) & 0xFF, (cnt >> 24) & 0xFF]
        self.send_response('r', res)
        return SS_ERR_OK if cnt == 2500 else 0x10


    def glitch_comparison(self, cmd, scmd, length, data):
        ok = 5
        res = self.trigger_callback(True)
        # Mock
        if res == RESET_RESULT:
            return self.reset()

        if data[0] == 0xA2:
            ok = 1
        else:
            ok = 0

        # Mock
        if res == SUCCESS_RESULT:
            if ok == 1:
                ok = 0
            else:
                ok = 1
        self.trigger_callback(False)
        self.send_response('r', [ok])
        return SS_ERR_OK

    def password(self, cmd, scmd, length, data):
        passwd = "touch"
        passok = 1
        
        res = self.trigger_callback(True)
        if res == RESET_RESULT:
            return self.reset()

        for cnt in range(5):
            # Avoiding Python idx error
            if len(data) >= cnt:
                passok = 0
            elif data[cnt] != passwd[cnt]:
                passok = 0
                
        if res == SUCCESS_RESULT:
            passok = 1
            
        self.trigger_callback(False)
        self.send_response('r', [passok])
        return SS_ERR_OK

    def write_to_buf(self,data):
        self.databuf.extend(data)

    def infinite_loop(self, cmd, scmd, length, data):
        a = 0
        res = self.trigger_callback(True)
        if res == RESET_RESULT:
            return self.reset()
        self.trigger_callback(False)
        # while a != 2:
        #     pass
        # don't actually do an infinite loop
        if res == NORMAL_RESULT:
            return MOCK_SS_NO_MSG

        # success
        # return self.send_response('r', [ord(x) for x in "BREAKOUT\n"])
        self.write_to_buf([ord(x) for x in "rBREAKOUT\n"])
        return SS_ERR_OK

    def toggle_external_clock(self, cmd, scmd, len, data):
        return SS_ERR_OK


        
    @staticmethod
    def _unstuff_data(buf, len):
        """Removes COBS from buf

        Can currently get into an infinite loop, don't know why
        """
        next = buf[0]
        buf[0] = 0x00
        tmp = next
        while (next < len) and (tmp != 0):
            tmp = buf[next]
            buf[next] = FRAME_BYTE
            next = (next + tmp) & 0xFF
        return next

    @staticmethod
    def _stuff_data(buf):
        """Apply COBS to buf
        """
        l = len(buf)
        ptr = 0
        last = 0
        for i in range(1, l):
            if (buf[i] == FRAME_BYTE):
                buf[last] = i - last
                last = i
                # target_logger.debug("Stuffing byte {}".format(i))
        return buf

    def make_packet(self, resp_code, data) -> bytearray:
        if type(data) is list:
            data = bytearray(data)
        if isinstance(resp_code, str):
            resp_code = ord(resp_code[0])
        buf = [0x00, resp_code, len(data)]
        buf.extend(data)
        crc = SimpleSerial2._calc_crc(buf[1:])
        buf.append(crc)
        buf.append(0x00)
        buf = self._stuff_data(buf)
        return buf
        
    def make_error(self, error_code)  -> bytearray:
        return self.make_packet('e', bytearray([error_code]))
    
    def send_response(self, resp_code, data):
        self.write_to_buf(self.make_packet(resp_code, data))

    def send_error(self, error_code):
        self.write_to_buf(self.make_error(error_code))

    def process_cmd(self, data: bytearray):
        # check if any of the first four bytes are FRAME_BYTE
        if FRAME_BYTE in data[:4]:
            self.send_error(SS_ERR_FRAME_BYTE)
            return SS_ERR_FRAME_BYTE
        next_frame = self._unstuff_data(data, 4)

        req_cmd = chr(data[1])
        req_subcmd = data[2]
        req_len = data[3]
        real_len = req_len + 5
        if req_cmd not in self.cmds:
            self.send_error(SS_ERR_CMD)
            return SS_ERR_CMD
        if req_len + 5 < next_frame:
            self.send_error(SS_ERR_LEN)
            return SS_ERR_LEN
        i = 4
        for i in range(i, real_len):
            if data[i] == FRAME_BYTE:
                self.send_error(SS_ERR_FRAME_BYTE)
                return SS_ERR_FRAME_BYTE
        i += 1
        if data[i] != FRAME_BYTE:
            self.send_error(SS_ERR_LEN)
            return SS_ERR_LEN
        new_data = bytearray(data[next_frame:])
        self._unstuff_data(new_data, i + 1)
        data = bytearray(data[:next_frame]) + new_data + bytearray(data[i + 1:] if i + 1 < len(data) else bytearray())
        crc = SimpleSerial2._calc_crc(data[1:i-1])
        if crc != data[i-1]:
            self.send_error(SS_ERR_CRC)
            return SS_ERR_CRC
        err = self.cmds[req_cmd](req_cmd, req_subcmd, req_len, data[4:4+req_len])
        if err == MOCK_SS_RESET or err == MOCK_SS_NO_MSG:
            # don't send back anything if we reset
            return err
        self.send_error(err)
        return err
    @staticmethod
    def err_to_str(err):
        if err == SS_ERR_OK:
            return "SS_ERR_OK"
        elif err == SS_ERR_CMD:
            return "SS_ERR_CMD"
        elif err == SS_ERR_CRC:
            return "SS_ERR_CRC"
        elif err == SS_ERR_TIMEOUT:
            return "SS_ERR_TIMEOUT"
        elif err == SS_ERR_LEN:
            return "SS_ERR_LEN"
        elif err == SS_ERR_FRAME_BYTE:
            return "SS_ERR_FRAME_BYTE"
        else:
            return "Unknown Error"
        
    def __init__(self, trigger_callback):
        super().__init__(trigger_callback)
        self.databuf = bytearray(RESET_BUF)
        self.cmds: dict[str, callable] = {
            'v': self.check_version,
            'w': self.get_commands,
            'g': self.glitch_loop,
            'c': self.glitch_comparison,
            't': self.toggle_external_clock,
            '\x01': self.password,
            'i': self.infinite_loop
        }
        
    def reset(self):
        self.databuf = bytearray(RESET_BUF)
        self.trigger_callback(False)
        return MOCK_SS_RESET

    def send_to_target(self, data):
        is_flush_cmd = (data == bytearray([0,0]))
        err = self.process_cmd(data)
        if err != SS_ERR_OK and not is_flush_cmd:
            if err == MOCK_SS_RESET:
                target_logger.info("Random reset result, target reset")
            elif err != MOCK_SS_NO_MSG:
                target_logger.error("Error: " + self.err_to_str(err))
        
    def read_from_target(self, length = 0, timeout = 0):
        if length == 0:
            length = len(self.databuf)
        ret = self.databuf[:length]
        target_logger.info("Data: " + str(ret))
        self.databuf = self.databuf[length:] if length < len(self.databuf) else bytearray()
        return ret

    def in_waiting(self):
        return len(self.databuf)