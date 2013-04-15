#!/usr/bin/python
# Markham Thomas   April 1, 2013
# Version 1.1      April 9, 2013   modified C library for non-SYSF GPIO setup
#
# OdroidX and X2 python module allowing memory mapped GPIO access
#
# This supports both pure python mmap of gpio and a C library that does mmap also
# for performance you can call the C version
import os, mmap, sys, time
from ctypes import *
from hkgpiolib import *

class Bunch(dict):
        def __init__(self, d = {}):
                dict.__init__(self, d)
                self.__dict__.update(d)
        def __setattr__(self, name, value):
                dict.__setitem__(self, name, value)
                object.__setattr__(self, name, value)
        def __setitem__(self, name, value):
                dict.__setitem__(self, name, value)
                object.__setattr__(self, name, value)
        def copy(self):
                return Bunch(dict.copy(self))

MAP_MASK = mmap.PAGESIZE - 1
gpio_addr =  0x11400000
OUTPUT = 1
INPUT  = 0
PULLDS = 0	# disable pullup/down
PULLUP = 1  # enable pullup
PULLDN = 2  # enable pull down
# When you do not use or connect port to an input pin without Pull-up/Pull-down then do not leave a port in Input Pull-up/Pull-down disable state. It may cause unexpected state and leakage current. Disable Pull-up/Pull-down when you use port as output function.
# ----
# GPF0DAT = 0x0184  - 4  = GPF0CON (0x0180)  byte0 = low nibble is either 0000=input or 0001=output hi-nibble same for next port
# this repeats for 4 GPIO registers up to 0x0183
# ----
# GPF0UPD = 0x0188 (4 registers controlled by 2 bits each: 00=pull-up/down disabled, 01=pull-down enabled, 10=pull-up enabled
# ----
# GPF0DRV = 0x018c (drive strength control register (2-bits each) 00=1x, 10=2x, 01=3x, 11=4x
# ----
# notes:  when using sysfs interface to set GPIO pin state you must delay 800 clocks before expecting the
# C library to be able to read a GPIO register, set one bit, and write it back out.  If you immediately
# read the value after setting one bit in the same register chip, the next bit set to the same GPIO chip
# will not see a previous bit if it was in the same GPIO chip without waiting those 800 clocks.
# ----

# maps the GPIO pin to the sysfs /sys/class/gpio/gpioXXX
gpio_sysfs = { 'pin17':112, 'pin18':115, 'pin19':93, 'pin20':100, 'pin21':108, 'pin22':91, 'pin23':90,
			   'pin24':99,  'pin25':111, 'pin26':103,'pin27':88,  'pin28':98,  'pin29':89, 'pin30':114,
			   'pin31':87,  'pin33':94,  'pin34':105,'pin35':97,  'pin36':102, 'pin37':107,'pin38':110,
			   'pin39':101, 'pin40':117, 'pin41':92, 'pin42':96,  'pin43':116, 'pin44':106,'pin45':109,}
# maps the GPIO pin to the memory mapped offset and bit
gpio_addresses = { 'pin17':[0x01c4,7], 'pin18':[0x01e4,1], 'pin19':[0x0184,6], 'pin20':[0x01a4,4],
				   'pin21':[0x01c4,3], 'pin22':[0x0184,4], 'pin23':[0x0184,3], 'pin24':[0x01a4,3],
				   'pin25':[0x01c4,6], 'pin26':[0x01a4,7], 'pin27':[0x0184,1], 'pin28':[0x01a4,2],
				   'pin29':[0x0184,2], 'pin30':[0x01e4,0], 'pin31':[0x0184,0], 'pin33':[0x0184,7],
				   'pin34':[0x01c4,0], 'pin35':[0x01a4,1], 'pin36':[0x01a4,6], 'pin37':[0x01c4,2],
				   'pin38':[0x01c4,5], 'pin39':[0x01a4,5], 'pin40':[0x01e4,3], 'pin41':[0x0184,5],
				   'pin42':[0x01a4,0], 'pin43':[0x01e4,2], 'pin44':[0x01c4,1], 'pin45':[0x01c4,4],
}

gpio = Bunch(gpio_addresses)	# GPIO register interface
gsys = Bunch(gpio_sysfs)		# sysfs interface

# pure python mmap setup code
def setup_fd():
	try:
		f = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
	except:
		print "Open of /dev/mem failed: ", sys.exc_info()[0]
		raise
	return f
def setup_mmap(f):
	try:
		m = mmap.mmap(f, mmap.PAGESIZE, mmap.MAP_SHARED, mmap.PROT_WRITE | mmap.PROT_READ, offset=gpio_addr & ~MAP_MASK)
	except:
		print "mmap of GPIO space failed: ", sys.exc_info()[0]
		raise
	return m
def read_offset(m, offset):
	m.seek(offset)
	a = m.read_byte()
	b = ord(a)
	return b
def read_gpio(m, pin):
	offset = pin[0]
	bit = pin[1]
	m.seek(offset)
	a = m.read_byte()
	b = ord(a)
	c = b >> bit
	c &= 1
	return c
def write_gpio(m, pin, value):
	offset = pin[0]
	bit = pin[1]
	m.seek(offset)
	a = m.read_byte()
	b = ord(a)
	#c = 0
	c = 1 << bit		# shift the 1 to the correct bit number
	if (value):			# if 1 do this
		b |= c			# set the bit in the GPIO byte without destorying the other bits	
	else:
		c ^= 0xff 		# xor the bits with ff to flip the 1 to zero and 0's to 1's
		b &= c			# clears the correct bit
	m.seek(offset)
	m.write_byte(str(b))
def cleanup(m):
	m.close()
def setup_gpio_pin(pin, direction):
	a = '/sys/class/gpio/gpio' + str(pin) + '/direction'
	try:
		open(a).read()
	except:
  		# it isn't, so export it
  		open('/sys/class/gpio/export', 'w').write(str(pin))
	open(a, 'w').write(direction)
def cleanup_gpio_pin(pin):
	open('/sys/class/gpio/unexport', 'w').write(str(pin))
def gpio_sysfs_setvalue(pin, value):
	# when writing a 1 it briefly drops to 0 for 100 usec (no idea why)
	a = '/sys/class/gpio/gpio' + str(pin) + '/value'
	try:
		open(a, 'w').write(str(value))
	except IOError:
		print "Cannot open:", a
		print "  Did you setup that pin?"
		sys.exit(-1)
	except:
		print "GPIO pin not setup (missing): /sys/class/gpio/gpio" + str(pin)
		sys.exit(-1)
def gpio_sysfs_getvalue(pin):
	a = '/sys/class/gpio/gpio' + str(pin) + '/value'
	try:
		b = open(a).read()
	except:
		print "GPIO pin not setup (missing): /sys/class/gpio/gpio" + str(pin)
		sys.exit(-1)
	return b
#-------- example code ---------
def python_mmap_example():
	# mmap the GPIO pins into local address space
	# this uses the python mmap interface instead of the C library
	# yeilds around 75khz
	setup_gpio_pin(gpio_sysfs['pin31'], "out")	# this pin powers the level translator low side
	setup_gpio_pin(gpio_sysfs['pin27'], "out")	# this pin gets toggled
	# note: i switch to using the Bunch class to have less typing for gpio_sysfs list
	gpio_sysfs_setvalue(gsys.pin31,1)			# power the level translator
	gpio_sysfs_setvalue(gsys.pin27,1)			# start the toggle pin high
	fd = setup_fd()
	mm = setup_mmap(fd)
	for i in range(500000):
		write_gpio(mm, gpio_addresses['pin27'], 0)
		write_gpio(mm, gpio_addresses['pin27'], 1)
	cleanup(mm)									# cleanup python mmap
def python_sysfs_example():						# pure sysfs interface (no mmap)
	# sysfs GPIO toggle test below yeilds 4.35khz
	setup_gpio_pin(gpio_sysfs['pin31'], "out")	# this pin powers the level translator low side
	setup_gpio_pin(gpio_sysfs['pin27'], "out")	# this pin gets toggled
	gpio_sysfs_setvalue(gsys.pin31,1)			# power the level translator
	gpio_sysfs_setvalue(gsys.pin27,1)			# start the toggle pin high
	for i in range(50000):
		gpio_sysfs_setvalue(gpio_sysfs['pin27'], 1)
		gpio_sysfs_setvalue(gpio_sysfs['pin27'], 0)
def c_mmap_example():							# pure C library access of GPIO registers
	# setup the GPIO pins for measuring with the logic analyzer
	# PULLDS disables pullup or pulldown (use those for input settings)
	setup_gpio()	# setup GPIO mmap in the C library
	setup_gpiopin(gpio.pin31[0],gpio.pin31[1], PULLDS, OUTPUT)	# this pin powers the level translator low side
	setup_gpiopin(gpio.pin27[0],gpio.pin27[1], PULLDS, OUTPUT)	# toggle this pin
	gpio_write(gpio.pin31[0],gpio.pin31[1],1) # initially high
	time.sleep(0.005)	# needed since GPIO state change doesn't update the mmap'd GPIO space for some clock cycles
	gpio_write(gpio.pin27[0],gpio.pin27[1],1) # initially high
	# note: 50000000 is about 22 seconds of toggling GPIO
	gpio_toggle(gpio.pin27[0],gpio.pin27[1], 25000000)		# gives 2.4mhz 
	gpio_shutdown()

# note this should now not require GPIO SYSFS be compiled in for the pure C library calls
# if you uncomment the others and try them they DO use SYSFS
c_mmap_example()			# uses the C library to toggle pin27
#python_sysfs_example()		# pure python sysfs interface to toggle bits
#python_mmap_example()		# uses mmap inside of python to improve performance
