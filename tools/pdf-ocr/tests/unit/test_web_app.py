"""Unit tests for web application."""

import pytest
from pdfcover.web.app import create_app


def test_create_app():
    """Test that Flask app can be created."""
    app = create_app()
    assert app is not None
    assert app.config['TESTING'] is True


def test_output_dir_config():
    """Test that output directory is configured."""
    app = create_app()
    assert 'OUTPUT_DIR' in app.config
    assert app.config['OUTPUT_DIR'] == 'D:\\Users\\luocj\\pyProject\\ky\\pdfcover\\coverdPDF'


def test_max_content_length():
    """Test that max content length is set."""
    app = create_app()
    assert app.config['MAX_CONTENT_LENGTH'] == 2 * 1024 * 1024 * 1024


def test_root_route():
    """Test that root route returns HTML."""
    app = create_app()
    client = app.test_client()
    response = client.get('/')
    assert response.status_code == 200
    assert b'PDF' in response.data
    assert b'html' in response.data.lower()


def test_module_main_exists():
    """Test that __main__ module can be imported."""
    from pdfcover.web import __main__
    assert hasattr(__main__, 'main')
