from flask import Flask, request, jsonify, send_from_directory
from supabase import create_client, Client
import os
import uuid
import zipfile
import tempfile
import shutil
import traceback

app = Flask(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://sailxghtmwksgbkjtrck.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InNhaWx4Z2h0bXdrc2dia2p0cmNrIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2MjA5MjI5MywiZXhwIjoyMDc3NjY4MjkzfQ.AdKr52iLo0fBNV7H0-LDmXnI5shGTMpE-vuxA3jRYVE")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
BUCKET_NAME = "sites"
CUSTOM_DOMAIN = "https://teamdevsss.netlify.app"

# Allowed for single file upload + ZIP contents
ALLOWED_EXTENSIONS = {
    '.html', '.htm', '.css', '.js', '.json', '.xml', '.txt', '.md', '.svg',
    '.png', '.jpg', '.jpeg', '.gif', '.webp', '.ico', '.avif',
    '.woff', '.woff2', '.ttf', '.eot', '.otf'
}

def is_allowed_file(filename):
    return os.path.splitext(filename)[1].lower() in ALLOWED_EXTENSIONS

@app.route("/upload", methods=["POST"])
def upload():
    name = request.form.get("name") or str(uuid.uuid4())[:10]
    
    # Case 1: ZIP Upload (Full Site)
    if "file" in request.files and request.files["file"].filename.endswith('.zip'):
        return handle_zip_upload(request.files["file"], name)
    
    # Case 2: Single File Upload (Direct .html, .css, etc)
    elif "file" in request.files:
        return handle_single_file_upload(request.files["file"], name)
    
    else:
        return jsonify({"error": "No file provided"}), 400


def handle_zip_upload(zip_file, name):
    if not zip_file.filename.endswith('.zip'):
        return jsonify({"error": "Only .zip files allowed for multi-file upload"}), 400

    temp_dir = tempfile.mkdtemp()
    zip_path = os.path.join(temp_dir, "site.zip")

    try:
        zip_file.save(zip_path)
        with zipfile.ZipFile(zip_path, 'r') as z:
            for file_info in z.infolist():
                if file_info.filename.startswith('/') or '../' in file_info.filename:
                    return jsonify({"error": "Invalid paths in ZIP"}), 400
                if not is_allowed_file(file_info.filename):
                    return jsonify({"error": f"Blocked file: {file_info.filename}"}), 400
            z.extractall(temp_dir)

        uploaded = 0
        for root, _, files in os.walk(temp_dir):
            for f in files:
                if f == "site.zip": continue
                local_path = os.path.join(root, f)
                rel_path = os.path.relpath(local_path, temp_dir).replace("\\", "/")
                storage_path = f"{name}/{rel_path}"

                with open(local_path, "rb") as f_obj:
                    supabase.storage.from_(BUCKET_NAME).upload(
                        path=storage_path,
                        file=f_obj,
                        file_options={"content-type": get_mime_type(f), "upsert": "true"}
                    )
                uploaded += 1

        public_url = supabase.storage.from_(BUCKET_NAME).get_public_url(f"{name}/index.html")
        return jsonify({
            "success": True,
            "name": name,
            "url": f"{CUSTOM_DOMAIN}/{name}",
            "direct": public_url,
            "files": uploaded,
            "message": "Full site deployed from ZIP!"
        })

    except Exception as e:
        return jsonify({"error": "ZIP upload failed", "details": str(e)}), 500
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def handle_single_file_upload(file, name):
    if not file or file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    original_name = file.filename
    if not is_allowed_file(original_name):
        return jsonify({"error": f"File type not allowed: {original_name}"}), 400

    # If it's index.html → treat as root site
    if original_name.lower() == "index.html":
        storage_path = f"{name}/index.html"
    else:
        storage_path = f"{name}/{original_name}"

    try:
        file.stream.seek(0)
        supabase.storage.from_(BUCKET_NAME).upload(
            path=storage_path,
            file=file.stream.read(),
            file_options={
                "content-type": get_mime_type(original_name),
                "upsert": "true"
            }
        )

        public_url = supabase.storage.from_(BUCKET_NAME).get_public_url(storage_path)

        return jsonify({
            "success": True,
            "name": name,
            "file": original_name,
            "url": f"{CUSTOM_DOMAIN}/{name}" if "index.html" in storage_path else public_url,
            "direct": public_url,
            "message": "Single file uploaded successfully!"
        })

    except Exception as e:
        return jsonify({"error": "Upload failed", "details": str(e)}), 500


def get_mime_type(filename):
    ext = os.path.splitext(filename)[1].lower()
    map = {
        '.html': 'text/html', '.css': 'text/css', '.js': 'application/javascript',
        '.json': 'application/json', '.xml': 'application/xml',
        '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
        '.gif': 'image/gif', '.webp': 'image/webp', '.svg': 'image/svg+xml',
        '.ico': 'image/x-icon', '.woff': 'font/woff', '.woff2': 'font/woff2'
    }
    return map.get(ext, 'application/octet-stream')


@app.route("/")
def home():
    return jsonify({
        "service": "TeamDevSSS – Free Unlimited Hosting",
        "status": "running",
        "upload": "/upload (ZIP or single file)",
        "example": "curl -F 'file=@index.html' https://teamdevapi-1.onrender.com/upload"
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
