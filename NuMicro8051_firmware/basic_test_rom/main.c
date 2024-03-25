// main.c
// combined: One project that combines all of the smaller modules
// Assumes 7.37 MHz clock speed

// Different project modes:
// - print: prints "Testing #" for debug
// - passcheck: password check susceptible to timing attacks
// - glitchloop: looped calculations susceptible to glitching
// - xor: SimpleSerial XOR encryption     (128 bit key, 128 bit block)
// - aes: SimpleSerial AES-128 encryption (128 bit key, 128 bit block)
// - tea: SimpleSerial TEA encryption     (128 bit key, 64 bit block)

// Include this once for 8051-specific IO

//#include <stdio.h>
#include "N76E003.h"
#include "SFR_Macro.h"
#include "Function_define.h"
#include "Common.h"
#include "Delay.h"

#include "hal.h"


#ifdef GPIO_FOREVER
void init_leds() {
    P03_PUSHPULL_MODE;
    P12_PUSHPULL_MODE;
    P05_PUSHPULL_MODE;

    // set LED 1 to on
    P03 = 1;
    P12 = 1;
    P05 = 0;
}

void toggle_GPIO_forever(void){
	unsigned char i;
	init_leds();
	while(1)
  	{
		P12 = 0; // disable LED
		for (i = 0; i < 250; i++){
			P02 = 0;
			P16 = 0;
			Timer0_Delay1ms(1);
			P02 = 1;
			P16 = 1;
			Timer0_Delay1ms(1);
		}
		P12 = 1; // enable LED
		for (i = 0; i < 250; i++){
			P02 = 0;
			P16 = 0;
			Timer0_Delay1ms(1);
			P02 = 1;
			P16 = 1;
			Timer0_Delay1ms(1);
		}
	}

}
#endif
#define LOOP_ITER 50

#define USE_EXTERNAL_CLOCK 1
#ifdef USE_EXTERNAL_CLOCK
#else
#ifdef FOSC_166000
void MODIFY_HIRC_166(void)				// Modify HIRC to 16.6MHz, more detail please see datasheet V1.02
{
		UINT8 hircmap0,hircmap1;
		UINT16 trimvalue16bit;
/* Check if power on reset, modify HIRC */
		if ((PCON&SET_BIT4)==SET_BIT4)				
		{
				hircmap0 = RCTRIM0;
				hircmap1 = RCTRIM1;
				trimvalue16bit = ((hircmap0<<1)+(hircmap1&0x01));
				trimvalue16bit = trimvalue16bit - 14;
				hircmap1 = trimvalue16bit&0x01;
				hircmap0 = trimvalue16bit>>1;
				TA=0XAA;
				TA=0X55;
				RCTRIM0 = hircmap0;
				TA=0XAA;
				TA=0X55;
				RCTRIM1 = hircmap1;
/* Clear power on flag */
				PCON &= CLR_BIT4;
		}
}
#endif // FOSC_166000
#endif // USE_EXTERNAL_CLOCK

void main_glitchloop()
{
	volatile UINT8 i, j;
	volatile UINT32 cnt;
	volatile UINT8  inner_count;
	volatile UINT32 busy = 2;
    UINT8 *cnt_ptr = (UINT8 *)&cnt;
	cnt = 0;
	while (1) 
	{

        cnt = 0;
        // block until we get a 'g' on the serial port
		
        while(getchar() != 'g');
		// led_ok(1);
		set_trigger(1);
        for(i = 0; i < LOOP_ITER; i++)
		{
			// led_ok(1);
            for(j = 0; j < LOOP_ITER; j++)
			{
				// led_error(1);
				// busy *= 3;
				// busy *= 3;
				// busy *= 3;
				inner_count++;
			
				// busy *= 3;
				// busy *= 3;
				// busy *= 3;
				// led_error(0);
            }
			cnt += inner_count;
			inner_count = 0;
			// led_ok(0);
        }
		// led_ok(0);
		set_trigger(0);
		Send_Data_To_UART0(i);
		Send_Data_To_UART0(j);
		Send_Data_To_UART0(cnt_ptr[0]);
        Send_Data_To_UART0(cnt_ptr[1]);
        Send_Data_To_UART0(cnt_ptr[2]);
        Send_Data_To_UART0(cnt_ptr[3]);
    }
}
void main(void) 
{	

#ifdef USE_EXTERNAL_CLOCK
	    set_EXTEN1;  
		set_EXTEN0;
		clr_OSC1;													//step3: switching system clock source if needed
		set_OSC0;
		clr_HIRCEN;
		set_CT_T0;													//Timer0 Clock source = OSCIN (external clock)
#else // ifndef USE_EXTERNAL_CLOCK
#ifdef FOSC_166000
	MODIFY_HIRC_166();
#endif
    // if external clock isn't enabled...
	P11_PUSHPULL_MODE;	// Set P1.1 to push-pull mode
	set_CLOEN;	// Enable clock out pin

#endif
	// set all pins to pushpull mode except trigger (P04), OSCIN (P3.0), and the serial UART lines (P06 and P07)
	P00_PUSHPULL_MODE;
	P01_PUSHPULL_MODE;
	P02_PUSHPULL_MODE;
	P03_PUSHPULL_MODE;
	P05_PUSHPULL_MODE;
	P10_PUSHPULL_MODE;
	P11_PUSHPULL_MODE;
	P12_PUSHPULL_MODE;
	P13_PUSHPULL_MODE;
	P14_PUSHPULL_MODE;
	P15_PUSHPULL_MODE;
	P16_PUSHPULL_MODE;
	P17_PUSHPULL_MODE;
	// set all pins high except trigger (P04), OSCIN (P3.0), and the serial UART lines (P06 and P07)
	P00 = 1;
	P01 = 1;
	P02 = 1;
	P03 = 1;
	P05 = 1;
	P10 = 1;
	P11 = 1;
	P12 = 1;
	P13 = 1;
	P14 = 1;
	P15 = 1;
	P16 = 1;
	P17 = 1;

	init_uart();
	trigger_setup();
	trigger_low();
	// set all leds on beccause init UART turned them off
	led_ok(1);
	led_error(1);
	main_glitchloop();

}
