from flask import Flask, request, send_file, render_template, Response
import fitz  # PyMuPDF
from pypdf import PdfReader
import os
from collections import defaultdict
import json
import re

app = Flask(__name__)

UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "output"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# -----------------------------
# SHIPPING LABEL SKU EXTRACTOR
# -----------------------------
def extract_sku_from_text(page_text):
    if not page_text:
        return None
        
    # Lines mein todte hain text ko saaf padhne ke liye
    lines = [line.strip() for line in page_text.split('\n') if line.strip()]
    
    for idx, line in enumerate(lines):
        # Agar kisi line mein exact "SKU" likha dikhe (Product Details ke andar)
        if line.upper() == "SKU":
            # Toh uski theek agli line mein tumhara actual SKU number hota hai
            if idx + 1 < len(lines):
                potential_sku = lines[idx + 1]
                # Filter: SKU aamtaur par Size ya Qty jaisa chota nahi hoga, usme numbers_underscore honge
                if len(potential_sku) > 3 and potential_sku.upper() != "SIZE":
                    return potential_sku
                    
        # Backup Tarika: Agar text sahi se read na ho aur "SKU" ke saath hi number chipka ho
        match = re.search(r'SKU\s*([\w\d_-]+)', line, re.IGNORECASE)
        if match:
            sku_val = match.group(1).strip()
            if sku_val and len(sku_val) > 2:
                return sku_val

    return None

# -----------------------------
# HOME ROUTE
# -----------------------------
@app.route("/")
def home():
    return render_template("index.html")

# -----------------------------
# STREAM PROCESSING UPLOAD
# -----------------------------
@app.route("/upload", methods=["POST"])
def upload():
    if "pdf" not in request.files:
        return "No file uploaded", 400

    file = request.files["pdf"]
    if file.filename == "":
        return "No file selected", 400

    filepath = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(filepath)

    def stream():
        yield json.dumps({"step": "Uploading PDF", "progress": 5}) + "\n"
        
        # PyMuPDF processing aur output ke liye
        doc = fitz.open(filepath)
        total_pages = len(doc)
        
        # pypdf text extract karne ke liye
        reader = PdfReader(filepath)
        
        grouped = defaultdict(list)

        yield json.dumps({"step": "Analysing Shipping Labels", "progress": 10}) + "\n"

        # -----------------------------
        # PAGE PROCESSING
        # -----------------------------
        for i in range(total_pages):
            sku = None
            
            try:
                pypdf_page = reader.pages[i]
                text = pypdf_page.extract_text()
                sku = extract_sku_from_text(text)
            except Exception as e:
                print(f"Error reading text at page {i}: {e}")

            # Agar kisi wajah se text na mile, toh hum "UNKNOWN" daal denge
            if not sku:
                sku = "UNKNOWN"

            grouped[sku].append(i)

            progress = int(((i + 1) / total_pages) * 60) + 10
            yield json.dumps({
                "step": f"Processing Page {i+1}/{total_pages} | Detected SKU: {sku}",
                "progress": progress
            }) + "\n"

        # -----------------------------
        # SORTING
        # -----------------------------
        yield json.dumps({"step": "Grouping & Sorting SKUs", "progress": 75}) + "\n"
        # Unknown ko aakhiri mein bhej kar baki sabko sort karein
        sorted_keys = sorted(grouped.keys(), key=lambda x: (x == "UNKNOWN", x))

        # -----------------------------
        # OUTPUT GENERATION
        # -----------------------------
        yield json.dumps({"step": "Generating Sorted PDF", "progress": 85}) + "\n"
        
        out_doc = fitz.open()
        output_file = os.path.join(OUTPUT_FOLDER, "SORTED_" + file.filename)

        for sku in sorted_keys:
            page_indices = grouped[sku]
            
            # Saare same SKU wale pages ek sath insert karo
            out_doc.insert_pdf(doc, from_page=page_indices[0], to_page=page_indices[-1], select=page_indices)
            
            # Har SKU ke khatam hote hi summary page add karein (Jaise tumne manga: Total 10 label)
            summary_page = out_doc.new_page(width=595, height=842)
            summary_page.insert_text((150, 400), f"SKU: {sku}", fontsize=26, fontname="helv-bold")
            summary_page.insert_text((150, 450), f"TOTAL LABELS: {len(page_indices)}", fontsize=22, fontname="helv-bold")

        out_doc.save(output_file, garbage=3, deflate=True)
        out_doc.close()
        doc.close()

        if os.path.exists(filepath):
            os.remove(filepath)

        yield json.dumps({
            "step": "COMPLETED",
            "progress": 100,
            "file": "/download/" + os.path.basename(output_file)
        }) + "\n"

    return Response(stream(), mimetype="text/plain")

# -----------------------------
# DOWNLOAD
# -----------------------------
@app.route("/download/<filename>")
def download(filename):
    path = os.path.join(OUTPUT_FOLDER, filename)
    if os.path.exists(path):
        return send_file(path, as_attachment=True)
    return "File Not Found", 404

if __name__ == "__main__":
    app.run(debug=False)