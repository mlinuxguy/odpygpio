Run ./build_lib.sh to first build the C gpio library for Python
after that you can edit hkodgpio.py, jump to the bottom and uncomment the demo
you want to test.

NOTE:  you will need to change a #define in the C lib for the board you have and an
if statement in the python code.
(Default currently is:  odroidxu board)

To run just execute:  ./hkodgpio.py

This will toggle pin27
(note: I use pin31 to power the low side of my level translator)

NOTES:  You can now use this without GPIO SYSFS being compiled in.  I changed
the c library to now setup the GPIO registers directly without using SYSFS
