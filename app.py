from flask import Flask, render_template, request, send_file
import fitz
import requests
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

# =========================================
# SKU FIND FUNCTION
# =========================================

def extract_sku(text):

    text = text.upper()

    patterns = [

        r'SKU\s*[:\-]?\s*([A-Z0-9\-_]+)',

        r'SELLER SKU\s*[:\-]?\s*([A-Z0-9\-_]+)',

        r'FSN\s*[:\-]?\s*([A-Z0-9\-_]+)',

        r'([A-Z]{2,}[0-9]{2,}[A-Z0-9\-_]*)'
    ]

    for pattern in patterns:

        match = re.search(pattern, text)

        if match:

            sku = match.group(1).strip()

            if len(sku) > 2:

                return sku

    return "ZZZ"

# =========================================
# HOME PAGE
# =========================================

@app.route("/")
def home():

    return render_template("index.html")

# =========================================
# UPLOAD + SORT
# =========================================

@app.route("/upload", methods=["POST"])
def upload():

    try:

        file = request.files["pdf"]

        if file.filename == "":
            return "NO FILE SELECTED"

        filepath = os.path.join(
            UPLOAD_FOLDER,
            file.filename
        )

        file.save(filepath)

        # =========================================
        # OPEN PDF
        # =========================================

        doc = fitz.open(filepath)

        total_pages = len(doc)

        grouped = defaultdict(list)

        print("PROCESS STARTED")

        # =========================================
        # PAGE LOOP
        # =========================================

        for page_num in range(total_pages):

            page = doc.load_page(page_num)

            # FAST IMAGE
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

            except Exception as e:

                print("OCR ERROR :", e)

                text = ""

            # =========================================
            # FIND SKU
            # =========================================

            sku = extract_sku(text)

            grouped[sku].append(img_data)

            # =========================================
            # TERMINAL PROGRESS
            # =========================================

            percent = int(
                ((page_num + 1) / total_pages) * 100
            )

            print(
                f"PROCESSING : {percent}% "
                f"({page_num + 1}/{total_pages}) "
                f"SKU : {sku}"
            )

        # =========================================
        # OUTPUT PDF
        # =========================================

        output_pdf = os.path.join(
            OUTPUT_FOLDER,
            "SORTED_" + file.filename
        )

        c = canvas.Canvas(output_pdf)

        sorted_skus = sorted(grouped.keys())

        # =========================================
        # SORTING PDF
        # =========================================

        for sku in sorted_skus:

            items = grouped[sku]

            # =========================================
            # LABEL PAGES
            # =========================================

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

            # =========================================
            # SUMMARY PAGE
            # =========================================

            c.setFont(
                "Helvetica-Bold",
                28
            )

            c.drawString(
                120,
                500,
                f"SKU : {sku}"
            )

            c.drawString(
                120,
                440,
                f"TOTAL LABELS : {len(items)}"
            )

            c.showPage()

        # =========================================
        # SAVE PDF
        # =========================================

        c.save()

        print("DONE SUCCESSFULLY")

        # =========================================
        # DOWNLOAD
        # =========================================

        return send_file(
            output_pdf,
            as_attachment=True
        )

    except Exception as e:

        print("MAIN ERROR :", e)

        return f"ERROR : {str(e)}"

# =========================================
# RUN
# =========================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=10000
    )