from flask import Flask, request, send_file, render_template, Response
import fitz  # PyMuPDF
import os
import io
import cv2
import numpy as np
from collections import defaultdict
import json
import time

app = Flask(__name__)

UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "output"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# -----------------------------
# OPENCV BARCODE DETECTOR (No libzbar0 dependency)
# -----------------------------
def get_sku_from_barcode(image_bytes):
    try:
        # Bytes ko image mein convert karein
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return None
        
        # OpenCV ka native barcode detector initialize karein
        detector = cv2.barcode.BarcodeDetector()
        
        # 1. Pehla Try: Original Image par
        retval, decoded_info, decoded_type, _ = detector.detectAndDecode(img)
        if retval and decoded_info and decoded_info[0].strip():
            return decoded_info[0].strip()
            
        # 2. Doosra Try: Image ko Grayscale aur B&W (Threshold) karke (For blurry/small barcodes)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)
        
        retval, decoded_info, _, _ = detector.detectAndDecode(thresh)
        if retval and decoded_info and decoded_info[0].strip():
            return decoded_info[0].strip()

        # 3. Teesra Try: Image Sharpening (Agar barcode lines dhundli hain)
        kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
        sharpened = cv2.filter2D(gray, -1, kernel)
        retval, decoded_info, _, _ = detector.detectAndDecode(sharpened)
        if retval and decoded_info and decoded_info[0].strip():
            return decoded_info[0].strip()

    except Exception as e:
        print(f"Barcode Detection Error: {e}")
        return None
    return None

# -----------------------------
# HOME ROUTE
# -----------------------------
@app.route("/")
def home():
    return render_template("index.html")

# -----------------------------
# STREAM PROCESSING UPLOAD & SORT
# -----------------------------
@app.route("/upload", methods=["POST"])
def upload():
    if "pdf" not in request.files:
        return "No file uploaded", 400

    file = request.files["pdf"]
    if file.filename == "":
        return "No file selected", 400

    # Original PDF ko temporary save karein
    filepath = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(filepath)

    def stream():
        yield json.dumps({"step": "Uploading PDF", "progress": 5}) + "\n"
        
        # Source PDF ko open karein
        doc = fitz.open(filepath)
        total_pages = len(doc)
        
        # Dictionary jisme sirf page numbers store honge (RAM bachegi)
        grouped = defaultdict(list)

        yield json.dumps({"step": "Reading PDF Pages", "progress": 10}) + "\n"

        # -----------------------------
        # PAGE PROCESSING LOOP
        # -----------------------------
        for i in range(total_pages):
            page = doc.load_page(i)
            sku = None

            # High-resolution (150 DPI) par page ki image banayein scanning ke liye
            try:
                pix = page.get_pixmap(dpi=150) 
                img_bytes = pix.tobytes("png")
                sku = get_sku_from_barcode(img_bytes)
            except Exception as e:
                print(f"Error rendering page {i}: {e}")
                sku = "UNKNOWN"

            if not sku:
                sku = "UNKNOWN"

            # Sirf page index save karein, heavy image bytes nahi!
            grouped[sku].append(i)

            # Progress percentage calculate karein (10% se 70% ke beech)
            progress = int(((i + 1) / total_pages) * 60) + 10
            yield json.dumps({
                "step": f"Processing Page {i+1}/{total_pages} | SKU: {sku}",
                "progress": progress
            }) + "\n"

        # -----------------------------
        # SORTING DATA
        # -----------------------------
        yield json.dumps({"step": "Sorting SKU Data", "progress": 75}) + "\n"
        # UNKNOWN waale pages ko sabse aakhiri mein rakhne ke liye sort logic
        sorted_keys = sorted(grouped.keys(), key=lambda x: (x == "UNKNOWN", x))

        # -----------------------------
        # NEW PDF GENERATION (Fast & Lossless)
        # -----------------------------
        yield json.dumps({"step": "Generating Output PDF", "progress": 85}) + "\n"
        
        out_doc = fitz.open() # Naya blank PDF banayein
        output_file = os.path.join(OUTPUT_FOLDER, "SORTED_" + file.filename)

        for sku in sorted_keys:
            page_indices = group = grouped[sku]
            
            # Direct original PDF se naye PDF mein bina quality loss ke pages copy karein
            out_doc.insert_pdf(doc, from_page=page_indices[0], to_page=page_indices[-1], select=page_indices)
            
            # Har SKU ke baad ek Separator/Summary Page lagayein
            summary_page = out_doc.new_page(width=595, height=842) # A4 size standard
            summary_page.insert_text((150, 400), f"SKU: {sku}", fontsize=24, fontname="helv-bold")
            summary_page.insert_text((150, 440), f"TOTAL LABELS: {len(page_indices)}", fontsize=20, fontname="helv")

        # PDF ko optimize karke save karein taaki size chota rahe
        out_doc.save(output_file, garbage=3, deflate=True)
        out_doc.close()
        doc.close()

        # Kaam hone ke baad original heavy uploaded file delete karein space bachane ke liye
        if os.path.exists(filepath):
            os.remove(filepath)

        # Frontend ko download link bheinjiye
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

# -----------------------------
# RUN APPLICATION
# -----------------------------
if __name__ == "__main__":
    app.run(debug=False)