"""Single-message IoTDA synthetic probe; Python standard library only.

Never disables certificate verification or prints authentication material.
References: Huawei iot_02_0203 (authentication), iot_06_v5_3010 (properties).
"""
import argparse
import hashlib
import hmac
import json
import socket
import ssl
import struct
from datetime import datetime, timezone
from pathlib import Path


def password(secret, timestamp):
    return hmac.new(timestamp.encode(), secret.encode(), hashlib.sha256).hexdigest()


def mqtt_string(value):
    data = value.encode()
    return struct.pack('!H', len(data)) + data


def packet(header, body):
    size = len(body)
    encoded = bytearray()
    while True:
        digit = size % 128
        size //= 128
        encoded.append(digit | (128 if size else 0))
        if not size:
            return bytes([header]) + bytes(encoded) + body


def read_exact(conn, length):
    result = bytearray()
    while len(result) < length:
        part = conn.recv(length - len(result))
        if not part:
            raise ConnectionError('Peer closed MQTT connection')
        result.extend(part)
    return bytes(result)


def read_packet(conn):
    header = read_exact(conn, 1)[0]
    length = 0
    for index in range(4):
        digit = read_exact(conn, 1)[0]
        length += (digit & 127) * 128 ** index
        if not digit & 128:
            if length > 65536:
                raise ValueError('Unexpectedly large MQTT packet')
            return header, read_exact(conn, length)
    raise ValueError('Malformed MQTT remaining length')


def probe(config, tls_only=False):
    host = config['host']
    if config.get('port', 8883) != 8883:
        raise ValueError('This probe requires MQTTS port 8883')
    if not tls_only and not config.get('device_secret', '').strip():
        raise ValueError('device_secret is empty; save the dedicated test secret locally first')
    context = ssl.create_default_context()
    with socket.create_connection((host, 8883), timeout=15) as raw:
        with context.wrap_socket(raw, server_hostname=host) as conn:
            result = {'tls_verified': True, 'tls_version': conn.version(),
                      'mqtt_authenticated': False, 'puback_received': False,
                      'platform_properties_verified': False,
                      'playback_confirmed': False}
            if tls_only:
                return result
            device_id = config['device_id']
            now = datetime.now(timezone.utc)
            stamp = now.strftime('%Y%m%d%H')
            client_id = f'{device_id}_0_1_{stamp}'
            body = (mqtt_string('MQTT') + bytes([4, 0xC2]) + struct.pack('!H', 30)
                    + mqtt_string(client_id) + mqtt_string(device_id)
                    + mqtt_string(password(config['device_secret'], stamp)))
            conn.sendall(packet(0x10, body))
            header, response = read_packet(conn)
            if header != 0x20 or len(response) != 2 or response[1] != 0:
                raise ConnectionError(f'MQTT authentication rejected (CONNACK={response.hex()})')
            result['mqtt_authenticated'] = True
            record_id = 'synthetic-' + now.strftime('%Y%m%dT%H%M%S%fZ')
            payload = {'services': [{'service_id': config.get('service_id', 'PhysicalExam'),
                        'properties': {'record_id': record_id,
                                       'measured_at': now.isoformat().replace('+00:00', 'Z'),
                                       'height_cm': 175.0,
                                       'weight_kg': 70.0}}]}
            topic = f'$oc/devices/{device_id}/sys/properties/report'
            conn.sendall(packet(0x32, mqtt_string(topic) + b'\x00\x01'
                                + json.dumps(payload).encode()))
            for _ in range(10):
                header, response = read_packet(conn)
                if header == 0x40 and response == b'\x00\x01':
                    result.update(puback_received=True, record_id=record_id,
                                  synthetic_height_cm=175.0, synthetic_weight_kg=70.0)
                    conn.sendall(b'\xe0\x00')
                    return result
            raise ConnectionError('No matching PUBACK; platform parsing is not confirmed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--tls-only', action='store_true')
    args = parser.parse_args()
    try:
        config = json.loads(args.config.read_text(encoding='utf-8-sig'))
        print(json.dumps(probe(config, args.tls_only), ensure_ascii=False))
    except (OSError, ValueError, KeyError, ConnectionError) as error:
        # Exceptions deliberately contain no secret/password/client packet.
        parser.exit(1, f'{type(error).__name__}: {error}\n')


if __name__ == '__main__':
    main()
