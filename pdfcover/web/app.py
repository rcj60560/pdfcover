"""Flask application for PDFCover web interface."""

import os
from pathlib import Path
from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename
import tempfile
from pdfcover.processor import process_file

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
    app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 1024  # 1GB
    app.config['OUTPUT_DIR'] = str(OUTPUT_DIR)
    app.config['UPLOAD_FOLDER'] = str(Path.cwd() / 'temp')

    # Ensure output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    @app.route('/')
    def index():
        return render_template('index.html')

    ALLOWED_EXTENSIONS = {'pdf'}

    def allowed_file(filename):
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

    @app.route('/api/convert', methods=['POST'])
    def convert():
        if 'file' not in request.files:
            return jsonify({
                'status': 'error',
                'message': '没有上传文件',
                'output_path': None,
                'error': None
            }), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({
                'status': 'error',
                'message': '文件名为空',
                'output_path': None,
                'error': None
            }), 400

        if not allowed_file(file.filename):
            return jsonify({
                'status': 'error',
                'message': '请选择 PDF 文件',
                'output_path': None,
                'error': None
            }), 400

        # Save to temp location
        filename = secure_filename(file.filename)
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
            file.save(tmp.name)
            temp_path = tmp.name

        try:
            # Process the file
            output_dir = Path(app.config['OUTPUT_DIR'])
            output_path = output_dir / f"{Path(filename).stem}_ocr.pdf"

            result = process_file(temp_path, output_path)

            if result.status == 'success':
                return jsonify({
                    'status': 'success',
                    'message': '转换成功',
                    'output_path': f"coverdPDF/{result.output.name}",
                    'error': None
                })
            else:
                return jsonify({
                    'status': 'error',
                    'message': '转换失败',
                    'output_path': None,
                    'error': result.error
                })

        except Exception as e:
            return jsonify({
                'status': 'error',
                'message': '服务器错误',
                'output_path': None,
                'error': str(e)
            })
        finally:
            # Clean up temp file
            try:
                Path(temp_path).unlink()
            except:
                pass

    return app
