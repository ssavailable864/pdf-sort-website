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
# SKU DETECTION
# -------------------------------------------------
def extract_sku(text):

    lines = text.split("\n")

    blocked = [
        "SIZE",
        "COLOR",
        "QTY",
        "FREE",
        "NO24A",
        "NA"
    ]

    for i in range(len(lines)):

        line = lines[i].strip().upper()

        # -------------------------
        # FIND SKU LINE
        # -------------------------
        if line == "SKU":

            # NEXT LINE VALUE
            if i + 1 < len(lines):

                next_line = lines[i + 1].strip()

                next_line_upper = next_line.upper()

                # BLOCK WRONG VALUES
                if next_line_upper in blocked:
                    continue

                # TRACKING ID BLOCK
                if next_line_upper.startswith("SF"):
                    continue

                # VALID SKU
                if len(next_line) >= 4:
                    return next_line

        # -------------------------
        # SKU : VALUE
        # -------------------------
        match = re.search(
            r"SKU\s*[:\-]?\s*([A-Z0-9_ -]+)",
            line,
            re.I
        )

        if match:

            sku = match.group(1).strip()

            sku_upper = sku.upper()

            if sku_upper in blocked:
                continue

            if sku_upper.startswith("SF"):
                continue

            if len(sku) >= 4:
                return sku

    return "UNKNOWN"


# -------------------------------------------------
# HOME
# -------------------------------------------------
@app.route("/")
def home():

    return render_template("index.html")


# -------------------------------------------------
# UPLOAD
# -------------------------------------------------
@app.route("/upload", methods=["POST"])
def upload():

    try:

        file = request.files["pdf"]

        if file.filename == "":
            return "NO FILE"

        filepath = os.path.join(
            UPLOAD_FOLDER,
            file.filename
        )

        file.save(filepath)

        doc = fitz.open(filepath)

        grouped = defaultdict(list)

        # -------------------------------------
        # READ ALL PAGES
        # -------------------------------------
        for page_num in range(len(doc)):

            page = doc.load_page(page_num)

            # TEXT
            text = page.get_text()

            print(text)

            # FIND SKU
            sku = extract_sku(text)

            print("FOUND SKU =", sku)

            # IMAGE
            pix = page.get_pixmap(dpi=200)

            img_data = pix.tobytes("png")

            grouped[sku].append(img_data)

        # -------------------------------------
        # OUTPUT PDF
        # -------------------------------------
        output_pdf = os.path.join(
            OUTPUT_FOLDER,
            "SORTED_" + file.filename
        )

        c = canvas.Canvas(output_pdf)

        # SORT SKU WISE
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

            # SUMMARY PAGE
            c.setFont(
                "Helvetica-Bold",
                28
            )

            c.drawString(
                130,
                550,
                f"SKU : {sku}"
            )

            c.drawString(
                100,
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
# RUN
# -------------------------------------------------
if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=10000,
        debug=False
    )