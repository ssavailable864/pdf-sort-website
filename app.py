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


# =====================================================
# SKU EXTRACT FUNCTION
# =====================================================
def extract_sku(text):

    text = text.upper()

    lines = text.splitlines()

    clean_lines = []

    # -----------------------------------------
    # CLEAN EMPTY LINES
    # -----------------------------------------
    for line in lines:

        line = line.strip()

        if line != "":
            clean_lines.append(line)

    # -----------------------------------------
    # FIND SKU
    # -----------------------------------------
    for i in range(len(clean_lines)):

        line = clean_lines[i]

        # EXACT SKU WORD
        if line == "SKU":

            # NEXT FEW LINES CHECK
            for j in range(i + 1, min(i + 6, len(clean_lines))):

                sku = clean_lines[j].strip()

                # SPACE REMOVE
                sku = sku.replace(" ", "_")

                # -----------------------------------------
                # IGNORE BAD WORDS
                # -----------------------------------------
                bad_words = [

                    "FPL",
                    "SURFACE",
                    "TRACK",
                    "TRACKING",
                    "DELIVERY",
                    "SHIPMENT",
                    "ORDER",
                    "ORDER ID",
                    "AWB",
                    "COD",
                    "PREPAID",
                    "XP",
                    "ROAD",
                    "ADDRESS",
                    "INDIA",
                    "MOBILE",
                    "PHONE",
                    "PIN"

                ]

                skip = False

                for bad in bad_words:

                    if bad in sku:
                        skip = True
                        break

                if skip:
                    continue

                # -----------------------------------------
                # IGNORE ONLY NUMBERS VERY LONG
                # -----------------------------------------
                if sku.isdigit() and len(sku) > 12:
                    continue

                # -----------------------------------------
                # IGNORE VERY LONG VALUES
                # -----------------------------------------
                if len(sku) > 25:
                    continue

                # -----------------------------------------
                # VALID SKU
                # -----------------------------------------
                if re.search(r"[A-Z0-9]", sku):

                    return sku

    return "UNKNOWN"


# =====================================================
# HOME PAGE
# =====================================================
@app.route("/")
def home():

    return render_template("index.html")


# =====================================================
# UPLOAD PDF
# =====================================================
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

        # OPEN PDF
        doc = fitz.open(filepath)

        grouped = defaultdict(list)

        total_pages = len(doc)

        # =====================================================
        # READ ALL PAGES
        # =====================================================
        for page_num in range(total_pages):

            page = doc.load_page(page_num)

            # -----------------------------------------
            # DIRECT TEXT EXTRACTION
            # -----------------------------------------
            text = page.get_text()

            # -----------------------------------------
            # FIND SKU
            # -----------------------------------------
            sku = extract_sku(text)

            print("FOUND SKU :", sku)

            # -----------------------------------------
            # SAVE PAGE PDF
            # -----------------------------------------
            single_pdf = fitz.open()

            single_pdf.insert_pdf(
                doc,
                from_page=page_num,
                to_page=page_num
            )

            pdf_bytes = single_pdf.tobytes()

            grouped[sku].append(pdf_bytes)

            single_pdf.close()

        # =====================================================
        # OUTPUT PDF
        # =====================================================
        output_pdf = os.path.join(
            OUTPUT_FOLDER,
            "SORTED_" + file.filename
        )

        final_pdf = fitz.open()

        # SORT SKU WISE
        for sku in sorted(grouped.keys()):

            items = grouped[sku]

            # -----------------------------------------
            # ADD LABEL PAGES
            # -----------------------------------------
            for pdf_data in items:

                temp_pdf = fitz.open(
                    stream=pdf_data,
                    filetype="pdf"
                )

                final_pdf.insert_pdf(temp_pdf)

                temp_pdf.close()

            # -----------------------------------------
            # SUMMARY PAGE
            # -----------------------------------------
            summary_pdf_path = os.path.join(
                OUTPUT_FOLDER,
                f"{sku}_summary.pdf"
            )

            c = canvas.Canvas(summary_pdf_path)

            c.setFont("Helvetica-Bold", 30)

            c.drawString(
                150,
                550,
                f"SKU : {sku}"
            )

            c.drawString(
                120,
                470,
                f"TOTAL LABELS : {len(items)}"
            )

            c.save()

            summary_doc = fitz.open(summary_pdf_path)

            final_pdf.insert_pdf(summary_doc)

            summary_doc.close()

        # SAVE FINAL PDF
        final_pdf.save(output_pdf)

        final_pdf.close()

        return send_file(
            output_pdf,
            as_attachment=True
        )

    except Exception as e:

        return f"ERROR : {str(e)}"


# =====================================================
# RUN APP
# =====================================================
if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=10000,
        debug=False
    )