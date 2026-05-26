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


# ------------------------------------------------------
# SKU FIND FUNCTION
# ------------------------------------------------------
def extract_sku(text):

    text = text.upper()

    # --------------------------------------------------
    # REMOVE EXTRA SPACES
    # --------------------------------------------------
    clean_text = text.replace("\n", " ")

    # --------------------------------------------------
    # IGNORE WORDS
    # --------------------------------------------------
    ignore = [
        "SIZE",
        "COLOR",
        "QTY",
        "FREE",
        "NA",
        "ITEM",
        "ORDER",
        "ID"
    ]

    # --------------------------------------------------
    # METHOD 1
    # SKU : APCD07
    # SELLER SKU : APCD07
    # --------------------------------------------------
    patterns = [

        r"SELLER\s*SKU\s*[:\-]?\s*([A-Z0-9\-_]+)",

        r"SKU\s*[:\-]?\s*([A-Z0-9\-_]+)",

        r"STYLE\s*CODE\s*[:\-]?\s*([A-Z0-9\-_]+)",

        r"ITEM\s*CODE\s*[:\-]?\s*([A-Z0-9\-_]+)"

    ]

    for pattern in patterns:

        match = re.search(pattern, clean_text)

        if match:

            sku = match.group(1).strip()

            if sku not in ignore:

                if len(sku) >= 4:

                    return sku

    # --------------------------------------------------
    # METHOD 2
    # FIND SKU LIKE APCD07
    # --------------------------------------------------
    matches = re.findall(

        r"\b[A-Z]{2,}[A-Z0-9\-_]{2,}\b",

        clean_text

    )

    for sku in matches:

        # ignore long ids
        if len(sku) > 25:
            continue

        # must contain number
        if not re.search(r"\d", sku):
            continue

        # ignore bad words
        bad_words = [
            "ORDER",
            "TRACK",
            "PHONE",
            "MOBILE",
            "PINCODE"
        ]

        skip = False

        for bad in bad_words:

            if bad in sku:
                skip = True

        if skip:
            continue

        return sku

    # --------------------------------------------------
    # METHOD 3
    # 188042787_70
    # --------------------------------------------------
    match2 = re.search(

        r"\d{6,}[_-]\d+",

        clean_text

    )

    if match2:

        return match2.group(0)

    return "UNKNOWN"


# ------------------------------------------------------
# HOME PAGE
# ------------------------------------------------------
@app.route("/")
def home():

    return render_template("index.html")


# ------------------------------------------------------
# UPLOAD PDF
# ------------------------------------------------------
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

        # --------------------------------------------------
        # READ ALL PAGES
        # --------------------------------------------------
        for page_num in range(total_pages):

            page = doc.load_page(page_num)

            # ----------------------------------------------
            # GET TEXT
            # ----------------------------------------------
            text = page.get_text()

            print("------------------------------------------------")

            print("PAGE :", page_num + 1)

            # ----------------------------------------------
            # FIND SKU
            # ----------------------------------------------
            sku = extract_sku(text)

            print("FOUND SKU :", sku)

            # ----------------------------------------------
            # PAGE IMAGE
            # ----------------------------------------------
            pix = page.get_pixmap(dpi=200)

            img_data = pix.tobytes("png")

            grouped[sku].append(img_data)

        # --------------------------------------------------
        # OUTPUT PDF
        # --------------------------------------------------
        output_pdf = os.path.join(

            OUTPUT_FOLDER,

            "SORTED_" + file.filename

        )

        c = canvas.Canvas(output_pdf)

        # --------------------------------------------------
        # SORT SKU WISE
        # --------------------------------------------------
        for sku in sorted(grouped.keys()):

            items = grouped[sku]

            print("WRITING SKU :", sku)

            # ----------------------------------------------
            # LABEL PAGES
            # ----------------------------------------------
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

            # ----------------------------------------------
            # SUMMARY PAGE
            # ----------------------------------------------
            c.setFont(
                "Helvetica-Bold",
                30
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

        print("PDF COMPLETE")

        return send_file(
            output_pdf,
            as_attachment=True
        )

    except Exception as e:

        print("ERROR :", str(e))

        return f"ERROR : {str(e)}"


# ------------------------------------------------------
# RUN APP
# ------------------------------------------------------
if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=10000,
        debug=False
    )