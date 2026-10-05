import socket

from run import find_available_port


def test_find_available_port_skips_occupied_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        occupied = listener.getsockname()[1]
        selected = find_available_port("127.0.0.1", occupied, auto_port=True, attempts=20)
    assert occupied < selected < occupied + 20
