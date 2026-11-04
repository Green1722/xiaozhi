import copy
import hashlib

import pytest
from fastapi.testclient import TestClient

from cloud.health_exam.app import create_app, iotda_signature

FORWARD_KEY = 'TestOnlyForwardingToken123456'
READ_KEY = 'test-only-business-key-at-least-24'
BINDINGS = {'test-device': {'app_id': 'test-app', 'product_id': 'test-product',
                            'instrument_id': 'DEMO-01', 'source': 'synthetic'}}
HEADERS = {'timestamp': '1675654743514', 'nonce': '8b9b796d388d49bba43adaa53aaf5bc4',
           'signature': hashlib.sha256(('1675654743514' +
                        '8b9b796d388d49bba43adaa53aaf5bc4' + FORWARD_KEY).encode()).hexdigest()}
READ_HEADERS = {'X-API-Key': READ_KEY}


def sample():
    # Shape follows Huawei's iot_06_v5_01202 example; our properties are explicit.
    return {'resource': 'device.property', 'event': 'report',
            'event_time': '20261104T153454Z', 'notify_data': {
                'header': {'device_id': 'test-device', 'app_id': 'test-app',
                           'product_id': 'test-product'},
                'body': {'services': [{'service_id': 'PhysicalExam',
                         'event_time': '20261104T153454Z',
                         'properties': {'record_id': 'synthetic-001', 'height_cm': 175,
                                        'weight_kg': 70, 'measured_at': '2026-11-04T15:34:00Z',
                                        'source': 'measured', 'instrument_id': 'spoofed'}}]}}}


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(f'sqlite:///{tmp_path / "iotda.db"}', READ_KEY,
                               BINDINGS, FORWARD_KEY)) as client:
        yield client


def test_forward_query_and_retries(client):
    response = client.post('/api/iotda/properties', headers=HEADERS, json=sample())
    assert response.status_code == 200
    record = response.json()['record']
    assert record['bmi'] == 22.86
    assert record['source'] == 'synthetic'
    assert record['instrument_id'] == 'DEMO-01'
    assert record['measured_at'] == '2026-11-04T15:34:00Z'
    assert record['speech_status'] == 'unconfirmed'
    assert client.get('/api/exams', headers=READ_HEADERS).json()['total_count'] == 1
    retry = sample()
    retry['event_time'] = '20261104T160000Z'
    assert client.post('/api/iotda/properties', headers=HEADERS, json=retry).json()['duplicate']
    retry['notify_data']['body']['services'][0]['properties']['weight_kg'] = 71
    assert client.post('/api/iotda/properties', headers=HEADERS, json=retry).status_code == 409


def test_forward_credential_has_no_read_access(client):
    assert client.post('/api/iotda/properties', json=sample()).status_code == 401
    assert client.post('/api/iotda/properties', headers={'X-Iotda-Key': READ_KEY},
                       json=sample()).status_code == 401
    assert client.get('/api/exams', headers={'X-API-Key': FORWARD_KEY}).status_code == 401


@pytest.mark.parametrize('field', ['device_id', 'app_id', 'product_id'])
def test_reject_unknown_or_mismatched_device(client, field):
    data = sample()
    data['notify_data']['header'][field] = 'unregistered'
    assert client.post('/api/iotda/properties', headers=HEADERS, json=data).status_code == 403
    assert client.get('/api/exams', headers=READ_HEADERS).json()['total_count'] == 0


@pytest.mark.parametrize('case', ['missing-time', 'no-timezone', 'invalid-time', 'zero-height',
                                  'wrong-service', 'duplicate-service', 'missing-record'])
def test_incomplete_or_invalid_measurement_is_not_saved(client, case):
    data = sample()
    services = data['notify_data']['body']['services']
    props = services[0]['properties']
    if case == 'missing-time':
        del props['measured_at']
    elif case == 'no-timezone':
        props['measured_at'] = '2026-11-04T15:34:00'
    elif case == 'invalid-time':
        props['measured_at'] = 'invalidZ'
    elif case == 'zero-height':
        props['height_cm'] = 0
    elif case == 'wrong-service':
        services[0]['service_id'] = 'Other'
    elif case == 'duplicate-service':
        services.append(copy.deepcopy(services[0]))
    else:
        del props['record_id']
    assert client.post('/api/iotda/properties', headers=HEADERS, json=data).status_code == 422
    assert client.get('/api/exams', headers=READ_HEADERS).json()['total_count'] == 0


def test_record_survives_restart(tmp_path):
    url = f'sqlite:///{tmp_path / "persistent.db"}'
    with TestClient(create_app(url, READ_KEY, BINDINGS, FORWARD_KEY)) as first:
        assert first.post('/api/iotda/properties', headers=HEADERS, json=sample()).status_code == 200
    with TestClient(create_app(url, READ_KEY, BINDINGS, FORWARD_KEY)) as second:
        result = second.get('/api/exams', headers=READ_HEADERS).json()
        assert result['total_count'] == 1
        assert result['records'][0]['source_record_id'] == 'synthetic-001'


def test_unconfigured_forwarding_fails_closed(tmp_path):
    with TestClient(create_app(f'sqlite:///{tmp_path / "disabled.db"}', READ_KEY,
                               {}, '')) as client:
        assert client.post('/api/iotda/properties', headers=HEADERS,
                           json=sample()).status_code == 503


def test_official_http_signature_vector(tmp_path):
    # Huawei's published aaaaaa token is shorter than our production minimum;
    # verify its known SHA256 example independently of the inbound API config.
    assert iotda_signature('aaaaaa', '1675654743514', '8b9b796d388d49bba43adaa53aaf5bc4') == (
        '2ff821fb8a976ede7d06434395ec8c25e4100bff8b3d12d8099ef7e30b58bd4c')


def test_invalid_signature_is_rejected(client):
    headers = dict(HEADERS, signature='0' * 64)
    assert client.post('/api/iotda/properties', headers=headers, json=sample()).status_code == 401
