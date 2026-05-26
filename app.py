from flask import Flask, render_template, request, send_file
import fitz
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


# ---------------------------------------------------
# REAL SKU DETECTION
# ---------------------------------------------------
def extract_sku(text):

    # CLEAN TEXT
    text = text.replace("\n", " ")
    text = text.replace("\r", " ")

    # REMOVE EXTRA SPACES
    text = re.sub(r"\s+", " ", text)

    # ----------------------------------------
    # TRY TO FIND SKU AFTER "SKU"
    # ----------------------------------------
    patterns = [

        # SKU 535971583_67
        r"SKU\s+([0-9]{6,}_[0-9]+)",

        # SKU APCD07
        r"SKU\s+([A-Z0-9]{4,})",

        # Product Details SKU 535971583_67
        r"Product Details.*?SKU\s+([A-Z0-9_-]+)",

    ]

    blocked_words = [

        "SIZE",
        "COLOR",
        "QTY",
        "FREE",
        "NA",
        "NO24A",
        "TS_AN",
        "S46_SME"

    ]

    for pattern in patterns:

        match = re.search(pattern, text, re.I)

        if match:

            sku = match.group(1).strip().upper()

            # REMOVE WRONG VALUES
            if sku not in blocked_words:

                # TRACKING ID BLOCK
                if not sku.startswith("SF"):

                    # VERY LONG NUMBER BLOCK
                    if len(sku) < 25:

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

        # ----------------------------------------
        # READ ALL PAGES
        # ----------------------------------------
        for page_num in range(total_pages):

            page = doc.load_page(page_num)

            # DIRECT TEXT EXTRACTION
            text = page.get_text()

            # FIND SKU
            sku = extract_sku(text)

            print("PAGE :", page_num + 1)
            print("FOUND SKU :", sku)

            # PAGE IMAGE
            pix = page.get_pixmap(dpi=200)

            img_data = pix.tobytes("png")

            grouped[sku].append(img_data)

        # ----------------------------------------
        # OUTPUT PDF
        # ----------------------------------------
        output_pdf = os.path.join(
            OUTPUT_FOLDER,
            "SORTED_" + file.filename
        )

        c = canvas.Canvas(output_pdf)

        # ----------------------------------------
        # SORT SKU WISE
        # ----------------------------------------
        for sku in sorted(grouped.keys()):

            items = grouped[sku]

            # -----------------------------
            # LABEL PAGES
            # -----------------------------
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

            # -----------------------------
            # SUMMARY PAGE
            # -----------------------------
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


# ---------------------------------------------------
# RUN APP
# ---------------------------------------------------
if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=10000,
        debug=False
    )