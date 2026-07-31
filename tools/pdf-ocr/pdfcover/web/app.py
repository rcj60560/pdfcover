"""Flask application for PDFCover web interface."""

import tempfile
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_from_directory
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import secure_filename

from pdfcover.config import DEFAULT_OUTPUT_SUFFIX
from pdfcover.processor import process_file
from pdfcover.reflow import reflow_pdf
from pdfcover.splitter import extract_page_range

OUTPUT_DIR = Path("D:/Users/luocj/pyProject/ky/pdfcover/coverdPDF")
ALLOWED_EXTENSIONS = {"pdf"}
MAX_UPLOAD_SIZE = 2 * 1024 * 1024 * 1024  # 2GB


def create_app(testing=True):
    """Create and configure Flask app."""

    app = Flask(__name__)
    app.config["TESTING"] = testing
    app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_SIZE
    app.config["OUTPUT_DIR"] = str(OUTPUT_DIR)
    app.config["UPLOAD_FOLDER"] = str(Path.cwd() / "temp")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    def allowed_file(filename):
        return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

    def save_upload(file):
        filename = secure_filename(file.filename)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            file.save(tmp.name)
            return filename, tmp.name

    def error_response(message, status_code=400, error=None, page_count=None):
        return jsonify({
            "status": "error",
            "message": message,
            "output_path": None,
            "error": error,
            "page_count": page_count,
        }), status_code

    @app.errorhandler(RequestEntityTooLarge)
    def handle_file_too_large(exc):
        size_gb = MAX_UPLOAD_SIZE // (1024 * 1024 * 1024)
        return error_response(
            f"文件过大，当前最大支持 {size_gb}GB",
            status_code=413,
            error=str(exc),
        )

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/api/convert", methods=["POST"])
    def convert():
        if "file" not in request.files:
            return error_response("没有上传文件")

        file = request.files["file"]
        if file.filename == "":
            return error_response("文件名为空")

        if not allowed_file(file.filename):
            return error_response("请选择 PDF 文件")

        filename, temp_path = save_upload(file)

        try:
            output_dir = Path(app.config["OUTPUT_DIR"])
            output_stem = Path(filename).stem or "document"
            output_path = output_dir / f"{output_stem}{DEFAULT_OUTPUT_SUFFIX}.pdf"

            result = process_file(temp_path, output_path)

            if result.status == "success":
                return jsonify({
                    "status": "success",
                    "message": "转换成功",
                    "output_path": f"coverdPDF/{result.output.name}",
                    "error": None,
                })

            return jsonify({
                "status": "error",
                "message": "转换失败",
                "output_path": None,
                "error": result.error,
            })
        except Exception as exc:
            return error_response("服务器错误", error=str(exc))
        finally:
            try:
                Path(temp_path).unlink()
            except OSError:
                pass

    @app.route("/api/extract-pages", methods=["POST"])
    def extract_pages():
        if "file" not in request.files:
            return error_response("没有上传文件")

        file = request.files["file"]
        if file.filename == "":
            return error_response("文件名为空")

        if not allowed_file(file.filename):
            return error_response("请选择 PDF 文件")

        try:
            start_page = int(request.form.get("start_page", ""))
            end_page = int(request.form.get("end_page", ""))
        except ValueError:
            return error_response("页码必须是数字")

        filename, temp_path = save_upload(file)

        try:
            output_dir = Path(app.config["OUTPUT_DIR"])
            output_stem = Path(filename).stem or "document"
            output_path = output_dir / f"{output_stem}_p{start_page}-{end_page}.pdf"

            result = extract_page_range(temp_path, output_path, start_page, end_page)

            if result.status == "success":
                return jsonify({
                    "status": "success",
                    "message": "截取成功",
                    "output_path": f"coverdPDF/{result.output.name}",
                    "error": None,
                    "page_count": result.page_count,
                })

            return jsonify({
                "status": "error",
                "message": "截取失败",
                "output_path": None,
                "error": result.error,
                "page_count": result.page_count,
            })
        except Exception as exc:
            return error_response("服务器错误", error=str(exc))
        finally:
            try:
                Path(temp_path).unlink()
            except OSError:
                pass

    @app.route("/api/reflow", methods=["POST"])
    def reflow():
        if "file" not in request.files:
            return error_response("没有上传文件")

        file = request.files["file"]
        if file.filename == "":
            return error_response("文件名为空")

        if not allowed_file(file.filename):
            return error_response("请选择 PDF 文件")

        # Page range is optional; empty values mean "whole document".
        start_page = request.form.get("start_page") or None
        end_page = request.form.get("end_page") or None
        try:
            start_page = int(start_page) if start_page else None
            end_page = int(end_page) if end_page else None
        except ValueError:
            return error_response("页码必须是数字")

        filename, temp_path = save_upload(file)

        try:
            output_dir = Path(app.config["OUTPUT_DIR"])
            output_stem = Path(filename).stem or "document"
            output_path = output_dir / f"{output_stem}_reflow.txt"

            result = reflow_pdf(temp_path, output_path, start_page, end_page)

            if result.status == "success":
                return jsonify({
                    "status": "success",
                    "message": "整理成功",
                    "output_path": f"coverdPDF/{result.output.name}",
                    "error": None,
                    "page_count": result.page_count,
                    "text": result.text,
                    "truncated": result.truncated,
                })

            return jsonify({
                "status": "error",
                "message": "整理失败",
                "output_path": None,
                "error": result.error,
                "page_count": result.page_count,
            })
        except Exception as exc:
            return error_response("服务器错误", error=str(exc))
        finally:
            try:
                Path(temp_path).unlink()
            except OSError:
                pass

    @app.route("/download/<path:filename>")
    def download(filename):
        output_dir = Path(app.config["OUTPUT_DIR"])
        # Resolve and confirm the target stays inside OUTPUT_DIR (no traversal).
        target = (output_dir / filename).resolve()
        if output_dir.resolve() not in target.parents and target != output_dir.resolve():
            return error_response("非法路径", status_code=404)
        return send_from_directory(str(output_dir), filename, as_attachment=True)

    return app
