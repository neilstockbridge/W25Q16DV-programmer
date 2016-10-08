#!/usr/bin/env python
#
# Interact with a W25Q16DV SPI flash chip
#
# Tested with the W25Q16DV on the iCE40HX1K-EVB.
#
# Wiring:
#
#   - #25   -> iCE40-CRESET  RPi GPIO 8 (Next to CE0)
#   - CE0   -> iCE40-SS_B
#   - SCLK  -> iCE40-SCK
#   - MOSI  -> iCE40-SDO
#   - MISO <-  iCE40-SDI
#
# RESET is straight through, SCLK via 100R, all others via 270R.  Higher values
# may work but 270R didn't work on SCLK.
#

import io
import sys
import W25Q16DV as flash


def dump (address, bytes_left_to_read, path_to_file):
  f = io.FileIO (path_to_file, 'w')
  buffer = bytearray ()
  while 0 < bytes_left_to_read:
    del buffer [:]
    bytes_to_read = min (256, bytes_left_to_read)
    bytes = flash.read (address, bytes_to_read)
    for b in bytes:
      buffer.append (b)
    address += bytes_to_read
    bytes_left_to_read -= bytes_to_read
    f.write (buffer)
  f.close ()


def upload (path_to_file, address):
  """
  `address` should be 256-byte page aligned otherwise the contents of each page
  will be rotated.
  """
  PAGE_SIZE = 256
  f = io.FileIO (path_to_file)
  buffer = bytearray (PAGE_SIZE)
  # Address of the beginning of the (4K) sector
  sector_address = -1
  while True:
    bytes_read = f.readinto (buffer)
    if bytes_read == 0: break
    # If only 200 bytes were read then don't flash the whole buffer, including
    # the garbage at the end
    a = [b for b in buffer]
    while bytes_read < len(a):
      a.pop()
    # A sector erase is required prior to page write although sectors are 4K in
    # size while pages are only 256 bytes in size
    sa = address & 0xfff000
    if sector_address < sa:
      print "Erasing 4K at 0x%06x"% sa
      flash.erase_4K (sa)
      sector_address = sa
    flash.page_program (a, address)
    #print address, bytes_read, len(a)
    address += PAGE_SIZE
  f.close ()


# FIXME: Proper command-line parsing, along with verify option and --dry-run option
def main ():
  cmd = sys.argv[1]
  flash.setup ()
  flash.power_up ()
  if cmd == "identify":
    flash.identify ()
  elif cmd == "erase":
    sector_id = int (sys.argv[2])
    flash.erase_4K (4096 * sector_id)
    #print "Erased 4K sector at 0x%x"% 4096 * sector_id
  elif cmd == "upload":
    # Use: upload my_project.bin
    #   ..to upload the contents of my_project.bin at address 0x0
    upload (sys.argv[2], 0)
  elif cmd == "dump":
    # Use: dump 8192 /tmp/ROM.bin
    #   ..to dump the first 8K of the flash to /tmp/ROM.bin
    dump (0, int(sys.argv[2]), sys.argv[3])
  else:
    print "Unrecognised command:", cmd
  #print "status:", flash.status()
  # If a write operation is in progress then wait for it to complete
  flash.wait_while_busy ()
  flash.wait_until_write_complete ()


main ()

