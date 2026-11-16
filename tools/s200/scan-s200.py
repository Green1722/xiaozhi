import asyncio, json, re
from s200_config import PRIVATE
from bleak import BleakScanner
import bleak.backends.winrt.scanner as winrt
import sys
from Crypto.Cipher import AES

async def main():
    cfg = dict(re.findall(r'^(\w+): "([^"]+)"$', (PRIVATE / 'secrets.yaml').read_text(encoding='utf-8-sig').strip(), re.M))
    mac = cfg['s200_mac'].upper()
    key = bytes.fromhex(cfg['s200_bindkey'])
    from collections import Counter
    formats = Counter()
    seen = set()
    first_weight = asyncio.get_running_loop().create_future()
    observed = dict(scale=0, encrypted=0, authenticated=0, weight=0)
    def receive(device, adv):
        if device.address.upper() != mac:
            return
        observed['scale'] += 1
        for uuid, frame in adv.service_data.items():
            formats[(uuid[:8], len(frame), hex(frame[0] & 0x58) if frame else None)] += 1
            if not uuid.lower().startswith('0000fe95-') or len(frame) < 12 or frame[0] & 0x48 != 0x48:
                continue
            address = bytes.fromhex(mac.replace(':',''))[::-1]
            start = 5
            if frame[0] & 0x10:
                if frame[5:11] != address:
                    continue
                start += 6
            if frame[0] & 0x20:
                continue
            if len(frame) <= start + 7:
                continue
            observed['encrypted'] += 1
            nonce = address + frame[2:5] + frame[-7:-4]
            cipher = AES.new(key, AES.MODE_CCM, nonce=nonce, mac_len=4)
            cipher.update(b'\x11')
            try:
                value = cipher.decrypt_and_verify(frame[start:-7], frame[-4:])
            except ValueError:
                continue
            observed['authenticated'] += 1
            if value[:3] == b'\x16\x4e\x09' and any(value[4:8]) and frame not in seen:
                seen.add(frame)
                observed['weight'] += 1
                from datetime import datetime, timezone
                weight = int.from_bytes(value[4:8], 'little') / 100
                row = {'weight_kg': weight, 'received_at_utc': datetime.now(timezone.utc).isoformat()}
                if not first_weight.done():
                    first_weight.set_result(row)
                with (PRIVATE / 's200-readings.private.jsonl').open('a', encoding='utf-8') as out:
                    out.write(json.dumps(row) + '\n')
                print('Authenticated S200 weight frame', observed['weight'], flush=True)
                if '--show-local' in sys.argv:
                    print(f'S200: {weight:.2f} kg', flush=True)
    if "--coded" in sys.argv:
        watcher_factory = winrt.BluetoothLEAdvertisementWatcher
        def enable_coded():
            watcher = watcher_factory()
            watcher.allow_extended_advertisements = True
            watcher.use_coded_phy = True
            return watcher
        winrt.BluetoothLEAdvertisementWatcher = enable_coded
    async with BleakScanner(receive, scanning_mode="passive"):
        print('Scanning', flush=True)
        if "--capture-json" in sys.argv:
            row = await asyncio.wait_for(first_weight, timeout=60)
            print(json.dumps(row), flush=True)
            return
        for _ in range(12):
            await asyncio.sleep(5)
            if observed['weight'] >= 2:
                break
    print(observed)
    print('Service frame formats:', dict(formats))
asyncio.run(main())
