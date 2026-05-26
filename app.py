from flask import Flask, request, send_file, render_template
import fitz
import os
import io
import cv2
import numpy as np
from pyzbar.pyzbar import decode
from collections import defaultdict
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

app = Flask(__name__)

UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "output"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)


# -----------------------------
# BARCODE SKU DETECTOR (FASTEST)
# -----------------------------
def get_sku_from_barcode(image_bytes):
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    barcodes = decode(img)

    for barcode in barcodes:
        sku = barcode.data.decode("utf-8")
        return sku.strip()

    return None


# -----------------------------
# HOME
# -----------------------------
@app.route("/")
def home():
    return render_template("index.html")


# -----------------------------
# PROCESS PDF
# -----------------------------
@app.route("/upload", methods=["POST"])
def upload():
    file = request.files["pdf"]

    filepath = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(filepath)

    doc = fitz.open(filepath)

    grouped = defaultdict(list)

    # -----------------------------
    # FAST PROCESSING LOOP
    # -----------------------------
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)

        pix = page.get_pixmap(dpi=200)
        img_bytes = pix.tobytes("png")

        sku = get_sku_from_barcode(img_bytes)

        if not sku:
            sku = "UNKNOWN"

        print("PAGE:", page_num, "SKU:", sku)

        grouped[sku].append(img_bytes)

    # -----------------------------
    # OUTPUT PDF
    # -----------------------------
    output_file = os.path.join(OUTPUT_FOLDER, "SORTED_" + file.filename)
    c = canvas.Canvas(output_file)

    for sku in sorted(grouped.keys(), key=lambda x: (x == "UNKNOWN", x)):

        items = grouped[sku]

        for img in items:
            c.drawImage(ImageReader(io.BytesIO(img)), 0, 0, 595, 842)
            c.showPage()

        c.setFont("Helvetica-Bold", 26)
        c.drawString(180, 550, f"SKU: {sku}")
        c.drawString(150, 500, f"TOTAL: {len(items)}")
        c.showPage()

    c.save()

    return send_file(output_file, as_attachment=True)


# -----------------------------
# RUN
# -----------------------------
if __name__ == "__main__":
    app.run(debug=False)