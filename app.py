from flask import Flask, render_template, request, send_file
import fitz
import os
import re
import requests

from collections import defaultdict

app = Flask(__name__)

UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "output"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)


# -----------------------------------
# FINAL SKU DETECTION
# -----------------------------------
def extract_sku(text):

    text = text.upper()

    patterns = [

        r"SELLER SKU\s*[:\-]?\s*([A-Z0-9\-_]+)",

        r"SKU CODE\s*[:\-]?\s*([A-Z0-9\-_]+)",

        r"SKU\s*[:\-]?\s*([A-Z0-9\-_]+)",

        r"SKU\s*\n\s*([A-Z0-9\-_]+)"

    ]

    blacklist = [
        "SIZE",
        "COLOR",
        "TRACK",
        "TRACKING",
        "ORDER",
        "ITEM",
        "TOTAL",
        "SKU",
        "QTY",
        "COD",
        "PAID",
        "NAME",
        "PRODUCT"
    ]

    for pattern in patterns:

        matches = re.findall(
            pattern,
            text,
            re.IGNORECASE
        )

        for m in matches:

            sku = m.strip().upper()

            # clean symbols
            sku = re.sub(
                r'[^A-Z0-9\-_]',
                '',
                sku
            )

            # blacklist reject
            if sku in blacklist:
                continue

            # small reject
            if len(sku) < 5:
                continue

            # only numbers reject
            if sku.isdigit():
                continue

            # tracking reject
            if re.fullmatch(r"[A-Z]{2,5}[0-9]{8,}", sku):
                continue

            # courier reject
            if re.fullmatch(r"[A-Z]{2,5}\-[A-Z0-9]+", sku):
                continue

            return sku

    return "UNKNOWN"


# -----------------------------------
# OCR API
# -----------------------------------
def ocr_page(page):

    try:

        rect = fitz.Rect(
            40,
            120,
            420,
            500
        )

        pix = page.get_pixmap(
            matrix=fitz.Matrix(3, 3),
            clip=rect
        )

        img_data = pix.tobytes("png")

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

        return extract_sku(text)

    except Exception as e:

        print("OCR ERROR :", e)

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

        total_pages = len(doc)

        # -----------------------------------
        # PROCESS EACH PAGE
        # -----------------------------------
        for page_num in range(total_pages):

            page = doc.load_page(page_num)

            # -----------------------------------
            # FAST TEXT EXTRACTION
            # -----------------------------------
            text = page.get_text()

            sku = extract_sku(text)

            # -----------------------------------
            # OCR FALLBACK
            # -----------------------------------
            if sku == "UNKNOWN":

                sku = ocr_page(page)

            print(
                f"PAGE {page_num + 1} -> {sku}"
            )

            grouped[sku].append(page_num)

        # -----------------------------------
        # CREATE OUTPUT PDF
        # -----------------------------------
        output_pdf = os.path.join(
            OUTPUT_FOLDER,
            "SORTED_" + file.filename
        )

        new_doc = fitz.open()

        # -----------------------------------
        # SORT SKU WISE
        # -----------------------------------
        for sku in sorted(grouped.keys()):

            pages = grouped[sku]

            # original pages
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
                (160, 300),
                f"SKU : {sku}",
                fontsize=28
            )

            s_page.insert_text(
                (160, 350),
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