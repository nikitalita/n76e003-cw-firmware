/*
    This file is part of the ChipWhisperer Example Targets
    Copyright (C) 2012-2020 NewAE Technology Inc.

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
*/

#include "hal.h"
#include "Common.h"
#include "isp_uart0.h"
#include <stdint.h>
#include <stdlib.h>


#include "simpleserial.h"

//uint8_t infinite_loop(uint8_t* in);
//uint8_t glitch_loop(uint8_t* in);
//uint8_t password(uint8_t* pw);

// Make sure no optimization happens for demo glitch logic.
// #pragma GCC push_options
// #pragma GCC optimize ("O0")

#if SS_VER == SS_VER_2_1
uint8_t glitch_loop(uint8_t cmd, uint8_t scmd, uint8_t len, uint8_t* in) REENTRANT
#else
uint8_t glitch_loop(uint8_t* in, uint8_t len) REENTRANT
#endif
{
    volatile uint16_t i, j;
    volatile uint32_t cnt;
    cnt = 0;
    trigger_high();
    for(i=0; i<50; i++){
        for(j=0; j<50; j++){
            cnt++;
        }
    }
    trigger_low();
    simpleserial_put('r', 4, (uint8_t*)&cnt);
#if SS_VER == SS_VER_2_1
    return (cnt != 2500) ? 0x10 : 0x00;
#else
    return (cnt != 2500);
#endif
}

#if SS_VER == SS_VER_2_1
uint8_t glitch_comparison(uint8_t cmd, uint8_t scmd, uint8_t len, uint8_t* in) REENTRANT
#else
uint8_t glitch_comparison(uint8_t* in, uint8_t len) REENTRANT
#endif
{
    uint8_t ok = 5;
    trigger_high();
    if (*in == 0xA2){
        ok = 1;
    } else {
        ok = 0;
    }
    trigger_low();
    simpleserial_put('r', 1, (uint8_t*)&ok);
    return 0x00;
}

#if SS_VER == SS_VER_2_1
uint8_t password(uint8_t cmd, uint8_t scmd, uint8_t len, uint8_t* pw) REENTRANT
#else
uint8_t password(uint8_t* pw, uint8_t len) REENTRANT
#endif
{
    char passwd[] = "touch";
    char passok = 1;
    int cnt;

    trigger_high();

    //Simple test - doesn't check for too-long password!
    for(cnt = 0; cnt < 5; cnt++){
        if (pw[cnt] != passwd[cnt]){
            passok = 0;
        }
    }

    trigger_low();

    simpleserial_put('r', 1, (uint8_t*)&passok);
    return 0x00;
}

#if SS_VER == SS_VER_2_1
uint8_t infinite_loop(uint8_t cmd, uint8_t scmd, uint8_t len, uint8_t* in) REENTRANT
#else
uint8_t infinite_loop(uint8_t* in, uint8_t len) REENTRANT
#endif
{
    led_ok(1);
    led_error(0);

    //Some fake variable
    volatile uint8_t a = 0;

    //External trigger logic
    trigger_high();
    trigger_low();

    //Should be an infinite loop
    while(a != 2){
    ;
    }

    led_error(1);
    led_error(1);
    led_error(1);
    led_error(1);
    led_error(1);
    led_error(1);
    led_error(1);
    led_error(1);
    led_error(1);

    putch('r');
    putch('B');
    putch('R');
    putch('E');
    putch('A');
    putch('K');
    putch('O');
    putch('U');
    putch('T');
    putch('\n');

    led_error(1);
    led_error(1);
    led_error(1);
    led_error(1);
    led_error(1);
    led_error(1);
    led_error(1);
    led_error(1);

    return 0;
}

// #pragma GCC pop_options

void BYTE_READ_FUNC(uint8_t cmd, uint16_t start, uint8_t len, uint8_t *buf)
{
  uint8_t i;
  set_IAPEN;
  IAPCN = cmd;
  IAPAH = (start >> 8) & 0xFF;
  IAPAL = start & 0xFF;
  for (i = 0; i < len - 1; i++)
  {
    set_IAPGO;
    buf[i] = IAPFD;
    IAPAL++;
  }
  // get the last one
  set_IAPGO;
  buf[i] = IAPFD;
  clr_IAPEN;
}

#if SS_VER == SS_VER_2_1
/**
 * @brief      Get the RC trim values (i.e. the internal clock calibration values)
*/
uint8_t get_rc_trim_values(uint8_t cmd, uint8_t scmd, uint8_t len, uint8_t* in) REENTRANT
#else
uint8_t get_rc_trim_values(uint8_t* in, uint8_t len) REENTRANT
#endif
{
    static uint8_t __data hircmap[12];
    hircmap[0] = RCTRIM0;
    hircmap[1] = RCTRIM1;
    BYTE_READ_FUNC(READ_UID, 0x30, 10, &hircmap[2]);
    simpleserial_put('r', 12, hircmap);
    return 0x00;
}


static uint8_t ROM_DATA[128];
#if SS_VER == SS_VER_2_1
/**
 * @brief      Get various rom data (e.g. CID, UID, etc.)
 * Expects 8-bit command, 16-bit start address (little endian), 8-bit length in input buffer
 * Commands are in isp_uart0.h
*/
uint8_t get_data(uint8_t cmd, uint8_t scmd, uint8_t len, uint8_t* in) REENTRANT
#else
uint8_t get_data(uint8_t* in, uint8_t len) REENTRANT
#endif
{
    if (len < 4) {
        return SS_ERR_LEN;
    }
    volatile uint8_t IAPcmd = in[0];
    // check to make sure the cmd isn't a program or erase command
    if (IAPcmd & 0x20) {
        return 0x18;
    }
    // little-endian
    volatile uint16_t start = in[1] | (((uint16_t)in[2]) << 8);
    volatile uint8_t length = in[3];
    if (length > 128) {
        return 0x17;
    }
    

    BYTE_READ_FUNC(IAPcmd, start, length, ROM_DATA);

    simpleserial_put('r', length, ROM_DATA);
    return 0x00;
}


#if SS_VER == SS_VER_2_1
// Just echos back the input data
uint8_t echo(uint8_t cmd, uint8_t scmd, uint8_t len, uint8_t *in) REENTRANT
#else
uint8_t echo(uint8_t* in, uint8_t len) REENTRANT
#endif
{
    simpleserial_put('r', len, in);
    return SS_ERR_OK;
}

#define TIMER_DIV12_VALUE_10ms_FOSC_160000			65536-13334	//13334*12/16000000 = 10 mS 		// Timer divider = 12 
// the idea is that the device will blink at different intervals depending on the clock speed
void Timer1_Delay10ms_16mhz_vals(UINT32 u32CNT)
{
    clr_T1M;      // T1M=0, Timer1 Clock = Fsys/12
    TMOD |= 0x10; // Timer1 is 16-bit mode
    set_TR1;      // Start Timer1
    while (u32CNT != 0)
    {
        TL1 = LOBYTE(TIMER_DIV12_VALUE_10ms_FOSC_160000); // Find  define in "Function_define.h" "TIMER VALUE"
        TH1 = HIBYTE(TIMER_DIV12_VALUE_10ms_FOSC_160000);
        while (TF1 != 1)
            ; // Check Timer1 Time-Out Flag
        clr_TF1;
        u32CNT--;
    }
    clr_TR1; // Stop Timer1
}

#define BLINK_DELAY 50

#if SS_VER == SS_VER_2_1
uint8_t blink_forever(uint8_t cmd, uint8_t scmd, uint8_t len, uint8_t* in) REENTRANT
#else
uint8_t blink_forever(uint8_t* in, uint8_t len) REENTRANT
#endif
{
    #ifdef FOSC_240000
    led_error(1);
    #endif
    while(1)
    {
        led_ok(1);
        Timer1_Delay10ms_16mhz_vals(BLINK_DELAY);
        led_ok(0);
        Timer1_Delay10ms_16mhz_vals(BLINK_DELAY);
    }
}

int main(void)
{
    platform_init();
    init_uart();
    trigger_setup();

    /* Device reset detected */
    putch('r');
    putch('R');
    putch('E');
    putch('S');
    putch('E');
    putch('T');
    putch(' ');
    putch(' ');
    putch(' ');
    putch('\n');

    simpleserial_init();
    simpleserial_addcmd('g', 0, glitch_loop);
    simpleserial_addcmd('c', 1, glitch_comparison);
    simpleserial_addcmd('n', 4, get_data);
    simpleserial_addcmd('x', 0, get_rc_trim_values);
    simpleserial_addcmd('y', 0, echo);
    simpleserial_addcmd('b', 0, blink_forever);
    #if SS_VER == SS_VER_2_1
    simpleserial_addcmd(0x01, 5, password);
    #else
    simpleserial_addcmd('p', 5, password);
    #endif
    simpleserial_addcmd('i', 0, infinite_loop);
    uint16_t __data count = 0;
    uint8_t __data curr_blink_val = 0;
    while(1) {
        simpleserial_get();
        if (count == 0){
            curr_blink_val = 1 - curr_blink_val;
            led_error(curr_blink_val);
        }
        count++;
    }
}
