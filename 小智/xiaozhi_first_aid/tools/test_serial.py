import serial
import serial.tools.list_ports

port_name = 'COM3'
baudrate = 115200

try:
    print(f'Opening {port_name} @ {baudrate}...')
    ser = serial.Serial(port_name, baudrate, timeout=1)
    print(f'Successfully opened {port_name}!')

    print('Waiting for data...')
    for i in range(3):
        line = ser.readline()
        if line:
            text = line.decode('utf-8', errors='ignore').strip()
            print(f'Received: {text}')
        else:
            print(f'[{i+1}] No data')

    ser.close()
    print('Serial port closed')
except serial.SerialException as e:
    print(f'Failed to open: {e}')
except Exception as e:
    print(f'Error: {e}')
