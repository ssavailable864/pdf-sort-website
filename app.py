from flask import Flask, render_template, request, send_file
import fitz
from PIL import Image as PILImage
import io
import re
import os
from collections import defaultdict
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
import requests

app = Flask(__name__)

UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "output"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)


# ------------------------------------
# SKU EXTRACT FUNCTION
# ------------------------------------
def extract_sku(text):

    text = text.upper()

    patterns = [

        r"SKU\s*[:\-]?\s*([A-Z0-9_-]+)",

        r"SKU\s*\n\s*([A-Z0-9_-]+)",

        r"SELLER SKU\s*[:\-]?\s*([A-Z0-9_-]+)",

        # direct sku number
        r"\b\d{6,}[_-]\d+\b"

    ]

    for pattern in patterns:

        match = re.search(pattern, text)

        if match:

            if match.groups():
                sku = match.group(1).strip()
            else:
                sku = match.group(0).strip()

            if len(sku) > 3:
                return sku

    return "ZZZ"


# ------------------------------------
# HOME
# ------------------------------------
@app.route("/")
def home():
    return render_template("index.html")


# ------------------------------------
# UPLOAD
# ------------------------------------
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

        doc = fitz.open(filepath)

        grouped = defaultdict(list)

        total_pages = len(doc)

        # ------------------------------------
        # PAGE LOOP
        # ------------------------------------
        for page_num in range(total_pages):

            page = doc.load_page(page_num)

            # ------------------------------------
            # FIRST TRY DIRECT PDF TEXT
            # ------------------------------------
            text = page.get_text()

            sku = extract_sku(text)

            # ------------------------------------
            # IF NOT FOUND THEN OCR
            # ------------------------------------
            if sku == "ZZZ":

                pix = page.get_pixmap(dpi=200)

                img_data = pix.tobytes("png")

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
                            "language": "eng"
                        },
                        timeout=60
                    )

                    result = response.json()

                    ocr_text = ""

                    if result.get("ParsedResults"):

                        ocr_text = result["ParsedResults"][0]["ParsedText"]

                    sku = extract_sku(ocr_text)

                except Exception as e:

                    print("OCR ERROR :", e)

            print("PAGE", page_num + 1, "SKU :", sku)

            # ------------------------------------
            # SAVE IMAGE
            # ------------------------------------
            pix = page.get_pixmap(dpi=200)

            img_data = pix.tobytes("png")

            grouped[sku].append(img_data)

        # ------------------------------------
        # OUTPUT PDF
        # ------------------------------------
        output_pdf = os.path.join(
            OUTPUT_FOLDER,
            "SORTED_" + file.filename
        )

        c = canvas.Canvas(output_pdf)

        # ------------------------------------
        # SORT SKU WISE
        # ------------------------------------
        for sku in sorted(grouped.keys()):

            items = grouped[sku]

            # LABELS
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

            # ------------------------------------
            # SUMMARY PAGE
            # ------------------------------------
            c.setFont("Helvetica-Bold", 28)

            c.drawString(
                150,
                550,
                f"SKU : {sku}"
            )

            c.drawString(
                120,
                480,
                f"TOTAL LABELS : {len(items)}"
            )

            c.showPage()

        c.save()

        return send_file(
            output_pdf,
            as_attachment=True
        )

    except Exception as e:

        return f"ERROR : {str(e)}"


# ------------------------------------
# RUN
# ------------------------------------
if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=10000,
        debug=False
    )