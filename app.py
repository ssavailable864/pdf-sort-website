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


# ---------------------------------
# SKU EXTRACT FUNCTION
# ---------------------------------
def extract_sku(text):

    text = text.replace("\n", " ")
    text_upper = text.upper()

    patterns = [

        # MAIN SKU LINE
        r"SKU\s+([A-Z0-9_-]{5,})",

        # BACKUP
        r"SKU\s*[:\-]?\s*([A-Z0-9_-]{5,})",

    ]

    reject_words = [

        "SIZE",
        "COLOR",
        "QTY",
        "FREE",
        "NA",
        "ORDER",
        "SHADOWFAX",
        "PREPAID",
        "PICKUP",
        "INVOICE",
        "DETAILS"

    ]

    for pattern in patterns:

        matches = re.findall(
            pattern,
            text_upper,
            re.IGNORECASE
        )

        for sku in matches:

            sku = sku.strip()

            # -----------------------------
            # REJECT BAD VALUES
            # -----------------------------
            if sku in reject_words:
                continue

            # TRACKING IDS
            if sku.startswith("SF"):
                continue

            # ADDRESS
            if "NO24A" in sku:
                continue

            # VERY LONG VALUES
            if len(sku) > 25:
                continue

            # VALID SKU
            return sku

    return "UNKNOWN"


# ---------------------------------
# HOME PAGE
# ---------------------------------
@app.route("/")
def home():
    return render_template("index.html")


# ---------------------------------
# PDF UPLOAD
# ---------------------------------
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

        print("TOTAL PAGES :", total_pages)

        # ---------------------------------
        # READ EVERY PAGE
        # ---------------------------------
        for page_num in range(total_pages):

            page = doc.load_page(page_num)

            # DIRECT PDF TEXT
            text = page.get_text()

            sku = extract_sku(text)

            print(f"PAGE {page_num+1} SKU => {sku}")

            # PAGE IMAGE
            pix = page.get_pixmap(dpi=200)

            img_data = pix.tobytes("png")

            grouped[sku].append(img_data)

        # ---------------------------------
        # OUTPUT PDF
        # ---------------------------------
        output_pdf = os.path.join(
            OUTPUT_FOLDER,
            "SORTED_" + file.filename
        )

        c = canvas.Canvas(output_pdf)

        # SORT SKU WISE
        for sku in sorted(grouped.keys()):

            items = grouped[sku]

            # -----------------------------
            # LABEL PAGES
            # -----------------------------
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

            # -----------------------------
            # SUMMARY PAGE
            # -----------------------------
            c.setFont(
                "Helvetica-Bold",
                28
            )

            c.drawString(
                170,
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


# ---------------------------------
# RUN
# ---------------------------------
if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=10000,
        debug=False
    )