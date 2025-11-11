from flask import Flask, request, jsonify
from supabase import create_client, Client
import os, uuid, zipfile, tempfile, shutil

# Initialize Flask
app = Flask(__name__)

# Supabase keys (use environment variables in Render)
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")  # service key for uploads
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

BUCKET_NAME = "sites"

@app.route("/upload", methods=["POST"])
def upload():
    file = request.files.get("file")
    name = request.form.get("name") or str(uuid.uuid4())[:6]

    if not file:
        return jsonify({"error": "No file"}), 400

    # Create a temp folder to extract ZIP
    temp_dir = tempfile.mkdtemp()
    zip_path = os.path.join(temp_dir, "upload.zip")
    file.save(zip_path)

    # Extract the zip
    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        zip_ref.extractall(temp_dir)

    # Upload all extracted files to Supabase Storage
    for root, dirs, files in os.walk(temp_dir):
        for f in files:
            local_path = os.path.join(root, f)
            rel_path = os.path.relpath(local_path, temp_dir)
            supabase.storage.from_(BUCKET_NAME).upload(
                f"{name}/{rel_path}", open(local_path, "rb")
            )

    # Clean up
    shutil.rmtree(temp_dir)

    # Public link (to index.html)
    public_url = (
        supabase.storage.from_(BUCKET_NAME)
        .get_public_url(f"{name}/index.html")
    )

    return jsonify({
        "success": True,
        "name": name,
        "url": f"https://teamdev.sbs/{name}",
        "public_index": public_url
    })


@app.route("/site/<name>/<path:filename>")
def serve_site(name, filename):
    """Redirect to Supabase public link"""
    file_url = (
        supabase.storage.from_(BUCKET_NAME)
        .get_public_url(f"{name}/{filename}")
    )
    return jsonify({"redirect": file_url})

if __name__ == "__main__":
    app.run(debug=True)
