from flask import Flask, render_template, request, send_file
import fitz
import pytesseract
from PIL import Image as PILImage
import io
import re
import os

from collections import defaultdict

from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

app = Flask(__name__)

UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "output"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

def extract_sku(text):

    patterns = [
        r'SKU\s*[:\-]?\s*([A-Z0-9_-]+)',
        r'Seller SKU\s*[:\-]?\s*([A-Z0-9_-]+)',
    ]

    for pattern in patterns:

        match = re.search(pattern, text, re.I)

        if match:
            return match.group(1)

    return "ZZZ"

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/upload", methods=["POST"])
def upload():

    file = request.files["pdf"]

    filepath = os.path.join(
        UPLOAD_FOLDER,
        file.filename
    )

    file.save(filepath)

    doc = fitz.open(filepath)

    grouped = defaultdict(list)

    for page_num in range(len(doc)):

        page = doc.load_page(page_num)

        pix = page.get_pixmap(dpi=200)

        img_data = pix.tobytes("png")

        image = PILImage.open(io.BytesIO(img_data))

        text = pytesseract.image_to_string(image)

        sku = extract_sku(text)

        grouped[sku].append(img_data)

    output_pdf = os.path.join(
        OUTPUT_FOLDER,
        "SORTED_" + file.filename
    )

    c = canvas.Canvas(output_pdf)

    for sku in sorted(grouped.keys()):

        items = grouped[sku]

        for img in items:

            image_reader = ImageReader(io.BytesIO(img))

            c.drawImage(
                image_reader,
                0,
                0,
                width=595,
                height=842
            )

            c.showPage()

        c.setFont("Helvetica-Bold", 24)

        c.drawString(
            180,
            500,
            f"SKU : {sku}"
        )

        c.drawString(
            180,
            450,
            f"TOTAL LABELS : {len(items)}"
        )

        c.showPage()

    c.save()

    return send_file(
        output_pdf,
        as_attachment=True
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)