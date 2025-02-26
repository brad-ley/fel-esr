import telnetlib3, asyncio
import time
import getpass
from PyQt6.QtCore import pyqtSignal, QThread
# from constants import LASERS

HOST = "192.168.103.105"
PORT = "25"
MAC = "00:80:A3:6B:E4:1D"
LOGOUT = "$LOGOUT\n"
STANDBY = "$STANDBY\n"
STOP = "$STOP\n"

def login_command(MAC):
    return f"$LOGIN VR{MAC.replace(":","")[-6:]}\n"

async def send_receive(reader, writer, command):
    try:
        async with asyncio.timeout(3):
            writer.write(command)
            await writer.drain()
            resp = await reader.read(20)
            print(resp)
            return resp
    # except asyncio.TimeoutError:
    except IndexError:
        print("Could not connect to the laser")
        return reader, writer

async def create_reader_writer(host=HOST, port=PORT, mac=MAC):
    try:
        async with asyncio.timeout(3):
            reader, writer = await telnetlib3.open_connection(host=HOST, port=PORT, encoding="ascii")
            print("Initialized")
    # except (ConnectionRefusedError, asyncio.TimeoutError):
    except IndexError:
        print("Could not connect to the laser")
        return None, None
    return reader, writer
