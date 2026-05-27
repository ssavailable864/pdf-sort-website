from flask import Flask, request, send_file, render_template, Response
import fitz
import os
import io
import cv2
import numpy as np
from pyzbar.pyzbar import decode
from collections import defaultdict
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
import json
import time

app = Flask(__name__)

UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "output"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)


# -----------------------------
# BARCODE DETECTOR
# -----------------------------
def get_sku_from_barcode(image_bytes):
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    barcodes = decode(img)

    for barcode in barcodes:
        try:
            return barcode.data.decode("utf-8").strip()
        except:
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

    file = request.files["pdf"]

    filepath = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(filepath)

    doc = fitz.open(filepath)

    grouped = defaultdict(list)

    total_pages = len(doc)

    def stream():

        # STEP 1
        yield json.dumps({"step": "Uploading PDF", "progress": 5}) + "\n"
        time.sleep(0.3)

        # STEP 2
        yield json.dumps({"step": "Reading PDF Pages", "progress": 10}) + "\n"

        # -----------------------------
        # PAGE PROCESSING
        # -----------------------------
        for i in range(total_pages):

            page = doc.load_page(i)

            pix = page.get_pixmap(dpi=200)
            img_bytes = pix.tobytes("png")

            sku = get_sku_from_barcode(img_bytes)

            if not sku:
                sku = "UNKNOWN"

            grouped[sku].append(img_bytes)

            progress = int(((i + 1) / total_pages) * 60)

            yield json.dumps({
                "step": f"Processing Page {i+1}/{total_pages} | SKU: {sku}",
                "progress": progress
            }) + "\n"

            time.sleep(0.05)

        # -----------------------------
        # SORTING
        # -----------------------------
        yield json.dumps({"step": "Sorting SKU Data", "progress": 75}) + "\n"
        time.sleep(0.5)

        sorted_keys = sorted(grouped.keys(), key=lambda x: (x == "UNKNOWN", x))

        # -----------------------------
        # PDF GENERATION
        # -----------------------------
        yield json.dumps({"step": "Generating Output PDF", "progress": 85}) + "\n"

        output_file = os.path.join(OUTPUT_FOLDER, "SORTED_" + file.filename)
        c = canvas.Canvas(output_file)

        for sku in sorted_keys:

            items = grouped[sku]

            # images
            for img in items:
                c.drawImage(ImageReader(io.BytesIO(img)), 0, 0, 595, 842)
                c.showPage()

            # SKU summary page
            c.setFont("Helvetica-Bold", 26)
            c.drawString(180, 550, f"SKU: {sku}")
            c.drawString(180, 500, f"TOTAL: {len(items)}")
            c.showPage()

        c.save()

        # -----------------------------
        # COMPLETED
        # -----------------------------
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


# -----------------------------
# RUN APP
# -----------------------------
if __name__ == "__main__":
    app.run(debug=False)