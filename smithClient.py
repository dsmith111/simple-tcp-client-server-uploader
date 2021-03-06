import socket
import random
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib import style
import time
import argparse
import serial


def getArgs():
    parser = argparse.ArgumentParser(description="IP and port for server")

    parser.add_argument("ip")
    parser.add_argument("port")
    parser.add_argument("targetIp")
    parser.add_argument("targetPort")
    parser.add_argument("type")
    parser.add_argument("message")

    return parser.parse_args()


def readImage(imagePath):
    with open(imagePath, "rb") as jpg:

        while True:
            image = jpg.read()
            break

    return image


def imageToBin(image):
    stringPacket = [f"{packByte:08b}" for packByte in image]
    return "".join(stringPacket)


def strToBin(msg: str):
    binRep = ""

    for character in msg:
        binRep += f"{(ord(character)):08b}"

    return binRep


def buildPacket(sync=0, ack=0, fin=0, seqNum=0, ackNum=0, payload=0, payloadSize=0, divisor="000000000"):
    flags = f"000{ack}00{sync}{fin}"
    stringPacket = flags + f"{seqNum:032b}" + f"{ackNum:032b}" + \
        f"{payloadSize:016b}" + f"{payload:01024b}"
    CRC = ""
    if int(divisor) > 0:
        CRC = getCRC(stringPacket, divisor)

    else:
        CRC = "00000000"
    stringPacket += CRC

    listPacket = np.array([val for val in stringPacket]).reshape(
        int(np.ceil(len(stringPacket)/8)), 8)
    intPacket = [int("".join(listByte), base=2) for listByte in listPacket]

    return intPacket


def getCRC(binCode, divisor):
    payload = list(binCode) + ([0]*(len(divisor)-1))
    payload = [int(n) for n in payload]
    divisor = [int(n) for n in list(divisor)]
    remainder = []
    pointer = 0

    while pointer <= len(payload) - len(divisor):
        # Extract slice to subtract
        val = payload[pointer: pointer + len(divisor)]

        # Subtract paired values
        operations = zip(val, divisor)
        remainder = [abs(op[0] - op[1]) for op in operations]

        # Modify payload values, set pointer to index
        for i in range(len(divisor)):
            payload[pointer + i] = remainder[i]

        # Move pointer to next non-zero value
        if 1 not in payload:
            return "0"*(len(divisor)-1)
        pointer = payload.index(1)

    return "".join([str(val) for val in payload[-(len(divisor) - 1):]])


def separateData(packet):
    stringPacket = [f"{packByte:08b}" for packByte in packet]
    flags = stringPacket[0]
    seqNum = int("".join(stringPacket[1:5]), base=2)
    ackNum = int("".join(stringPacket[5:9]), base=2)
    payloadSize = int("".join(stringPacket[9:11]), base=2)
    payload = "".join(stringPacket[11:-1])[-payloadSize:]
    return (flags, seqNum, ackNum, payload)


def decipherMessage(message):
    msgBytes = np.array([char for char in message]
                        ).reshape(int(len(message)/8), 8)
    letters = [chr(int("".join(msgByte), base=2)) for msgByte in msgBytes]
    return "".join(letters)


def decipherImage(message):
    msgBytes = [str(int(msg)) for msg in message]
    msgBytes = "".join(msgBytes)
    msgNum = int(msgBytes, base=2)
    hexNum = hex(msgNum)[2:]
    if len(hexNum) % 2 != 0:
        hexNum += "0"
    data = bytes.fromhex(hexNum)

    return data


def checkCRC(binCode, divisor):
    stringPacket = [f"{packByte:08b}" for packByte in binCode]
    payload = []
    for byteSection in stringPacket:
        payload += byteSection
    payload = [int(n) for n in payload]
    divisor = [int(n) for n in list(divisor)]
    remainder = []
    pointer = 0

    while pointer <= len(payload) - len(divisor):
        # Extract slice to subtract
        val = payload[pointer: pointer + len(divisor)]

        # Subtract paired values
        operations = zip(val, divisor)
        remainder = [abs(op[0] - op[1]) for op in operations]

        # Modify payload values, set pointer to index
        for i in range(len(divisor)):
            payload[pointer + i] = remainder[i]

        # Move pointer to next non-zero value
        if 1 not in payload:
            return 0
        pointer = payload.index(1)

    return "".join([str(val) for val in payload[-(len(divisor) - 1):]])


def runServer(ip, port, targetIP, targetPort, type, message):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        print("Attempting to connect")
        try:
            s.bind((ip, int(port)))
            print("Bound")
            s.connect((targetIP, int(targetPort)))
            print("Connected")
            cntRestrict = 500
            ser = None
            if type == "message":
                msgBin = strToBin(message)
                msgLength = len(msgBin)
            elif type == "serial":
                msgBin = strToBin(message)
                msgLength = 2**14
                ser = serial.Serial("COM7", 9600)
                cntRestrict = 99

            else:
                msgBin = imageToBin(readImage(message))
                msgLength = len(msgBin)

            # Define some packet info
            seqNum = 0
            ackNum = 0
            divisor = '100000111'

            print(f"Connected to {targetIP}:{targetPort}")

            # Handshake
            # - Send Sync Request
            syncPacket = bytes(buildPacket(sync=1))
            sent = s.send(syncPacket)

            # - Receive Sync Ack
            ackPacket = s.recv(2048)
            flags, otherSeq, otherAck, otherPayload = separateData(ackPacket)
            ackNum = otherAck
            print("Server Acknowledged: ", otherAck)

            # - Send Sync Ack
            ackPacket = bytes(buildPacket(ack=1, ackNum=ackNum, seqNum=seqNum))
            seqNum += 1
            payloadSent = 0
            sent = s.send(ackPacket)
            cnt = 1

            while True:

                # Send Data
                print("sending payload")
                if type == "serial":
                    tempLength = 0
                    while tempLength < 5:
                        line = ser.readline().decode() + "\n"
                        tempLength = len(line)
                        msgBin = strToBin(line)
                        payloadSent = 0

                payloadSlice = msgBin[payloadSent: payloadSent + 1024]
                if len(payloadSlice):
                    payloadPiece = bytes(buildPacket(ackNum=ackNum, seqNum=seqNum, payloadSize=len(
                        payloadSlice), payload=int(payloadSlice, base=2), divisor=divisor))
                else:
                    payloadPiece = bytes(buildPacket(
                        ackNum=ackNum, seqNum=seqNum, divisor=divisor))

                ttr = time.monotonic()
                sent = s.send(payloadPiece)

                # Wait for acknowledgement
                print("waiting for ack")
                resp = s.recv(2048)
                ttr = time.monotonic() - ttr

                flags, otherSeq, otherAck, otherPayload = separateData(resp)

                if otherAck == seqNum + len(payloadPiece):
                    print("Sequence Num", seqNum, "-->",
                          seqNum + len(payloadPiece))
                    seqNum += len(payloadPiece)
                    payloadSent += 1024

                else:
                    print("Faulty checksum")
                    print(checkCRC(payloadPiece, divisor))

                if seqNum >= msgLength + (98 * cnt) or cnt > cntRestrict:
                    print("Finished sending data")
                    s.send(bytes(buildPacket(fin=1, divisor=divisor)))
                    s.close()
                    # ser and ser.close()
                    break

                cnt += 1

                # time.sleep(3)
                lF = open("latency.txt", "a")
                lF.write(f"{cnt},{ttr}\n")
                lF.close()

        except Exception as error:
            s.close()
            # ser and ser.close()
            raise error


if __name__ == "__main__":
    args = getArgs()
    # Logs
    latencyFile = open("latency.txt", "w").close()
    runServer(args.ip, args.port, args.targetIp,
              args.targetPort, args.type, args.message)
