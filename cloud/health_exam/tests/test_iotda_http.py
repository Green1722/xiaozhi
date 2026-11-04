"""Real loopback HTTP + process restart; no cloud credentials or hardware."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import httpx

from cloud.health_exam.tests.test_iotda_forward import (
    BINDINGS, FORWARD_KEY, HEADERS, READ_HEADERS, READ_KEY, sample,
)


def test_real_http_forwarding_and_restart(tmp_path):
    root = Path(__file__).resolve().parents[3]
    env = dict(os.environ, HEALTH_API_KEY=READ_KEY, IOTDA_FORWARD_KEY=FORWARD_KEY,
               IOTDA_DEVICES_JSON=json.dumps(BINDINGS),
               DATABASE_URL='sqlite:///' + (tmp_path / 'exams.db').as_posix())
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1', 0))
        port = reservation.getsockname()[1]
    base = f'http://127.0.0.1:{port}'
    with (tmp_path / 'server.log').open('w') as log:
        def start():
            process = subprocess.Popen([sys.executable, '-m', 'uvicorn',
                'cloud.health_exam.app:create_app', '--factory', '--host', '127.0.0.1',
                '--port', str(port)], cwd=root, env=env, stdout=log, stderr=log)
            for _ in range(100):
                try:
                    if httpx.get(base + '/healthz', timeout=.3).status_code == 200:
                        return process
                except httpx.HTTPError:
                    pass
                if process.poll() is not None:
                    raise AssertionError('Server exited; inspect server.log')
                time.sleep(.05)
            process.terminate()
            process.wait(timeout=5)
            raise AssertionError('Server startup timed out')

        process = None
        try:
            process = start()
            data = sample()
            assert httpx.post(base + '/api/iotda/properties', json=data).status_code == 401
            first = httpx.post(base + '/api/iotda/properties', headers=HEADERS, json=data)
            assert first.status_code == 200
            assert first.json()['record']['bmi'] == 22.86
            assert first.json()['record']['speech_status'] == 'unconfirmed'
            assert httpx.post(base + '/api/iotda/properties', headers=HEADERS,
                              json=data).json()['duplicate'] is True
            data['notify_data']['body']['services'][0]['properties']['weight_kg'] = 71
            assert httpx.post(base + '/api/iotda/properties', headers=HEADERS,
                              json=data).status_code == 409
            process.terminate()
            process.wait(timeout=5)
            process = None
            process = start()
            result = httpx.get(base + '/api/exams', headers=READ_HEADERS).json()
            assert result['total_count'] == 1
            assert result['records'][0]['bmi'] == 22.86
            assert result['records'][0]['source'] == 'synthetic'
        finally:
            if process is not None:
                process.terminate()
                process.wait(timeout=5)
