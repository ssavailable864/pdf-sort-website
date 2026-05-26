from flask import Flask, render_template, request, send_file
import fitz
import io
import os
import re

from collections import defaultdict

from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

app = Flask(__name__)

UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "output"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)


# -----------------------------------
# CLEAN SKU DETECTION
# -----------------------------------
def extract_sku(text):

    text = text.replace("\r", "\n")

    lines = text.split("\n")

    blacklist = [
        "SIZE",
        "ORDER",
        "TRACK",
        "TRACKING",
        "SHIP",
        "DELIVERY",
        "COD",
        "PAID",
        "QTY",
        "TOTAL",
        "AMOUNT",
        "SELLER",
        "RETURN",
        "DATE"
    ]

    for i, line in enumerate(lines):

        line_upper = line.upper().strip()

        # SKU line mila
        if "SKU" in line_upper:

            # next 3 lines check karo
            for j in range(1, 4):

                if i + j >= len(lines):
                    continue

                possible = lines[i + j].strip().upper()

                possible = re.sub(r'[^A-Z0-9\-_ ]', '', possible)

                if len(possible) < 4:
                    continue

                # blacklist ignore
                bad = False

                for word in blacklist:
                    if word in possible:
                        bad = True
                        break

                if bad:
                    continue

                # tracking id ignore
                if re.fullmatch(r"[A-Z]{2,5}[0-9]{8,}", possible):
                    continue

                # courier code ignore
                if re.fullmatch(r"[A-Z]{2,5}\-[A-Z0-9]{1,5}", possible):
                    continue

                return possible

    return "UNKNOWN"


# -----------------------------------
# HOME
# -----------------------------------
@app.route("/")
def home():
    return render_template("index.html")


# -----------------------------------
# UPLOAD
# -----------------------------------
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

        # -----------------------------------
        # PAGE LOOP
        # -----------------------------------
        for page_num in range(len(doc)):

            page = doc.load_page(page_num)

            # DIRECT TEXT
            text = page.get_text()

            sku = extract_sku(text)

            print("PAGE", page_num + 1)
            print("FOUND SKU :", sku)

            pdf_bytes = page.parent.convert_to_pdf()

            grouped[sku].append(page_num)

        # -----------------------------------
        # OUTPUT PDF
        # -----------------------------------
        output_pdf = os.path.join(
            OUTPUT_FOLDER,
            "SORTED_" + file.filename
        )

        new_doc = fitz.open()

        # SORTING
        for sku in sorted(grouped.keys()):

            pages = grouped[sku]

            # add pages
            for pno in pages:

                new_doc.insert_pdf(
                    doc,
                    from_page=pno,
                    to_page=pno
                )

            # summary page
            summary = fitz.open()

            page = summary.new_page()

            page.insert_text(
                (170, 300),
                f"SKU : {sku}",
                fontsize=28
            )

            page.insert_text(
                (170, 350),
                f"TOTAL LABELS : {len(pages)}",
                fontsize=24
            )

            new_doc.insert_pdf(summary)

        new_doc.save(output_pdf)

        return send_file(
            output_pdf,
            as_attachment=True
        )

    except Exception as e:

        return f"ERROR : {str(e)}"


# -----------------------------------
# RUN
# -----------------------------------
if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=10000,
        debug=False
    )