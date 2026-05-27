from flask import Flask, request, send_file, render_template, Response
import fitz  # PyMuPDF
import os
import io
import cv2
import numpy as np
from pyzbar.pyzbar import decode
from collections import defaultdict
import json
import time

app = Flask(__name__)

UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "output"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# -----------------------------
# BARCODE DETECTOR (Optimized)
# -----------------------------
def get_sku_from_barcode(image_bytes):
    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return None
        
        barcodes = decode(img)
        for barcode in barcodes:
            return barcode.data.decode("utf-8").strip()
    except Exception as e:
        print(f"Barcode error: {e}")
        return "UNKNOWN"
    return None

# -----------------------------
# HOME
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
        
        # Open source PDF
        doc = fitz.open(filepath)
        total_pages = len(doc)
        
        # grouped[sku] = [page_num1, page_num2, ...] -> RAM mein sirf numbers save honge, images nahi!
        grouped = defaultdict(list)

        yield json.dumps({"step": "Reading PDF Pages", "progress": 10}) + "\n"

        # -----------------------------
        # PAGE PROCESSING (Low RAM)
        # -----------------------------
        for i in range(total_pages):
            page = doc.load_page(i)
            sku = None

            # Try to get embedded images first (Fastest & lowest RAM)
            image_list = page.get_images(full=True)
            if image_list:
                try:
                    xref = image_list[0][0] # Get the first image on the page
                    base_image = doc.extract_image(xref)
                    img_bytes = base_image["image"]
                    sku = get_sku_from_barcode(img_bytes)
                except:
                    sku = None

            # Fallback: Agar embedded image nahi mili ya barcode nahi mila, tabhi kam DPI par page render karo
            if not sku:
                try:
                    pix = page.get_pixmap(dpi=120) # 200 se ghata kar 120 kiya taaki RAM na bhare
                    img_bytes = pix.tobytes("png")
                    sku = get_sku_from_barcode(img_bytes)
                except:
                    sku = "UNKNOWN"

            if not sku:
                sku = "UNKNOWN"

            grouped[sku].append(i) # Store ONLY page index

            progress = int(((i + 1) / total_pages) * 60) + 10
            yield json.dumps({
                "step": f"Processing Page {i+1}/{total_pages} | SKU: {sku}",
                "progress": progress
            }) + "\n"

        # -----------------------------
        # SORTING
        # -----------------------------
        yield json.dumps({"step": "Sorting SKU Data", "progress": 75}) + "\n"
        sorted_keys = sorted(grouped.keys(), key=lambda x: (x == "UNKNOWN", x))

        # -----------------------------
        # PDF GENERATION (Super Fast Page Copy)
        # -----------------------------
        yield json.dumps({"step": "Generating Output PDF", "progress": 85}) + "\n"
        
        out_doc = fitz.open() # Create blank PDF
        output_file = os.path.join(OUTPUT_FOLDER, "SORTED_" + file.filename)

        for sku in sorted_keys:
            page_indices = grouped[sku]
            
            # 1. Asli PDF se direct pages copy karo (No quality loss, 0 RAM impact)
            out_doc.insert_pdf(doc, from_page=page_indices[0], to_page=page_indices[-1], select=page_indices)
            
            # 2. SKU Summary Page add karo
            summary_page = out_doc.new_page(width=595, height=842) # A4 size
            # Text write karne ke liye insert_text use karein
            summary_page.insert_text((180, 400), f"SKU: {sku}", fontsize=26, fontname="helv-bold")
            summary_page.insert_text((180, 450), f"TOTAL: {len(page_indices)}", fontsize=26, fontname="helv-bold")

        out_doc.save(output_file, garbage=3, deflate=True)
        out_doc.close()
        doc.close()

        # Delete original uploaded file to save disk space on Render
        if os.path.exists(filepath):
            os.remove(filepath)

        yield json.dumps({
            "step": "COMPLETED",
            "progress": 100,
            "file": "/download/" + os.path.basename(output_file)
        }) + "\n"

    return Response(stream(), mimetype="text/plain")

# -----------------------------
# DOWNLOAD FILE
# -----------------------------
@app.route("/download/<filename>")
def download(filename):
    path = os.path.join(OUTPUT_FOLDER, filename)
    return send_file(path, as_attachment=True)

if __name__ == "__main__":
    app.run(debug=False)