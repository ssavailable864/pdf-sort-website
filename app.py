from flask import Flask, render_template, request, send_file
import fitz
import requests
import io
import re
import os
import time

from collections import defaultdict

from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

app = Flask(__name__)

UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "output"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# =========================================
# SKU FIND
# =========================================

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

# =========================================
# HOME
# =========================================

@app.route("/")
def home():

    return render_template("index.html")

# =========================================
# UPLOAD
# =========================================

@app.route("/upload", methods=["POST"])
def upload():

    try:

        file = request.files["pdf"]

        filepath = os.path.join(
            UPLOAD_FOLDER,
            file.filename
        )

        file.save(filepath)

        doc = fitz.open(filepath)

        total_pages = len(doc)

        grouped = defaultdict(list)

        # =========================================
        # PROCESS PAGES
        # =========================================

        for page_num in range(total_pages):

            page = doc.load_page(page_num)

            # FAST RENDER
            pix = page.get_pixmap(dpi=70)

            img_data = pix.tobytes("png")

            # =========================================
            # OCR API
            # =========================================

            try:

                response = requests.post(
                    "https://api.ocr.space/parse/image",
                    files={
                        "filename": (
                            "page.png",
                            img_data,
                            "image/png"
                        )
                    },
                    data={
                        "apikey": "helloworld",
                        "language": "eng",
                        "OCREngine": "2"
                    },
                    timeout=20
                )

                result = response.json()

                text = ""

                if result.get("ParsedResults"):

                    text = result["ParsedResults"][0]["ParsedText"]

                else:

                    text = ""

            except:

                text = ""

            # =========================================
            # FIND SKU
            # =========================================

            sku = extract_sku(text)

            grouped[sku].append(img_data)

            # TERMINAL PROGRESS
            percent = int(((page_num + 1) / total_pages) * 100)

            print(
                f"PROCESSING : {percent}% "
                f"({page_num + 1}/{total_pages})"
            )

        # =========================================
        # OUTPUT PDF
        # =========================================

        output_pdf = os.path.join(
            OUTPUT_FOLDER,
            "SORTED_" + file.filename
        )

        c = canvas.Canvas(output_pdf)

        # =========================================
        # SORT SKU
        # =========================================

        sorted_skus = sorted(grouped.keys())

        for sku in sorted_skus:

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

        c.save()

        print("DONE SUCCESSFULLY")

        # =========================================
        # RETURN PDF
        # =========================================

        return send_file(
            output_pdf,
            as_attachment=True
        )

    except Exception as e:

        return f"ERROR : {str(e)}"

# =========================================
# RUN
# =========================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=10000
    )