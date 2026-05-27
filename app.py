from flask import Flask, request, send_file, render_template, Response
import fitz  # PyMuPDF
from pypdf import PdfReader
import os
import io
import cv2
import numpy as np
from collections import defaultdict
import json
import re

app = Flask(__name__)

UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "output"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# -----------------------------
# BACKUP: BARCODE DETECTOR
# -----------------------------
def get_sku_from_barcode(image_bytes):
    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return None
        
        detector = cv2.barcode.BarcodeDetector()
        retval, decoded_info, _, _ = detector.detectAndDecode(img)
        if retval and decoded_info and decoded_info[0].strip():
            return decoded_info[0].strip()
            
        # Try thresholding
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)
        retval, decoded_info, _, _ = detector.detectAndDecode(thresh)
        if retval and decoded_info and decoded_info[0].strip():
            return decoded_info[0].strip()
    except:
        return None
    return None

# -----------------------------
# SMART TEXT/SKU EXTRACTOR
# -----------------------------
def extract_sku_from_text(page_text):
    """
    Yahan aap apne SKU ka pattern set kar sakte hain.
    Abhi ke liye ye pure text mein se aam taur par dikhne wale SKU ya Barcode numbers dhoodhega.
    """
    if not page_text:
        return None
        
    # Tarika 1: Agar text mein saaf saaf 'SKU:' ya 'SKU ' likha hai
    sku_match = re.search(r'SKU[\s:]*([A-Z0-9_-]+)', page_text, re.IGNORECASE)
    if sku_match:
        return sku_match.group(1).strip()
        
    # Tarika 2: Har line ko check karo jo sirf uppercase alphanumeric ho (A-Z, 0-9)
    lines = page_text.split('\n')
    for line in lines:
        cleaned = line.strip()
        # Agar koi line 5 se 15 characters ki hai aur usme numbers/alphabets hain (Jaise: SKU12345, ITEM-01)
        if 5 <= len(cleaned) <= 20 and re.match(r'^[A-Z0-9_-]+$', cleaned):
            return cleaned
            
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
        
        # Open with PyMuPDF for rendering/building
        doc = fitz.open(filepath)
        total_pages = len(doc)
        
        # Open with pypdf for clean text extraction
        reader = PdfReader(filepath)
        
        grouped = defaultdict(list)

        yield json.dumps({"step": "Reading & Analysing PDF Pages", "progress": 10}) + "\n"

        # -----------------------------
        # PAGE PROCESSING LOOP
        # -----------------------------
        for i in range(total_pages):
            sku = None
            
            # METHOD 1: Try Text Extraction (Super Fast, 100% Accurate if PDF has text)
            try:
                pypdf_page = reader.pages[i]
                text = pypdf_page.extract_text()
                sku = extract_sku_from_text(text)
            except Exception as e:
                print(f"Text extraction failed on page {i}: {e}")

            # METHOD 2: Fallback to Barcode Detection (Agar text se nahi mila)
            if not sku:
                try:
                    page = doc.load_page(i)
                    pix = page.get_pixmap(dpi=150) 
                    img_bytes = pix.tobytes("png")
                    sku = get_sku_from_barcode(img_bytes)
                except Exception as e:
                    print(f"Image rendering failed on page {i}: {e}")

            # Agar dono method se kuch nahi mila
            if not sku:
                sku = "UNKNOWN"

            grouped[sku].append(i)

            progress = int(((i + 1) / total_pages) * 60) + 10
            yield json.dumps({
                "step": f"Processing Page {i+1}/{total_pages} | Detected: {sku}",
                "progress": progress
            }) + "\n"

        # -----------------------------
        # SORTING DATA
        # -----------------------------
        yield json.dumps({"step": "Sorting SKU Data", "progress": 75}) + "\n"
        sorted_keys = sorted(grouped.keys(), key=lambda x: (x == "UNKNOWN", x))

        # -----------------------------
        # NEW PDF GENERATION
        # -----------------------------
        yield json.dumps({"step": "Generating Output PDF", "progress": 85}) + "\n"
        
        out_doc = fitz.open()
        output_file = os.path.join(OUTPUT_FOLDER, "SORTED_" + file.filename)

        for sku in sorted_keys:
            page_indices = grouped[sku]
            
            # Original pages ko stitch karein
            out_doc.insert_pdf(doc, from_page=page_indices[0], to_page=page_indices[-1], select=page_indices)
            
            # Separator Page
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
# DOWNLOAD FILE ROUTE
# -----------------------------
@app.route("/download/<filename>")
def download(filename):
    path = os.path.join(OUTPUT_FOLDER, filename)
    if os.path.exists(path):
        return send_file(path, as_attachment=True)
    return "File Not Found", 404

if __name__ == "__main__":
    app.run(debug=False)