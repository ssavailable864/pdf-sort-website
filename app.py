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


# ----------------------------------------
# SKU FILTER
# ----------------------------------------
def clean_sku(value):

    value = value.strip().upper()

    blacklist = [
        "SIZE",
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
        "DELIVERY"
    ]

    if len(value) < 4:
        return None

    for b in blacklist:
        if b in value:
            return None

    # tracking ids ignore
    if re.fullmatch(r"[A-Z]{2,5}[0-9]{8,}", value):
        return None

    # courier codes ignore
    if re.fullmatch(r"[A-Z]{2,5}\-[A-Z0-9]+", value):
        return None

    return value


# ----------------------------------------
# TEXT SKU
# ----------------------------------------
def extract_sku_from_text(text):

    lines = text.split("\n")

    for i, line in enumerate(lines):

        line_upper = line.upper()

        if "SKU" in line_upper:

            for j in range(1, 4):

                if i + j >= len(lines):
                    continue

                candidate = lines[i + j]

                candidate = re.sub(
                    r"[^A-Z0-9\-_ ]",
                    "",
                    candidate.upper()
                )

                sku = clean_sku(candidate)

                if sku:
                    return sku

    return None


# ----------------------------------------
# OCR SKU
# ----------------------------------------
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

        return extract_sku_from_text(text)

    except Exception as e:

        print("OCR ERROR :", e)

        return None


# ----------------------------------------
# HOME
# ----------------------------------------
@app.route("/")
def home():
    return render_template("index.html")


# ----------------------------------------
# UPLOAD
# ----------------------------------------
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

        # ----------------------------------------
        # PAGE LOOP
        # ----------------------------------------
        for page_num in range(len(doc)):

            page = doc.load_page(page_num)

            # FAST TEXT TRY
            text = page.get_text()

            sku = extract_sku_from_text(text)

            # ----------------------------------------
            # OCR FALLBACK
            # ----------------------------------------
            if not sku:

                pix = page.get_pixmap(dpi=200)

                img_data = pix.tobytes("png")

                sku = extract_sku_ocr(img_data)

            # still not found
            if not sku:
                sku = "UNKNOWN"

            print("PAGE :", page_num + 1)
            print("SKU :", sku)

            grouped[sku].append(page_num)

        # ----------------------------------------
        # OUTPUT
        # ----------------------------------------
        output_pdf = os.path.join(
            OUTPUT_FOLDER,
            "SORTED_" + file.filename
        )

        new_doc = fitz.open()

        for sku in sorted(grouped.keys()):

            pages = grouped[sku]

            # insert pages
            for pno in pages:

                new_doc.insert_pdf(
                    doc,
                    from_page=pno,
                    to_page=pno
                )

            # summary page
            summary = fitz.open()

            spage = summary.new_page()

            spage.insert_text(
                (170, 300),
                f"SKU : {sku}",
                fontsize=28
            )

            spage.insert_text(
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


# ----------------------------------------
# RUN
# ----------------------------------------
if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=10000,
        debug=False
    )