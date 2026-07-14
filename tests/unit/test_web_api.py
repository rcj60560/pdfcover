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


def test_extract_pages_requires_numeric_pages(client):
    """Test page extraction endpoint rejects invalid page numbers."""
    data = {
        'file': (io.BytesIO(b'%PDF-1.4\n'), 'test.pdf'),
        'start_page': 'a',
        'end_page': '10',
    }
    response = client.post('/api/extract-pages', data=data, content_type='multipart/form-data')
    assert response.status_code == 400
    data_json = response.get_json()
    assert data_json['status'] == 'error'
    assert '页码' in data_json['message']


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


@patch('pdfcover.web.app.extract_page_range')
def test_extract_pages_success(mock_extract, client):
    """Test successful PDF page extraction."""
    from pathlib import Path
    mock_extract.return_value = MagicMock(
        source=Path('/tmp/test.pdf'),
        output=Path('D:/Users/luocj/pyProject/ky/pdfcover/coverdPDF/test_p50-60.pdf'),
        status='success',
        error=None,
        page_count=120
    )

    data = {
        'file': (io.BytesIO(b'%PDF-1.4\nfake pdf content'), 'test.pdf'),
        'start_page': '50',
        'end_page': '60',
    }
    response = client.post('/api/extract-pages', data=data, content_type='multipart/form-data')
    assert response.status_code == 200
    data_json = response.get_json()
    assert data_json['status'] == 'success'
    assert data_json['output_path'] == 'coverdPDF/test_p50-60.pdf'


@patch('pdfcover.web.app.extract_page_range')
def test_extract_pages_failure(mock_extract, client):
    """Test PDF page extraction error response."""
    from pathlib import Path
    mock_extract.return_value = MagicMock(
        source=Path('/tmp/test.pdf'),
        output=Path('D:/Users/luocj/pyProject/ky/pdfcover/coverdPDF/test_p60-50.pdf'),
        status='failed',
        error='起始页不能大于结束页',
        page_count=None
    )

    data = {
        'file': (io.BytesIO(b'%PDF-1.4\nfake pdf content'), 'test.pdf'),
        'start_page': '60',
        'end_page': '50',
    }
    response = client.post('/api/extract-pages', data=data, content_type='multipart/form-data')
    assert response.status_code == 200
    data_json = response.get_json()
    assert data_json['status'] == 'error'
    assert data_json['error'] == '起始页不能大于结束页'


def test_reflow_requires_pdf(client):
    """Reflow endpoint rejects non-PDF uploads."""
    data = {
        'file': (io.BytesIO(b'not a pdf'), 'test.txt')
    }
    response = client.post('/api/reflow', data=data, content_type='multipart/form-data')
    assert response.status_code == 400
    assert response.get_json()['status'] == 'error'


def test_reflow_rejects_non_numeric_pages(client):
    """Reflow endpoint rejects non-numeric page ranges."""
    data = {
        'file': (io.BytesIO(b'%PDF-1.4\n'), 'test.pdf'),
        'start_page': 'x',
        'end_page': '10',
    }
    response = client.post('/api/reflow', data=data, content_type='multipart/form-data')
    assert response.status_code == 400
    data_json = response.get_json()
    assert data_json['status'] == 'error'
    assert '页码' in data_json['message']


@patch('pdfcover.web.app.reflow_pdf')
def test_reflow_success(mock_reflow, client):
    """Test successful reflow returns inline text and output path."""
    from pathlib import Path
    mock_reflow.return_value = MagicMock(
        source=Path('/tmp/test.pdf'),
        output=Path('D:/Users/luocj/pyProject/ky/pdfcover/coverdPDF/test_reflow.txt'),
        status='success',
        error=None,
        page_count=18,
        text='alpha one\nbravo two',
        truncated=False,
    )

    data = {
        'file': (io.BytesIO(b'%PDF-1.4\nfake pdf content'), 'test.pdf'),
    }
    response = client.post('/api/reflow', data=data, content_type='multipart/form-data')
    assert response.status_code == 200
    data_json = response.get_json()
    assert data_json['status'] == 'success'
    assert data_json['output_path'] == 'coverdPDF/test_reflow.txt'
    assert data_json['text'] == 'alpha one\nbravo two'
    assert data_json['page_count'] == 18


@patch('pdfcover.web.app.reflow_pdf')
def test_reflow_failure(mock_reflow, client):
    """Reflow endpoint surfaces processing failures."""
    from pathlib import Path
    mock_reflow.return_value = MagicMock(
        source=Path('/tmp/test.pdf'),
        output=None,
        status='failed',
        error='起始页不能大于结束页',
        page_count=None,
        text='',
        truncated=False,
    )

    data = {
        'file': (io.BytesIO(b'%PDF-1.4\nfake pdf content'), 'test.pdf'),
        'start_page': '60',
        'end_page': '50',
    }
    response = client.post('/api/reflow', data=data, content_type='multipart/form-data')
    assert response.status_code == 200
    data_json = response.get_json()
    assert data_json['status'] == 'error'
    assert data_json['error'] == '起始页不能大于结束页'
