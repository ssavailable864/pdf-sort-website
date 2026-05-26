from flask import Flask, render_template, request, send_file
import fitz
import io
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

    # blacklist reject
    if value in blacklist:
        return None

    # too small reject
    if len(value) < 5:
        return None

    # only letters reject
    if value.isalpha():
        return None

    # only numbers reject
    if value.isdigit():
        return None

    # tracking id reject
    if re.fullmatch(r"[A-Z]{2,5}[0-9]{8,}", value):
        return None

    # courier code reject
    if re.fullmatch(r"[A-Z]{2,5}\-[A-Z0-9]+", value):
        return None

    # must contain letters + numbers
    has_letter = any(c.isalpha() for c in value)
    has_number = any(c.isdigit() for c in value)

    if not (has_letter and has_number):
        return None

    return value


# -----------------------------------
# FIND SKU FROM TEXT
# -----------------------------------
def extract_sku_from_text(text):

    lines = text.split("\n")

    # pass 1 → after SKU word
    for i, line in enumerate(lines):

        line_upper = line.upper()

        if "SKU" in line_upper:

            for j in range(1, 5):

                if i + j >= len(lines):
                    continue

                candidate = lines[i + j]

                sku = clean_sku(candidate)

                if sku:
                    return sku

    # pass 2 → scan all lines
    for line in lines:

        words = line.split()

        for word in words:

            sku = clean_sku(word)

            if sku:
                return sku

    return None


# -----------------------------------
# OCR API
# -----------------------------------
def extract_sku_ocr(img_data):

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

        sku = extract_sku_from_text(text)

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
            return "NO FILE SELECTED"

        filepath = os.path.join(
            UPLOAD_FOLDER,
            file.filename
        )

        file.save(filepath)

        doc = fitz.open(filepath)

        grouped = defaultdict(list)

        total_pages = len(doc)

        # -----------------------------------
        # PROCESS PAGES
        # -----------------------------------
        for page_num in range(total_pages):

            page = doc.load_page(page_num)

            # -----------------------------
            # FAST TEXT EXTRACTION
            # -----------------------------
            text = page.get_text()

            sku = extract_sku_from_text(text)

            # -----------------------------
            # OCR FALLBACK
            # -----------------------------
            if not sku:

                pix = page.get_pixmap(dpi=180)

                img_data = pix.tobytes("png")

                sku = extract_sku_ocr(img_data)

            # -----------------------------
            # FINAL FALLBACK
            # -----------------------------
            if not sku:
                sku = "UNKNOWN"

            print(
                f"PAGE {page_num + 1} -> {sku}"
            )

            grouped[sku].append(page_num)

        # -----------------------------------
        # CREATE SORTED PDF
        # -----------------------------------
        output_pdf = os.path.join(
            OUTPUT_FOLDER,
            "SORTED_" + file.filename
        )

        new_doc = fitz.open()

        # sort sku wise
        for sku in sorted(grouped.keys()):

            pages = grouped[sku]

            # insert actual pages
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