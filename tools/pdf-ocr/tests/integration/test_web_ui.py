"""Integration tests for web UI."""

import io
import time
from pdfcover.web.app import create_app


def test_full_conversion_flow():
    """Test end-to-end conversion through web interface."""
    app = create_app(testing=True)
    client = app.test_client()

    # Get main page
    response = client.get('/')
    assert response.status_code == 200
    assert b'PDF' in response.data

    # Upload and convert a minimal PDF
    minimal_pdf = b'%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n3 0 obj\n<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> /MediaBox [0 0 612 792] /Contents 5 0 R >>\nendobj\n4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n5 0 obj\n<< /Length 44 >>\nstream\nBT\n/F1 12 Tf\n100 700 Td\n(Test) Tj\nET\nendstream\nendobj\nxref\n0 6\n0000000000 65535 f\n0000000009 00000 n\n0000000056 00000 n\n0000000115 00000 n\n0000000266 00000 n\n0000000361 00000 n\ntrailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n451\n%%EOF'

    data = {'file': (io.BytesIO(minimal_pdf), 'integration_test.pdf')}
    response = client.post('/api/convert', data=data, content_type='multipart/form-data')

    # Note: This test uses mock OCR, so we just verify the API flow
    # Real OCR would require ocrmypdf installed
    assert response.status_code == 200
    result = response.get_json()
    assert 'status' in result
