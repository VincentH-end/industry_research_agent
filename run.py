import socket

import uvicorn

from app.config import get_settings


def find_available_port(host: str, preferred: int, auto_port: bool, attempts: int = 20) -> int:
    candidates = range(preferred, min(preferred + attempts, 65536)) if auto_port else [preferred]
    last_error: OSError | None = None
    for port in candidates:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                    probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                probe.bind((host, port))
            return port
        except OSError as exc:
            last_error = exc
    raise RuntimeError(
        f"无法绑定 {host}:{preferred}；请关闭占用端口的进程或修改 SERVER_PORT。"
    ) from last_error


if __name__ == "__main__":
    settings = get_settings()
    port = find_available_port(
        settings.server_host,
        settings.server_port,
        settings.server_auto_port,
    )
    if port != settings.server_port:
        print(f"端口 {settings.server_port} 已被占用，自动切换到 {port}。")
    print(f"访问地址：http://{settings.server_host}:{port}")
    uvicorn.run(
        "app.main:app",
        host=settings.server_host,
        port=port,
        reload=settings.server_reload,
    )
