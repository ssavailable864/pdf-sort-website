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


# ---------------------------------------------------
# SKU FIND FUNCTION
# ---------------------------------------------------
def extract_sku(text):

    text = text.upper()

    patterns = [

        r"SELLER SKU\s*[:\-]?\s*([A-Z0-9_-]+)",

        r"SKU\s*[:\-]?\s*([A-Z0-9_-]+)",

        r"SKU\s*\n\s*([A-Z0-9_-]+)"

    ]

    blocked = [

        "SIZE",
        "COLOR",
        "FREE",
        "QTY",
        "NO24A",
        "NA",
        "NEW"

    ]

    for pattern in patterns:

        matches = re.findall(pattern, text)

        for sku in matches:

            sku = sku.strip()

            # BLOCK EMPTY
            if not sku:
                continue

            # BLOCK COMMON WORDS
            if sku in blocked:
                continue

            # BLOCK TRACKING IDS
            if sku.startswith("SF"):
                continue

            # BLOCK VERY LONG IDS
            if len(sku) > 20:
                continue

            # VALID SKU
            if len(sku) >= 4:
                return sku

    return "UNKNOWN"


# ---------------------------------------------------
# HOME PAGE
# ---------------------------------------------------
@app.route("/")
def home():

    return render_template("index.html")


# ---------------------------------------------------
# UPLOAD PDF
# ---------------------------------------------------
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

        # ---------------------------------------------------
        # READ ALL PAGES
        # ---------------------------------------------------
        for page_num in range(total_pages):

            page = doc.load_page(page_num)

            # SMALL DPI = FAST + SMALL PDF
            pix = page.get_pixmap(dpi=120)

            # JPEG = SMALLER FILE
            img_data = pix.tobytes("jpeg")

            image = PILImage.open(io.BytesIO(img_data))

            # ---------------------------------------------------
            # OCR API
            # ---------------------------------------------------
            try:

                response = requests.post(
                    "https://api.ocr.space/parse/image",
                    files={
                        "filename": (
                            "page.jpg",
                            img_data,
                            "image/jpeg"
                        )
                    },
                    data={
                        "apikey": "helloworld",
                        "language": "eng"
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

            # ---------------------------------------------------
            # FIND SKU
            # ---------------------------------------------------
            sku = extract_sku(text)

            print("PAGE :", page_num + 1)
            print("FOUND SKU :", sku)

            grouped[sku].append(img_data)

        # ---------------------------------------------------
        # OUTPUT PDF
        # ---------------------------------------------------
        output_pdf = os.path.join(
            OUTPUT_FOLDER,
            "SORTED_" + file.filename
        )

        # PDF COMPRESSION
        c = canvas.Canvas(
            output_pdf,
            pageCompression=1
        )

        # ---------------------------------------------------
        # SORT SKU WISE
        # ---------------------------------------------------
        for sku in sorted(grouped.keys()):

            items = grouped[sku]

            # LABEL PAGES
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

            # ---------------------------------------------------
            # SUMMARY PAGE
            # ---------------------------------------------------
            c.setFont(
                "Helvetica-Bold",
                28
            )

            c.drawString(
                160,
                550,
                f"SKU : {sku}"
            )

            c.drawString(
                110,
                470,
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


# ---------------------------------------------------
# RUN APP
# ---------------------------------------------------
if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=10000,
        debug=False
    )