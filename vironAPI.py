import telnetlib3, asyncio
import time
import getpass

HOST = "192.168.103.105"
PORT = 25
MAC = "0080A36BE41D"
LOGOUT = "$LOGOUT\n"
STANDBY = "$STANDBY\n"
STOP = "$STOP\n"

def login_command(MAC):
    return f"$LOGIN VR{MAC[-6:]}\n"

async def send_receive(reader, writer, command):
    writer.write(command)
    resp = await reader.read(1024)
    return resp

async def initialize(host=HOST, port=PORT, mac=MAC):
    try:
        reader, writer = await telnetlib3.open_connection(host=HOST, port=PORT, encoding="ascii")
        print(await send_receive(reader, writer, login_command(MAC)))
    except:
        raise Exception("Could not connect to the laser")
    return reader, writer

async def communicate(host=HOST, port=PORT, mac=MAC):
    try:
        reader, writer = await initialize(HOST, PORT, MAC)
        print(await send_receive(reader, writer, login_command(MAC)))
        time.sleep(5)
        print(await send_receive(reader, writer, STANDBY))
        time.sleep(5)
        print(await send_receive(reader, writer, STOP))
        print(await send_receive(reader, writer, LOGOUT))
    except:
        pass
    finally:
        writer.close()

asyncio.run(communicate())