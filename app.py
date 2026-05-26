from flask import Flask, render_template, request, send_file
import fitz
import io
import re
import os
from collections import defaultdict
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
import requests

app = Flask(__name__)

UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "output"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)


# -----------------------------
# SKU DETECTOR (FINAL FIX)
# -----------------------------
def extract_sku(text):
    if not text:
        return None

    text = text.upper()
    text = re.sub(r'\s+', ' ', text)

    patterns = [
        r"SKU\s*[:\-]?\s*([A-Z0-9_-]{2,})",
        r"SELLER\s*SKU\s*[:\-]?\s*([A-Z0-9_-]{2,})",
        r"SKU\s*NO\s*[:\-]?\s*([A-Z0-9_-]{2,})",
    ]

    for p in patterns:
        m = re.search(p, text)
        if m:
            return m.group(1).strip()

    return None


# -----------------------------
# HOME
# -----------------------------
@app.route("/")
def home():
    return render_template("index.html")


# -----------------------------
# UPLOAD + PROCESS
# -----------------------------
@app.route("/upload", methods=["POST"])
def upload():
    try:
        file = request.files["pdf"]

        if file.filename == "":
            return "NO FILE SELECTED"

        filepath = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(filepath)

        doc = fitz.open(filepath)

        grouped = {}

        for page_num in range(len(doc)):
            page = doc.load_page(page_num)

            pix = page.get_pixmap(dpi=200)
            img_data = pix.tobytes("png")

            # ---------------- OCR ----------------
            try:
                response = requests.post(
                    "https://api.ocr.space/parse/image",
                    files={"filename": ("page.png", img_data, "image/png")},
                    data={"apikey": "helloworld", "language": "eng"},
                    timeout=60
                )

                result = response.json()

                text = ""
                if result.get("ParsedResults"):
                    text = result["ParsedResults"][0]["ParsedText"]

            except:
                text = ""

            print("\nPAGE:", page_num)
            print("OCR TEXT:", text[:150])

            sku = extract_sku(text)

            if not sku:
                sku = "UNKNOWN"

            print("SKU FOUND:", sku)

            if sku not in grouped:
                grouped[sku] = []

            grouped[sku].append(img_data)

        # ---------------- OUTPUT PDF ----------------
        output_pdf = os.path.join(OUTPUT_FOLDER, "SORTED_" + file.filename)
        c = canvas.Canvas(output_pdf)

        for sku in sorted(grouped.keys(), key=lambda x: (x == "UNKNOWN", x)):

            items = grouped[sku]

            for img in items:
                c.drawImage(
                    ImageReader(io.BytesIO(img)),
                    0, 0,
                    width=595,
                    height=842
                )
                c.showPage()

            c.setFont("Helvetica-Bold", 28)
            c.drawString(170, 550, f"SKU : {sku}")

            c.setFont("Helvetica", 20)
            c.drawString(150, 480, f"TOTAL LABELS : {len(items)}")

            c.showPage()

        c.save()

        return send_file(output_pdf, as_attachment=True)

    except Exception as e:
        return f"ERROR: {str(e)}"


# -----------------------------
# RUN
# -----------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=False)