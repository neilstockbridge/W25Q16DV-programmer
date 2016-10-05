#
# See: http://www.winbond.com/resource-files/w25q16dv_revi_nov1714_web.pdf
#
# Options:
#
#   1)  Require that calling code check status().BUSY is False before making
#       requests.  Perhaps raise an exception if status().BUSY is True
#
#   2)  Make all write operations synchronous (status().BUSY is False before
#       they return)
#
#   3)  Make all operations block waiting for status().BUSY to be False
#
# I have chosen 3) to allow for asynchronous operations while reducing the
# complexity of the calling code and likelihood that operations are ignored.
#

import time
import atexit
import RPi.GPIO as GPIO
import spidev
import js


SPI_TRACE = False
#SPI_TRACE = True
RESET_LINE = 25 # GPIO 8


def to_s (list):
  return ", ".join (["%02x"% i for i in list])


spi = None


def setup ():
  atexit.register (tidy_up)

  GPIO.setmode (GPIO.BCM)
  GPIO.setwarnings (False)
  GPIO.setup (RESET_LINE, GPIO.OUT)
  GPIO.output (RESET_LINE, GPIO.HIGH)
  time.sleep (0.5)
  GPIO.output (RESET_LINE, GPIO.LOW)
  time.sleep (0.5)

  global  spi
  spi = spidev.SpiDev ()
  spi.open (0, 0)
  #spi.max_speed_hz = 1 * 1000 * 1000
  spi.mode = 0


def tidy_up ():
  GPIO.output (RESET_LINE, GPIO.HIGH)
  GPIO.cleanup ()


READ_DATA =                   0x03
FAST_READ =                   0x0b
READ_STATUS_REGISTER_1 =      0x05
READ_STATUS_REGISTER_2 =      0x35
MANUFACTURER_AND_DEVICE_IDS = 0x90
JEDEC_ID =                    0x9f
READ_UNIQUE_ID =              0x4b
RELEASE_POWER_DOWN =          0xab
POWER_DOWN =                  0xb9
ENABLE_RESET =                0x66
RESET =                       0x99
WRITE_ENABLE =                0x06
SECTOR_ERASE =                0x20
PAGE_PROGRAM =                0x02

DONT_CARE =                   0xff


def address_bytes (address):
  return [(address >> os) & 0xff for os in [16, 8, 0]]


def wait_while (condition):
  # Timing is not accurate, but that's not very important
  time_waited = 0
  period = 1000 if SPI_TRACE else 1
  while condition():
    time.sleep (period / 1000.0)
    time_waited += period
    if 2000 <= time_waited:
      raise Exception ("Timed out waiting")
  return time_waited


def wait_while_busy ():
  return wait_while (lambda: status().BUSY)


def wait_until_write_complete ():
  return wait_while (lambda: status().WEL)


def wait_until_ready_for_write ():
  return wait_while (lambda: not status().WEL)


def ansi (color):
  return "\033[3%sm"% color


def request (request):
  if SPI_TRACE:
    print "%s>%s%s"% (ansi (5), to_s (request), ansi (9))

  should_check_busy = request[0] not in [RELEASE_POWER_DOWN, READ_STATUS_REGISTER_1, READ_STATUS_REGISTER_2, ENABLE_RESET, RESET]
  if should_check_busy:
    time_waited = wait_while_busy ()
    if 0 < time_waited:
      print "Waited %i ms while busy"% time_waited

  response = spi.xfer2 (request)
  # Ignore the first byte since the slave cannot possibly have had anything
  # interesting to say before it received the command byte
  response = response[1:]
  if SPI_TRACE:
    print "%s<%s%s"% (ansi (6), to_s (response), ansi (9))

  if request == [WRITE_ENABLE]:
    time_waited = wait_until_ready_for_write ()
    if 0 < time_waited:
      print "Waited %i ms for WEL=1"% time_waited

  return response


def power_up ():
  request ([RELEASE_POWER_DOWN])


def status ():
  response = request ([READ_STATUS_REGISTER_1, DONT_CARE])
  s = response [0]
  def bv (bit_position):
    return 0 < (s & (1 << bit_position))
  return js.JsObject (BUSY= bv (0), WEL= bv (1))


def identify ():

  def el (label, expected_value, value):
    addendum = "  (Expected %02x)"% expected_value if value is not expected_value else ""
    print "%s: %02x%s"% (label, value, addendum)

  response = request ([RELEASE_POWER_DOWN] + [DONT_CARE]*4)
  device_id = response [3]
  el ("Device ID", 0x14, device_id)

  response = request ([MANUFACTURER_AND_DEVICE_IDS, DONT_CARE, DONT_CARE, 0x00, DONT_CARE, DONT_CARE])
  manufacturer_id, device_id = response[3:]
  el ("Manufacturer ID", 0xef, manufacturer_id)
  el ("Device ID", 0x14, device_id)

  response = request ([JEDEC_ID] + [DONT_CARE]*3)
  manufacturer_id, memory_type, capacity = response
  print "JEDEC ID:"
  el ("  Manufacturer ID", 0xef, manufacturer_id)
  el ("  Memory Type", 0x40, memory_type)
  el ("  Capacity", 0x15, memory_type)

  response = request ([READ_UNIQUE_ID] + [DONT_CARE]*(4+8))
  unique_id = ":".join ("%02x"% v for v in response[4:])
  print "Unique ID:", unique_id


def read (address, count):
  #return request ([READ_DATA, a2, a1, a0] + [DONT_CARE]*count)[3:]
  # FAST_READ allows 80/104 MHz SCK as opposed to 50 MHz max. for READ_DATA
  return request ([FAST_READ] + address_bytes (address) + [DONT_CARE] + [DONT_CARE]*count)[4:]


def erase_4K (address):
  """Asynchronous.  Finished when status().BUSY is False.
  Further commands will block.
  address is byte-granular address, not 4K sector index, so an address of 1
  will erase "sector" 0.  Invoke as erase_4K (4096*sector_index).
  """
  request ([WRITE_ENABLE])
  # Seems to block forever.  WEL seems to be 1 *while* the erase is in
  # progress, in constrast to what the data sheet says: "A Write Enable
  # instruction must be executed before the device will accept the Sector Erase
  # instruction (Status Register bit WEL must equal 1)"
  #wait_until_ready_for_write ()
  request ([SECTOR_ERASE] + address_bytes (address))


def page_program (data, address):
  """the 8 LSB of address should be zero because the chip will not cross (256 byte) pages in the same operation.
  "data" is an array of bytes
  """
  request ([WRITE_ENABLE])
  request ([PAGE_PROGRAM] + address_bytes (address) + data)

