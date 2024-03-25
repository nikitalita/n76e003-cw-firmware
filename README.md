# N76E003 ChipWhisperer Firmware

board: https://github.com/nikitalita/n76e003-ufo-target-board
programmer: https://github.com/nikitalita/NuMicro-8051-prog

## Usage:
- Build board
- Get chipwhisperer with UFO board and CW Advanced Breakout
- Put jumpers on GPIO4 connect and 2.5v
- install chipwhisperer software package
- install sdcc
- `pyenv shell cw`
- install NuMicro-8051-prog: `pip install -e .` in the cloned repo
- then run `python run_ss_test.py`
