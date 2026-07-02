"""Unit tests for web API."""

import io
from unittest.mock import patch, MagicMock
import pytest

from pdfcover.web.app import create_app


@pytest.fixture
def app():
    return create_app(testing=True)


@pytest.fixture
def client(app):
    return app.test_client()


def test_convert_no_file(client):
    """Test convert endpoint without file."""
    response = client.post('/api/convert')
    assert response.status_code == 400
    data = response.get_json()
    assert data['status'] == 'error'


def test_convert_non_pdf(client):
    """Test convert endpoint with non-PDF file."""
    data = {
        'file': (io.BytesIO(b'not a pdf'), 'test.txt')
    }
    response = client.post('/api/convert', data=data, content_type='multipart/form-data')
    assert response.status_code == 400
    data_json = response.get_json()
    assert data_json['status'] == 'error'
    assert 'PDF' in data_json['message']


@patch('pdfcover.web.app.process_file')
def test_convert_success(mock_process, client):
    """Test successful PDF conversion."""
    # Mock the process_file function
    from pathlib import Path
    mock_process.return_value = MagicMock(
        source=Path('/tmp/test.pdf'),
        output=Path('D:/Users/luocj/pyProject/ky/pdfcover/coverdPDF/test_ocr.pdf'),
        status='success',
        error=None
    )

    # Create a minimal PDF-like content
    pdf_content = b'%PDF-1.4\n' + b'fake pdf content'

    data = {
        'file': (io.BytesIO(pdf_content), 'test.pdf')
    }
    response = client.post('/api/convert', data=data, content_type='multipart/form-data')
    assert response.status_code == 200
    data_json = response.get_json()
    assert data_json['status'] == 'success'
    assert 'output_path' in data_json


@patch('pdfcover.web.app.process_file')
def test_convert_ocr_error(mock_process, client):
    """Test OCR processing error."""
    # Mock failed processing
    from pathlib import Path
    mock_process.return_value = MagicMock(
        source=Path('/tmp/test.pdf'),
        output=None,
        status='failed',
        error='OCR processing failed'
    )

    pdf_content = b'%PDF-1.4\n' + b'fake pdf content'
    data = {
        'file': (io.BytesIO(pdf_content), 'test.pdf')
    }
    response = client.post('/api/convert', data=data, content_type='multipart/form-data')
    assert response.status_code == 200
    data_json = response.get_json()
    assert data_json['status'] == 'error'
    assert data_json['error'] == 'OCR processing failed'
