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
# ADVANCED BARCODE DETECTOR (Enhanced)
# -----------------------------
def get_sku_from_barcode(image_bytes):
    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return None
        
        # 1. Direct try karo (Original Image)
        barcodes = decode(img)
        for barcode in barcodes:
            return barcode.data.decode("utf-8").strip()
            
        # 2. Agar nahi mila, toh image ko Grayscale aur B&W (Threshold) karo taaki barcode clear ho jaye
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)
        
        barcodes = decode(thresh)
        for barcode in barcodes:
            return barcode.data.decode("utf-8").strip()

        # 3. Ek aur try: Sharpening (agar barcode blur hai)
        kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
        sharpened = cv2.filter2D(gray, -1, kernel)
        barcodes = decode(sharpened)
        for barcode in barcodes:
            return barcode.data.decode("utf-8").strip()

    except Exception as e:
        print(f"Barcode error: {e}")
        return None
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
        
        doc = fitz.open(filepath)
        total_pages = len(doc)
        grouped = defaultdict(list)

        yield json.dumps({"step": "Reading PDF Pages", "progress": 10}) + "\n"

        # -----------------------------
        # PAGE PROCESSING
        # -----------------------------
        for i in range(total_pages):
            page = doc.load_page(i)
            sku = None

            # Render page at 150 DPI (Good balance between RAM and Clarity)
            try:
                pix = page.get_pixmap(dpi=150) 
                img_bytes = pix.tobytes("png")
                sku = get_sku_from_barcode(img_bytes)
            except Exception as e:
                print(f"Page render error at page {i}: {e}")
                sku = "UNKNOWN"

            if not sku:
                sku = "UNKNOWN"

            grouped[sku].append(i)

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
        # PDF GENERATION
        # -----------------------------
        yield json.dumps({"step": "Generating Output PDF", "progress": 85}) + "\n"
        
        out_doc = fitz.open()
        output_file = os.path.join(OUTPUT_FOLDER, "SORTED_" + file.filename)

        for sku in sorted_keys:
            page_indices = grouped[sku]
            
            # Original pages copy karo
            out_doc.insert_pdf(doc, from_page=page_indices[0], to_page=page_indices[-1], select=page_indices)
            
            # SKU Separator Page
            summary_page = out_doc.new_page(width=595, height=842)
            summary_page.insert_text((150, 400), f"SKU: {sku}", fontsize=24, fontname="helv-bold")
            summary_page.insert_text((150, 440), f"TOTAL LABELS: {len(page_indices)}", fontsize=20, fontname="helv")

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
# DOWNLOAD FILE
# -----------------------------
@app.route("/download/<filename>")
def download(filename):
    path = os.path.join(OUTPUT_FOLDER, filename)
    return send_file(path, as_attachment=True)

if __name__ == "__main__":
    app.run(debug=False)