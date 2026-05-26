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
# SKU FIND FUNCTION
# -------------------------------------------------
def extract_sku(text):

    text = text.upper()

    # --------------------------------
    # SKU ke niche wala text pakdega
    # --------------------------------
    match = re.search(

        r"SKU\s+([A-Z0-9_-]+)",

        text,

        re.MULTILINE

    )

    if match:

        sku = match.group(1).strip()

        ignore = [
            "SIZE",
            "COLOR",
            "QTY",
            "FREE",
            "NA"
        ]

        if sku not in ignore:

            return sku

    # --------------------------------
    # Backup direct pattern
    # Example:
    # 188042787_70
    # --------------------------------
    match2 = re.search(

        r"\b\d{6,}[_-]\d+\b",

        text

    )

    if match2:

        return match2.group(0)

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

        print("TOTAL PAGES :", total_pages)

        # -------------------------------------------------
        # READ ALL PAGES
        # -------------------------------------------------
        for page_num in range(total_pages):

            page = doc.load_page(page_num)

            # ---------------------------------------------
            # DIRECT PDF TEXT
            # ---------------------------------------------
            text = page.get_text()

            sku = extract_sku(text)

            print(

                f"PAGE {page_num+1} => SKU : {sku}"

            )

            # ---------------------------------------------
            # PAGE IMAGE
            # ---------------------------------------------
            pix = page.get_pixmap(dpi=200)

            img_data = pix.tobytes("png")

            grouped[sku].append(img_data)

        # -------------------------------------------------
        # OUTPUT PDF
        # -------------------------------------------------
        output_pdf = os.path.join(

            OUTPUT_FOLDER,

            "SORTED_" + file.filename

        )

        c = canvas.Canvas(output_pdf)

        # -------------------------------------------------
        # SORT SKU WISE
        # -------------------------------------------------
        for sku in sorted(grouped.keys()):

            items = grouped[sku]

            print("WRITING SKU :", sku)

            # ---------------------------------------------
            # LABEL PAGES
            # ---------------------------------------------
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

            # ---------------------------------------------
            # SUMMARY PAGE
            # ---------------------------------------------
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


# -------------------------------------------------
# RUN APP
# -------------------------------------------------
if __name__ == "__main__":

    app.run(

        host="0.0.0.0",

        port=10000,

        debug=False

    )