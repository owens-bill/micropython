#!/usr/bin/env python

"""
The WiPy firmware update script. Transmits the specified firmware file over FTP
and then resets the WiPy.

Usage:

    ./update-wipy.py --file "path_to_mcuimg.bin" --verify

Or:

    python update-wipy.py --file "path_to_mcuimg.bin"
"""

import sys
import argparse
import time
from ftplib import FTP
from telnetlib import Telnet


def print_exception(e):
    print ('Exception: {}, on line {}'.format(e, sys.exc_info()[-1].tb_lineno))


def transfer_file(args):
    with FTP(args.ip, timeout=10) as ftp:
        print ('FTP connection established')

        if '230' in ftp.login(args.user, args.password):
            print ('Login successful')

            if '250' in ftp.cwd('/flash/sys'):
                print ("Entered '/flash/sys' directory")

                with open(args.file, "rb") as fwfile:
                    print ('Firmware image found, initiating transfer...')

                    if '226' in ftp.storbinary("STOR " + 'mcuimg.bin', fwfile, 512):
                        print ('File transfer complete')
                        return True
                    else:
                        print ('Error: file transfer failed')
            else:
                print ('Error: cannot enter /flash/sys directory')
        else:
            print ('Error: ftp login failed')

    return False


def reset_board(args):
    success = False

    try:
        tn = Telnet(args.ip, timeout=5)
        print("Connected via Telnet, trying to login now")

        if b'Login as:' in tn.read_until(b"Login as:", timeout=5):
            tn.write(bytes(args.user, 'ascii') + b"\r\n")

            if b'Password:' in tn.read_until(b"Password:", timeout=5):
                # needed because of internal implementation details of the WiPy's telnet server
                time.sleep(1)
                tn.write(bytes(args.password, 'ascii') + b"\r\n")

                if b'Type "help()" for more information.' in tn.read_until(b'Type "help()" for more information.', timeout=5):
                    print("Telnet login succeeded")
                    tn.write(b'\r\x03\x03') # ctrl-C twice: interrupt any running program
                    time.sleep(1)
                    tn.write(b'\r\x02') # ctrl-B: enter friendly REPL
                    if b'Type "help()" for more information.' in tn.read_until(b'Type "help()" for more information.', timeout=5):
                        tn.write(b"import pyb\r\n")
                        tn.write(b"pyb.reset()\r\n")
                        time.sleep(1)
                        print("Reset performed")
                        success = True
                    else:
                        print("Error: cannot enter friendly REPL")
                else:
                    print("Error: telnet login failed")

    except Exception as e:
        print_exception(e)
    finally:
        try:
            tn.close()
        except Exception as e:
            pass
        return success


def verify_update(args):

    success = False
    firmware_tag = ''

    def find_tag (tag):
        nonlocal success, firmware_tag
        if tag in firmware_tag:
            success = True
            print("Verification passed")
        else:
            print("Error: verification failed, the git tag doesn't match")

    try:
        # Specify a longer time out value because the board has just been reset
        # and the wireless connection might not be fully established yet
        tn = Telnet(args.ip, timeout=15)
        print("Connected via telnet again, lets check the git tag")

        firmware_tag = tn.read_until (b'with CC3200')
        tag_file_path = args.file.rstrip('mcuimg.bin') + 'genhdr/mpversion.h'
        
        if args.tag is not None:
            find_tag(bytes(args.tag, 'ascii'))
        else:
            with open(tag_file_path) as tag_file:
                for line in tag_file:
                    bline = bytes(line, 'ascii')
                    if b'MICROPY_GIT_HASH' in bline:
                        bline = bline.lstrip(b'#define MICROPY_GIT_HASH ').replace(b'"', b'').replace(b'\r', b'').replace(b'\n', b'')
                        find_tag(bline)
                        break

    except Exception as e:
        print_exception(e)
    finally:
        try:
            tn.close()
        except Exception as e:
            pass
        return success


def main():
    cmd_parser = argparse.ArgumentParser(description='Update the WiPy firmware with the specified image file')
    cmd_parser.add_argument('-f', '--file', default=None, help='the path of the firmware file')
    cmd_parser.add_argument('-u', '--user', default='micro', help='the username')
    cmd_parser.add_argument('-p', '--password', default='python', help='the login password')
    cmd_parser.add_argument('--ip', default='192.168.1.1', help='the ip address of the WiPy')
    cmd_parser.add_argument('--verify', action='store_true', help='verify that the update succeded')
    cmd_parser.add_argument('-t', '--tag', default=None, help='git tag of the firmware image')
    args = cmd_parser.parse_args()

    result = 1

    try:
        if args.file is None:
            raise ValueError('the image file path must be specified')
        if transfer_file(args):
            if reset_board(args):
                if args.verify:
                    print ('Waiting for the WiFi connection to come up again...')
                    # this time is to allow the system's wireless network card to connect to the
                    # WiPy again. Sometimes it might only take a couple of seconds, but let's
                    # leave 10s to be on the safe side
                    time.sleep(10)
                    if verify_update(args):
                        result = 0
                else:
                    result = 0

    except Exception as e:
        print_exception(e)
    finally:
        sys.exit(result)


if __name__ == "__main__":
    main()
