"""入口：python -m launcher → :5500 并自动开浏览器。"""
import threading
import time
import webbrowser

from .app import create_app


def main() -> None:
    app = create_app()
    threading.Thread(
        target=lambda: (time.sleep(1.2), webbrowser.open("http://127.0.0.1:5500")),
        daemon=True,
    ).start()
    app.run(host="127.0.0.1", port=5500, debug=False)


if __name__ == "__main__":
    main()
