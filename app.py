from flask import Flask, request, render_template, jsonify, send_file
import fitz  # PyMuPDF
import os
from collections import defaultdict
import json

app = Flask(__name__)

# Vercel par temporary files ke liye /tmp folder use karna zaroori hai
UPLOAD_FOLDER = "/tmp/uploads"
OUTPUT_FOLDER = "/tmp/output"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

@app.route("/")
def home():
    return render_template("index.html")

@app.route('/wms')
def wms_panel():
    return render_template('wms.html') 

@app.route("/upload", methods=["POST"])
def upload():
    if "pdf" not in request.files or "mapping" not in request.form:
        return jsonify({"error": "Missing data"}), 400

    file = request.files["pdf"]
    mapping = json.loads(request.form["mapping"])

    filepath = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(filepath)

    try:
        doc = fitz.open(filepath)
        grouped = defaultdict(list)

        for item in mapping:
            sku = item["sku"]
            page_idx = item["pageIndex"]
            grouped[sku].append(page_idx)

        sorted_keys = sorted(grouped.keys(), key=lambda x: (x == "UNKNOWN", x))

        out_doc = fitz.open()
        output_file = os.path.join(OUTPUT_FOLDER, "SORTED_" + file.filename)

        for sku in sorted_keys:
            page_indices = grouped[sku]
            out_doc.insert_pdf(doc, from_page=page_indices[0], to_page=page_indices[-1], select=page_indices)
            
            summary_page = out_doc.new_page(width=595, height=842)
            summary_page.insert_text((150, 400), f"SKU: {sku}", fontsize=26, fontname="helv-bold")
            summary_page.insert_text((150, 450), f"TOTAL LABELS: {len(page_indices)}", fontsize=22, fontname="helv-bold")

        out_doc.save(output_file, garbage=3, deflate=True)
        out_doc.close()
        doc.close()

        if os.path.exists(filepath):
            os.remove(filepath)

        return jsonify({"file": "/download/" + os.path.basename(output_file)})

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/download/<filename>")
def download(filename):
    path = os.path.join(OUTPUT_FOLDER, filename)
    if os.path.exists(path):
        return send_file(path, as_attachment=True)
    return "File Not Found", 404

# Vercel ke liye iski zaroorat hoti hai
app_obj = app

if __name__ == "__main__":
    app.run(debug=True)
