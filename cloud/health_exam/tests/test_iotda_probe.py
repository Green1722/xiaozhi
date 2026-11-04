import io

from cloud.health_exam.iotda_probe import password, packet, read_packet


def test_official_huawei_authentication_vector():
    # Huawei iot_02_0203 published example, independent of our implementation.
    assert password('12345678', '2025041401') == (
        'c75150e6cb841417396819e4d2ee4358a416344a03a083e3a8567074ddec820a')


def test_mqtt_standard_remaining_length_boundary():
    assert packet(0x30, b'x' * 128)[:3] == b'\x30\x80\x01'


def test_connack_can_arrive_in_multiple_tcp_fragments():
    stream = io.BytesIO(b'\x20\x02\x00\x00')

    class FragmentedConnection:
        def recv(self, count):
            return stream.read(min(count, 1))

    assert read_packet(FragmentedConnection()) == (0x20, b'\x00\x00')
