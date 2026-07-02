"""Flask application for PDFCover web interface."""

import os
from pathlib import Path
from flask import Flask, render_template

OUTPUT_DIR = Path('D:/Users/luocj/pyProject/ky/pdfcover/coverdPDF')


def create_app(testing=True):
    """Create and configure Flask app.

    Args:
        testing: Whether to run in testing mode

    Returns:
        Configured Flask application
    """
    app = Flask(__name__)
    app.config['TESTING'] = testing
    app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB
    app.config['OUTPUT_DIR'] = str(OUTPUT_DIR)
    app.config['UPLOAD_FOLDER'] = str(Path.cwd() / 'temp')

    # Ensure output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    @app.route('/')
    def index():
        return render_template('index.html')

    return app
