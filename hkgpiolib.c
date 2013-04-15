// Markham Thomas April 1, 2013
// version 1.0
// version 1.1    April 9, 2013 - using mmap to setup GPIO
// note: I have not implemented drive strength access yet
//  the default appears to be 1 which should be the lowest mA setting
// Python library for odroid-x and x2 boards from hardkernel
// implements mmap'd GPIO address space for performance
#include <Python.h>
#include <stdio.h>
#include <stdlib.h>
#include <assert.h>
#include <unistd.h>
#include <errno.h>
#include <fcntl.h>
#include <sys/mman.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <signal.h>
#include "exceptions.h"

#define EXYNOS4_PA_GPIO1                0x11400000
#define GPIO_GPCONREG		4		// subtract 4 from DATA register base to get CON reg
#define GPIO_UPDOWN			4		// add 4 to DATA register base to get UPD register
#define GPIO_DRIVESTR		8		// add 8 to DATA register base to get drive str control reg
// example:  GPF0CON = 0x0180 low/high nibbles are either 0000=input, 0001=output
// GPF0DAT = 0x0184  data bits for input or output
// GPF0UPD = 0x0188  every 2 bits is a GPIO pin 00=up/down disabled, 01=pull down, 10=pull up
// GPF0DRV = 0x018c  drive str control reg (2-bits each pin) 00=1x, 10=2x, 01=3x, 11=4x

#define PULLDS 0					// disable pullup/down
#define PULLUP 1					// enable pullup
#define PULLDN 2					// enable pulldown

#define MAP_SIZE 4096UL
#define MAP_MASK (MAP_SIZE - 1)

static PyObject* gpioerror;		// new exception for this GPIO module
void *map_base, *virt_addr;
int fd;

// setup the mmap of the GPIO pins,  this should be called before anything else
static PyObject* py_setup_gpio(PyObject* self, PyObject* args) {

    off_t target = EXYNOS4_PA_GPIO1;
 
    if((fd = open("/dev/mem", O_RDWR | O_SYNC)) == -1) {
        PyErr_SetString(SetupException, "/dev/mem could not be opened");
		return NULL;
    } 
    /* Map one page */
    map_base = mmap(0, MAP_SIZE, PROT_READ | PROT_WRITE, MAP_SHARED, fd, target & ~MAP_MASK);
    if(map_base == (void *) -1) {
        PyErr_SetString(SetupException, "Memory map failed");
		return NULL;
    } 
	Py_INCREF(Py_None);
	return Py_None;
}

// configure a single GPIO pin: pullup/down and input or output is currently set here
// it does NOT use the SYSFS interface but directly accesses the GPIO control registers
static PyObject* py_setup_gpiopin(PyObject* self, PyObject* args) {
	int channel, bit, value, pullval;
	div_t div_res;
	unsigned char val, tmp, hld;
	unsigned char * base;
	if (!PyArg_ParseTuple(args, "iiii", &channel, &bit, &pullval, &value)) return NULL;
	base = (map_base + channel) - GPIO_GPCONREG;
	div_res = div (bit, 2);		// 2 nibbles per byte so divide by 2
	base += div_res.quot;
	val  = *(unsigned char *) base;
	if (value) {				// non-zero means set 0001=output
		if (div_res.rem) {		// if remainder then its upper nibble
			val &= 0b00011111;	// upper nibble, not always def to zero
			val |= 0b00010000;	// set upper nibble as output
		} else {				// otherwise its lower nibble
			val &= 0b11110001;	// not always def to zero on boot
			val |= 0b00000001;	// set lower nibble as output
		}
	} else {					// otherwise set 0000=input
		if (div_res.rem) {		// if remainder then its upper nibble
			val &= 0b00001111;	// clear upper nibble to be input
		} else {				// otherwise its lower nibble
			val &= 0b11110000;	// clear lower nibble to be input
		}
	}				
	*(unsigned char *) base = val;	
	base = (map_base + channel) + GPIO_UPDOWN;
	if      (pullval == PULLUP) {
		tmp = 0b00000010;		// pullup enabled
	}
	else if (pullval == PULLDN) {
		tmp = 0b00000001;		// pulldown enabled
	} 
	else {
		tmp = 0;				// disable pullup/down
	}
	if (bit < 4) {
		hld = tmp << (bit*2);	// shift the 2 bits to their proper location
	} else {
		bit = bit - 4;
		hld = tmp << (bit*2);	// shift the 2 bits to their proper location
		base++;					// move up to next byte
	}
	val = *(unsigned char *) base;
	//printf("curr value=0x%02x\n", val);
	val |= hld;
	//printf("set value=0x%02x\n", val);
	//printf("base=0x%8x\n",(unsigned int) base);
	Py_INCREF(Py_None);
	return Py_None;
}

// read a GPIO pin that was previously setup as INPUT
static PyObject* py_gpio_read(PyObject* self, PyObject* args) {
	int input, channel, bit;
	PyObject *value;
	if (!PyArg_ParseTuple(args, "ii", &channel, &bit)) return NULL;
	input = *(unsigned char *) (map_base + channel);
	if (input & (1 << bit)) {
		value = Py_BuildValue("i", 1);
	} else {
		value = Py_BuildValue("i", 0);
	}
	return value;
}

// Note: expect it to take around 800 clocks after setting a output bit for it to show
// up when you read the bits from that GPIO register again
static PyObject* py_gpio_write(PyObject* self, PyObject* args) {
	int output, channel, bit;
	int tmp, tmp1;
	unsigned char val;
	if (!PyArg_ParseTuple(args, "iii", &channel, &bit, &output)) return NULL;
	virt_addr = map_base + channel;			// offset of the GPIO
	val = *(unsigned char *) virt_addr;		// get the current bits
	if (output) {
		val |=  (1 << bit);					// set the bit
	} else {
		val &= ~(1 << bit);					// clear the bit
	}
	*(unsigned char *) virt_addr = val;		// write the newly set bit out
	Py_INCREF(Py_None);
	return Py_None;
}
 
// toggle count number of GPIO pin transitions
static PyObject* py_gpio_toggle(PyObject* self, PyObject* args) {
	int count, channel, bit;
	int val, vbl, vcl, sbit, x, y;
	if (!PyArg_ParseTuple(args, "iii", &channel, &bit, &count)) return NULL;
	virt_addr = map_base + channel;			// offset of the GPIO
	val = *(unsigned char *) virt_addr;		// get the current bits
	sbit = 1 << bit;						// our bit to toggle
	sbit &= 0xff;
	vbl = val ^ sbit;						// toggle the bit
	vcl = vbl ^ sbit;						// toggle the bit
	for (x=0;x<count;x++) {
		//val ^= sbit;						// toggle the bit
		*(unsigned char *) virt_addr = vbl;	// write the newly changed bit out
		*(unsigned char *) virt_addr = vcl;	// write the newly changed bit out
		//for (y=0;y<10;y++) {}
	}
	Py_INCREF(Py_None);
	return Py_None;
}

// Just a placeholder for testing Python <--> C access
static PyObject* py_gpio_test(PyObject* self, PyObject* args) {
	PyObject *value;
	value = Py_BuildValue("s", "This string is from C");
	return value;
}

// The last thing to call when exiting your program, cleans up the mmap
static PyObject* py_gpio_shutdown(PyObject* self, PyObject* args) {
	if(munmap(map_base, MAP_SIZE) == -1) {
        PyErr_SetString(gpioerror, "Memory unmap failed");	
    }
    close(fd);
	Py_INCREF(Py_None);
	return Py_None;
}

static PyMethodDef gpioMethods[] = {
    {"setup_gpio",    py_setup_gpio,   METH_VARARGS},
    {"setup_gpiopin", py_setup_gpiopin,METH_VARARGS},
	{"gpio_write",    py_gpio_write,   METH_VARARGS},
	{"gpio_read" ,    py_gpio_read,    METH_VARARGS},
	{"gpio_test" ,    py_gpio_test,    METH_VARARGS},
	{"gpio_toggle",   py_gpio_toggle,  METH_VARARGS},
	{"gpio_shutdown", py_gpio_shutdown,METH_VARARGS},
    {NULL, NULL, 0, NULL}        /* Sentinel */
};

void inithkgpiolib()
{
	(void) Py_InitModule("hkgpiolib", gpioMethods);
}
