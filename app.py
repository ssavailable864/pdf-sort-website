from flask import Flask, render_template, request, send_file
import fitz
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


# -------------------------------------------------
# FAST SKU DETECTION
# -------------------------------------------------
def extract_sku(text):

    text = text.upper()

    patterns = [

        r"SKU\s*[:\-]?\s*([A-Z0-9_-]+)",

        r"SELLER SKU\s*[:\-]?\s*([A-Z0-9_-]+)",

        r"SKU\s*\n\s*([A-Z0-9_-]+)"

    ]

    blocked = [

        "SIZE",
        "COLOR",
        "FREE",
        "QTY",
        "NO24A",
        "NA"

    ]

    for pattern in patterns:

        matches = re.findall(pattern, text)

        for sku in matches:

            sku = sku.strip()

            # BLOCK WRONG VALUES
            if sku in blocked:
                continue

            # BLOCK TRACKING IDS
            if sku.startswith("SF"):
                continue

            # BLOCK LONG IDS
            if len(sku) > 25:
                continue

            if len(sku) >= 4:
                return sku

    return "UNKNOWN"


# -------------------------------------------------
# HOME PAGE
# -------------------------------------------------
@app.route("/")
def home():

    return render_template("index.html")


# -------------------------------------------------
# UPLOAD PDF
# -------------------------------------------------
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

        # -----------------------------------------
        # READ ALL PAGES FAST
        # -----------------------------------------
        for page_num in range(total_pages):

            page = doc.load_page(page_num)

            # FAST DIRECT TEXT
            text = page.get_text()

            # FIND SKU
            sku = extract_sku(text)

            print("PAGE :", page_num + 1)
            print("FOUND SKU :", sku)

            # SMALLER IMAGE SIZE
            pix = page.get_pixmap(
                dpi=120
            )

            img_data = pix.tobytes("jpeg")

            grouped[sku].append(img_data)

        # -----------------------------------------
        # OUTPUT PDF
        # -----------------------------------------
        output_pdf = os.path.join(
            OUTPUT_FOLDER,
            "SORTED_" + file.filename
        )

        # PDF COMPRESSION
        c = canvas.Canvas(
            output_pdf,
            pageCompression=1
        )

        # -----------------------------------------
        # SORT SKU WISE
        # -----------------------------------------
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

            # ---------------------------------
            # SUMMARY PAGE
            # ---------------------------------
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
                120,
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


# -------------------------------------------------
# RUN APP
# -------------------------------------------------
if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=10000,
        debug=False
    )