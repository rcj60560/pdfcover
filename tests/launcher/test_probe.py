import socket

from launcher.probe import port_open


def _free_port() -> int:
    """拿一个空闲端口后立刻关闭，返回其号（此时应不可连）。"""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_open_port_detected():
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    try:
        assert port_open(port) is True
    finally:
        srv.close()


def test_closed_port_not_detected():
    port = _free_port()  # 已关闭
    assert port_open(port) is False
