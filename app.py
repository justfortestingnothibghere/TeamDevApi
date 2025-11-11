from flask import Flask, request, jsonify
from supabase import create_client, Client
import os
import uuid
import zipfile
import tempfile
import shutil

# Initialize Flask
app = Flask(__name__)

# === SUPABASE CONFIGURATION ===
# In production (Render, Railway, etc.), set these as environment variables
# Locally, you can use the values below or create a .env file

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://sailxghtmwksgbkjtrck.supabase.co")
SUPABASE_KEY = os.environ.get(
    "SUPABASE_SERVICE_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InNhaWx4Z2h0bXdrc2dia2p0cmNrIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2MjA5MjI5MywiZXhwIjoyMDc3NjY4MjkzfQ.AdKr52iLo0fBNV7H0-LDmXnI5shGTMpE-vuxA3jRYVE"
)

# Optional: You can also expose the anon key if needed elsewhere
SUPABASE_ANON_KEY = os.environ.get(
    "SUPABASE_ANON_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InNhaWx4Z2h0bXdrc2dia2p0cmNrIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjIwOTIyOTMsImV4cCI6MjA3NzY2ODI5M30.E0VmWmHszgHj_ny7QQZ6dkBfLvBFwbRQ96hv2_dir1o"
)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

BUCKET_NAME = "sites"


@app.route("/upload", methods=["POST"])
def upload():
    file = request.files.get("file")
    name = request.form.get("name") or str(uuid.uuid4())[:8]  # slightly longer for uniqueness

    if not file:
        return jsonify({"error": "No file provided"}), 400

    # Create temporary directory
    temp_dir = tempfile.mkdtemp()
    zip_path = os.path.join(temp_dir, "upload.zip")
    
    try:
        file.save(zip_path)

        # Extract ZIP
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(temp_dir)

        # Upload all files to Supabase Storage
        uploaded_files = []
        for root, dirs, files in os.walk(temp_dir):
            for f in files:
                local_path = os.path.join(root, f)
                rel_path = os.path.relpath(local_path, temp_dir)
                storage_path = f"{name}/{rel_path}".replace("\\", "/")  # Normalize path

                with open(local_path, "rb") as f_obj:
                    supabase.storage.from_(BUCKET_NAME).upload(
                        storage_path,
                        f_obj,
                        file_options={"upsert": True}  # Overwrite if exists
                    )
                uploaded_files.append(storage_path)

        # Generate public URL for index.html
        public_url = supabase.storage.from_(BUCKET_NAME).get_public_url(f"{name}/index.html")

        return jsonify({
            "success": True,
            "name": name,
            "url": f"https://teamdev.sbs/{name}",
            "public_index": public_url,
            "uploaded_files_count": len(uploaded_files)
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

    finally:
        # Always clean up temp files
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.route("/site/<name>/<path:filename>")
def serve_site(name, filename):
    """Return the direct Supabase public URL (can be used for redirect or proxy)"""
    file_url = supabase.storage.from_(BUCKET_NAME).get_public_url(f"{name}/{filename}")
    return jsonify({"redirect": file_url})


# Health check endpoint (useful for Render/Vercel)
@app.route("/")
def health():
    return jsonify({"status": "ok", "service": "Supabase Static Site Deployer"})


if __name__ == "__main__":
    # Never use debug=True in production
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
