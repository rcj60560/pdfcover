"""Entry point for running PDFCover web server."""

import webbrowser
import time
from pdfcover.web.app import create_app


def main():
    """Start the Flask development server and open browser."""
    app = create_app()

    print("=" * 50)
    print("PDFCover Web 服务器已启动")
    print("=" * 50)
    print(f"访问地址: http://127.0.0.1:5000")
    print(f"输出目录: {app.config['OUTPUT_DIR']}")
    print("=" * 50)
    print("按 Ctrl+C 停止服务器")
    print()

    # Open browser after a short delay
    def open_browser():
        time.sleep(1)
        webbrowser.open('http://127.0.0.1:5000')

    import threading
    browser_thread = threading.Thread(target=open_browser, daemon=True)
    browser_thread.start()

    # Run app
    app.run(host='127.0.0.1', port=5000, debug=False)


if __name__ == '__main__':
    main()
