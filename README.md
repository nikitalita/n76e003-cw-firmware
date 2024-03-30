# N76E003 ChipWhisperer Firmware Testing

board: https://github.com/nikitalita/n76e003-ufo-target-board

programmer: https://github.com/nikitalita/NuMicro-8051-prog

firmware: https://github.com/nikitalita/chipwhisperer/tree/n76-wip-branch

## Usage:
- Build board
- Get chipwhisperer-lite with UFO board and CW Advanced Breakout
- Put jumpers on GPIO4 connect and 3.3v
- install chipwhisperer software package according to the instructions, but use my version of chipwhisperer on the `n76-wip-branch` branch instead:
```bash
git clone -b n76-wip-branch https://github.com/nikitalita/chipwhisperer
```
- clone and install the programmer software:
```bash
 git clone https://github.com/nikitalita/NuMicro-8051-prog
 pyenv shell cw
 pip install -e .
 ```
- then run `python run_ss_test.py`
