from flask import Flask, render_template, request, send_file
import fitz
import requests
from PIL import Image as PILImage
import io
import re
import os

from collections import defaultdict

from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

app = Flask(__name__)

# =====================================
# FOLDERS
# =====================================

UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "output"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# =====================================
# SKU FIND FUNCTION
# =====================================

def extract_sku(text):

    patterns = [

        r'FNSKU\s*[:\-]?\s*([A-Z0-9_-]+)',

        r'ASIN\s*[:\-]?\s*([A-Z0-9_-]+)',

        r'SKU\s*[:\-]?\s*([A-Z0-9_-]+)',

        r'Seller SKU\s*[:\-]?\s*([A-Z0-9_-]+)',

    ]

    for pattern in patterns:

        match = re.search(pattern, text, re.I)

        if match:
            return match.group(1)

    return "ZZZ"

# =====================================
# HOME PAGE
# =====================================

@app.route("/")
def home():

    return render_template("index.html")

# =====================================
# PDF UPLOAD + SORT
# =====================================

@app.route("/upload", methods=["POST"])
def upload():

    try:

        file = request.files["pdf"]

        if not file:
            return "No File Selected"

        filepath = os.path.join(
            UPLOAD_FOLDER,
            file.filename
        )

        file.save(filepath)

        # =====================================
        # OPEN PDF
        # =====================================

        doc = fitz.open(filepath)

        grouped = defaultdict(list)

        total_pages = len(doc)

        # =====================================
        # OCR PROCESS
        # =====================================

        for page_num in range(total_pages):

            try:

                print(f"PAGE : {page_num + 1}")

                page = doc.load_page(page_num)

                # BETTER QUALITY
                pix = page.get_pixmap(dpi=200)

                img_data = pix.tobytes("png")

                image = PILImage.open(
                    io.BytesIO(img_data)
                )

                # =====================================
                # OCR API
                # =====================================

                response = requests.post(

                    "https://api.ocr.space/parse/image",

                    files={
                        "filename": img_data
                    },

                    data={
                        "apikey": "helloworld",
                        "language": "eng",
                        "OCREngine": 2
                    }

                )

                result = response.json()

                text = ""

                if result.get("ParsedResults"):

                    text = result["ParsedResults"][0]["ParsedText"]

                # =====================================
                # DEBUG OCR TEXT
                # =====================================

                print("========== OCR TEXT ==========")
                print(text)

                # =====================================
                # SKU FIND
                # =====================================

                sku = extract_sku(text)

                print("FOUND SKU :", sku)

                grouped[sku].append(img_data)

            except Exception as page_error:

                print("PAGE ERROR :", page_num + 1)

                print(str(page_error))

        # =====================================
        # OUTPUT PDF
        # =====================================

        output_pdf = os.path.join(

            OUTPUT_FOLDER,

            "SORTED_" + file.filename

        )

        c = canvas.Canvas(output_pdf)

        # =====================================
        # SORTING
        # =====================================

        for sku in sorted(grouped.keys()):

            items = grouped[sku]

            # =====================================
            # LABEL PAGES
            # =====================================

            for img in items:

                image_reader = ImageReader(
                    io.BytesIO(img)
                )

                c.drawImage(

                    image_reader,

                    0,
                    0,

                    width=595,
                    height=842

                )

                c.showPage()

            # =====================================
            # SUMMARY PAGE
            # =====================================

            c.setFont(
                "Helvetica-Bold",
                24
            )

            c.drawString(
                150,
                500,
                f"SKU : {sku}"
            )

            c.drawString(
                150,
                450,
                f"TOTAL LABELS : {len(items)}"
            )

            c.showPage()

        # =====================================
        # SAVE PDF
        # =====================================

        c.save()

        # =====================================
        # RETURN PDF
        # =====================================

        return send_file(

            output_pdf,

            as_attachment=True

        )

    except Exception as e:

        return f"ERROR : {str(e)}"

# =====================================
# RUN APP
# =====================================

if __name__ == "__main__":

    app.run(

        host="0.0.0.0",

        port=10000,

        debug=False

    )