from flask import Flask, request, jsonify
from supabase import create_client, Client
import os
import uuid
import zipfile
import tempfile
import shutil
import traceback

app = Flask(__name__)

# === SUPABASE CONFIGURATION ===
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://sailxghtmwksgbkjtrck.supabase.co")
SUPABASE_KEY = os.environ.get(
    "SUPABASE_SERVICE_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InNhaWx4Z2h0bXdrc2dia2p0cmNrIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2MjA5MjI5MywiZXhwIjoyMDc3NjY4MjkzfQ.AdKr52iLo0fBNV7H0-LDmXnI5shGTMpE-vuxA3jRYVE"
)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
BUCKET_NAME = "sites"

# Your new domain
CUSTOM_DOMAIN = "https://teamdevsss.netlify.app"

# Allowed extensions (same safe list)
ALLOWED_EXTENSIONS = {
    '.html', '.htm', '.css', '.js', '.json', '.xml',
    '.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.ico',
    '.txt', '.md', '.woff', '.woff2', '.ttf', '.eot', '.otf',
    '.mp3', '.wav', '.ogg', '.mp4', '.webm', '.pdf', '.csv',
}

BLOCKED_EXTENSIONS = {
    '.py', '.php', '.php5', '.phtml', '.exe', '.sh', '.bat', '.cmd',
    '.jar', '.asp', '.aspx', '.rb', '.pl', '.cgi', '.dll', '.so'
}

def is_safe_path(path):
    normalized = os.path.normpath("/" + path).lstrip("/")
    if normalized.startswith("..") or normalized == ".":
        return False
    ext = os.path.splitext(path)[1].lower()
    if ext in BLOCKED_EXTENSIONS:
        return False
    if ext and ext not in ALLOWED_EXTENSIONS:
        return False
    return True

def get_mime_type(filename):
    ext = os.path.splitext(filename)[1].lower()
    mime_map = {
        '.html': 'text/html', '.css': 'text/css', '.js': 'application/javascript',
        '.json': 'application/json', '.png': 'image/png', '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg', '.gif': 'image/gif', '.svg': 'image/svg+xml',
        '.webp': 'image/webp', '.ico': 'image/x-icon', '.woff': 'font/woff',
        '.woff2': 'font/woff2', '.ttf': 'font/ttf',
    }
    return mime_map.get(ext, 'application/octet-stream')

@app.route("/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400
    
    file = request.files["file"]
    name = request.form.get("name") or str(uuid.uuid4())[:10]

    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    if not file.filename.lower().endswith('.zip'):
        return jsonify({"error": "Only .zip files are allowed"}), 400

    temp_dir = tempfile.mkdtemp()
    zip_path = os.path.join(temp_dir, "upload.zip")

    try:
        file.save(zip_path)

        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            for zip_info in zip_ref.infolist():
                if zip_info.filename.startswith("/") or ".." in zip_info.filename:
                    return jsonify({"error": "Path traversal detected in ZIP"}), 400
                if not is_safe_path(zip_info.filename):
                    ext = os.path.splitext(zip_info.filename)[1].lower()
                    return jsonify({
                        "error": f"Blocked file: {zip_info.filename}",
                        "reason": f"Extension {ext} not allowed"
                    }), 400
            zip_ref.extractall(temp_dir)

        uploaded_files = []
        index_found = False

        for root, _, files in os.walk(temp_dir):
            for f in files:
                if f == "upload.zip":
                    continue
                local_path = os.path.join(root, f)
                rel_path = os.path.relpath(local_path, temp_dir)
                
                if not is_safe_path(rel_path):
                    continue

                storage_path = f"{name}/{rel_path}".replace("\\", "/")

                with open(local_path, "rb") as f_obj:
                    res = supabase.storage.from_(BUCKET_NAME).upload(
                        storage_path,
                        f_obj,
                        file_options={"upsert": True, "content-type": get_mime_type(f)}
                    )
                    if res.status_code not in (200, 201):
                        raise Exception(f"Upload failed: {res.json()}")

                uploaded_files.append(storage_path)
                if rel_path.lower() == "index.html":
                    index_found = True

        public_url = supabase.storage.from_(BUCKET_NAME).get_public_url(f"{name}/index.html")

        return jsonify({
            "success": True,
            "name": name,
            "url": f"{CUSTOM_DOMAIN}/{name}",           # ← Updated here
            "public_index": public_url,
            "uploaded_files_count": len(uploaded_files),
            "message": "Site deployed successfully!"
        })

    except zipfile.BadZipFile:
        return jsonify({"error": "Invalid or corrupted ZIP file"}), 400
    except Exception as e:
        error_detail = traceback.format_exc()
        print("Upload Error:", error_detail)
        return jsonify({
            "error": "Deployment failed",
            "details": str(e),
            "traceback": error_detail   # Remove this line in production if you don't want to expose traceback
        }), 500
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.route("/site/<name>/<path:filename>")
def serve_site(name, filename):
    file_url = supabase.storage.from_(BUCKET_NAME).get_public_url(f"{name}/{filename}")
    return jsonify({"redirect": file_url})


@app.route("/")
def health():
    return jsonify({"status": "ok", "service": "teamdevsss.netlify.app Deployer"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
