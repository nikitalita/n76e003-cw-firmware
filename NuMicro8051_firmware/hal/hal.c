
#include <stdint.h>
#include "numicro_8051.h"
#include "Common.h"
#include "Delay.h"
#include "clock.h"
#include "isp_uart0.h"

// NOTE: When using FOSC_160000, the actual baud rate as processed will be closer to 111111 (see N76E003 datasheet, section 13.5). 
// The `target.baud` setting must be set to account for this
#define BAUD_RATE 115200

int putchar(int c)
{
    Send_Data_To_UART0(c);
    return c;
}

int getchar(void)
{
    int c;
    while (!RI)
        ;
    c = SBUF;
    RI = 0;
    return (c);
}

void init_uart(void)
{
    // setting pushpull mode for LED1, LED2, and LED3 because they sometimes do not have enough voltage
    P03_PUSHPULL_MODE;
    P12_PUSHPULL_MODE;
    P05_PUSHPULL_MODE;

    // set LED 1 to on
    P03 = 1;
    P12 = 0;
    P05 = 0;

    InitialUART0_Timer3(BAUD_RATE);
}

void putch(char c)
{
    putchar(c);
}
char getch(void)
{
    return (char)getchar();
}

void trigger_setup(void)
{
    P04 = 0;
    P04_QUASI_MODE;
}

void trigger_low(void)
{
    P04 = 0;
}
void trigger_high(void)
{
    P04 = 1;
}

void platform_init(void)
{
#if USE_EXTERNAL_CLOCK
    use_external_clock();
#else // use internal clock
    use_internal_clock();
    enable_output_clock();
#endif
    set_BODCON1_LPBOD1; // set BOD to only turn on every 25 ms
    set_BODCON1_LPBOD0; // set BOD to only turn on every 25 ms
    clr_BODCON0_BODEN;  // disable brown-out detector
    clr_IE_EBOD;        // disable brown-out detector interrupt
    clr_BODCON0_BORST;  // disable brown-out reset
}

// void led_error(unsigned int status){
//     P05 = status;

// }
// void led_ok(unsigned int status){
//     P12 = status;
// }
