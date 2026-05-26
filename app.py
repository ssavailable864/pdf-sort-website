from flask import Flask, render_template, request, send_file
import fitz
import io
import os
import re
import requests

from PIL import Image

from collections import defaultdict

app = Flask(__name__)

UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "output"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)


# -----------------------------------
# CLEAN SKU
# -----------------------------------
def clean_sku(value):

    value = value.strip().upper()

    value = re.sub(
        r'[^A-Z0-9\-_]',
        '',
        value
    )

    blacklist = [
        "SIZE",
        "COLOR",
        "TRACK",
        "TRACKING",
        "ORDER",
        "SHIP",
        "COD",
        "PAID",
        "QTY",
        "TOTAL",
        "ITEM",
        "RETURN",
        "DELIVERY",
        "PRODUCT",
        "NAME",
        "SKU"
    ]

    if value in blacklist:
        return None

    if len(value) < 5:
        return None

    if value.isalpha():
        return None

    if value.isdigit():
        return None

    # tracking reject
    if re.fullmatch(r"[A-Z]{2,5}[0-9]{8,}", value):
        return None

    # courier reject
    if re.fullmatch(r"[A-Z]{2,5}\-[A-Z0-9]+", value):
        return None

    return value


# -----------------------------------
# EXTRACT SKU
# -----------------------------------
def extract_sku(text):

    lines = text.split("\n")

    for line in lines:

        words = line.split()

        for word in words:

            sku = clean_sku(word)

            if sku:
                return sku

    return None


# -----------------------------------
# OCR ONLY SKU AREA
# -----------------------------------
def ocr_sku_area(page):

    # -----------------------------------
    # CROP AREA
    # LEFT, TOP, RIGHT, BOTTOM
    # -----------------------------------

    rect = fitz.Rect(
        50,
        150,
        400,
        450
    )

    pix = page.get_pixmap(
        matrix=fitz.Matrix(3, 3),
        clip=rect
    )

    img_data = pix.tobytes("png")

    try:

        response = requests.post(
            "https://api.ocr.space/parse/image",
            files={
                "file": (
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

        text = ""

        if result.get("ParsedResults"):

            text = result["ParsedResults"][0]["ParsedText"]

        print("OCR TEXT:")
        print(text)

        sku = extract_sku(text)

        return sku

    except Exception as e:

        print("OCR ERROR :", e)

        return None


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

            # FAST TEXT TRY
            text = page.get_text()

            sku = extract_sku(text)

            # OCR fallback
            if not sku:

                sku = ocr_sku_area(page)

            if not sku:
                sku = "UNKNOWN"

            print(
                f"PAGE {page_num + 1} -> {sku}"
            )

            grouped[sku].append(page_num)

        # -----------------------------------
        # OUTPUT PDF
        # -----------------------------------
        output_pdf = os.path.join(
            OUTPUT_FOLDER,
            "SORTED_" + file.filename
        )

        new_doc = fitz.open()

        for sku in sorted(grouped.keys()):

            pages = grouped[sku]

            # actual pages
            for pno in pages:

                new_doc.insert_pdf(
                    doc,
                    from_page=pno,
                    to_page=pno
                )

            # summary page
            summary = fitz.open()

            s_page = summary.new_page()

            s_page.insert_text(
                (170, 300),
                f"SKU : {sku}",
                fontsize=28
            )

            s_page.insert_text(
                (170, 350),
                f"TOTAL LABELS : {len(pages)}",
                fontsize=22
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