from flask import Flask, request, render_template, jsonify, send_file
import fitz  # PyMuPDF
import os
from collections import defaultdict
import json

app = Flask(__name__)

UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "output"

# Folders banao agar nahi hain toh
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# -----------------------------
# HOME ROUTE
# -----------------------------
@app.route("/")
def home():
    return render_template("index.html")

# -----------------------------
# HIGH-SPEED SORTING ROUTE
# -----------------------------
@app.route("/upload", methods=["POST"])
def upload():
    if "pdf" not in request.files or "mapping" not in request.form:
        return jsonify({"error": "Missing PDF file or mapping data"}), 400

    file = request.files["pdf"]
    # Frontend (JavaScript) ne jo data bheja hai use read karein
    mapping = json.loads(request.form["mapping"])

    # Temporary save uploaded PDF
    filepath = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(filepath)

    try:
        # Original PDF open karein
        doc = fitz.open(filepath)
        grouped = defaultdict(list)

        # Mapping ke hisab se pages ko group karein
        for item in mapping:
            sku = item["sku"]
            page_idx = item["pageIndex"]
            grouped[sku].append(page_idx)

        # UNKNOWN ko aakhiri mein rakhne ke liye custom sort logic
        sorted_keys = sorted(grouped.keys(), key=lambda x: (x == "UNKNOWN", x))

        # Naya blank PDF generator initialize karein
        out_doc = fitz.open()
        output_file = os.path.join(OUTPUT_FOLDER, "SORTED_" + file.filename)

        for sku in sorted_keys:
            page_indices = grouped[sku]
            
            # Direct original PDF se naye PDF mein bina quality loss ke pages copy karein (Super Fast)
            out_doc.insert_pdf(doc, from_page=page_indices[0], to_page=page_indices[-1], select=page_indices)
            
            # Har SKU bundle ke baad ek Separator/Summary Page lagayein
            summary_page = out_doc.new_page(width=595, height=842) # Standard A4 Size
            summary_page.insert_text((150, 400), f"SKU: {sku}", fontsize=26, fontname="helv-bold")
            summary_page.insert_text((150, 450), f"TOTAL LABELS: {len(page_indices)}", fontsize=22, fontname="helv-bold")

        # PDF ko compress aur optimize karke save karein
        out_doc.save(output_file, garbage=3, deflate=True)
        out_doc.close()
        doc.close()

        # Server ka storage space bachane ke liye original uploaded file delete karein
        if os.path.exists(filepath):
            os.remove(filepath)

        # Frontend ko download link JSON format mein bheinjein (No timeout danger!)
        return jsonify({"file": "/download/" + os.path.basename(output_file)})

    except Exception as e:
        print(f"Server Processing Error: {e}")
        return jsonify({"error": str(e)}), 500

# -----------------------------
# DOWNLOAD ROUTE
# -----------------------------
@app.route("/download/<filename>")
def download(filename):
    path = os.path.join(OUTPUT_FOLDER, filename)
    if os.path.exists(path):
        return send_file(path, as_attachment=True)
    return "File Not Found", 404

if __name__ == "__main__":
    app.run(debug=False)