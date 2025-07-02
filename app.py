import os
import uuid
import csv
import random
from flask import Flask, render_template, request, send_file, redirect, after_this_request

app = Flask(__name__)
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

THRESHOLD = 49999  # Max allowed amount per split


def _split_fixed_amount(row, amount_index, id_index, split_amount):
    original_amount = int(row[amount_index])
    if original_amount <= THRESHOLD:
        return [row]

    parts = []
    num_parts = -(-original_amount // split_amount)  # Ceiling division
    base_id = row[id_index]

    for i in range(num_parts):
        new_row = row.copy()
        new_amount = (
            split_amount if i < num_parts - 1 else original_amount - split_amount * (num_parts - 1)
        )
        new_row[amount_index] = str(new_amount)
        new_row[id_index] = f"{base_id}X{str(i + 1).zfill(2)}"
        parts.append(new_row)

    return parts


def _split_equally(row, amount_index, id_index):
    original_amount = int(row[amount_index])
    if original_amount <= THRESHOLD:
        return [row]

    parts_count = -(-original_amount // THRESHOLD)  # Minimum parts to keep each ≤ THRESHOLD
    base_id = row[id_index]
    base_amount = original_amount // parts_count
    remainder = original_amount % parts_count

    parts = []
    for i in range(parts_count):
        new_row = row.copy()
        new_amount = base_amount + (1 if i < remainder else 0)
        new_row[amount_index] = str(new_amount)
        new_row[id_index] = f"{base_id}X{str(i + 1).zfill(2)}"
        parts.append(new_row)

    return parts

def split_distinct_parts_decreasing(amount, threshold):
    parts = []
    current = min(amount, threshold)

    while amount > 0 and current > 0:
        if amount - current >= 0:
            parts.append(current)
            amount -= current
            current -= 1
        else:
            current = amount  # last part to cover remaining amount

    if amount != 0:
        # Could not split exactly with distinct parts <= threshold
        return None

    return parts

def _split_randomly(row, amount_index, id_index):
    original_amount = int(row[amount_index])
    if original_amount <= THRESHOLD:
        return [row]

    parts = split_distinct_parts_decreasing(original_amount, THRESHOLD)
    if parts is None:
        # fallback to equal split if no valid distinct parts within threshold
        return _split_equally(row, amount_index, id_index)

    base_id = row[id_index]
    new_rows = []
    for i, amt in enumerate(parts):
        new_row = row.copy()
        new_row[amount_index] = str(amt)
        new_row[id_index] = f"{base_id}X{str(i + 1).zfill(2)}"
        new_rows.append(new_row)

    return new_rows


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        file = request.files.get("file")
        if not file or file.filename == "":
            return redirect(request.url)

        split_method = request.form.get("split_method", "equal")
        split_value_int = int(request.form.get("split_value", "0"))

        original_filename = os.path.splitext(file.filename)[0]
        input_ext = os.path.splitext(file.filename)[1]
        unique_suffix = uuid.uuid4().hex
        input_path = os.path.join(UPLOAD_FOLDER, f"{original_filename}_{unique_suffix}{input_ext}")
        file.save(input_path)

        output_filename = f"{original_filename}_{split_method}_split.csv"
        output_path = os.path.join(UPLOAD_FOLDER, output_filename)

        with open(input_path, newline="", encoding="utf-8") as infile, open(
            output_path, "w", newline="", encoding="utf-8"
        ) as outfile:
            sample = infile.read(2048)
            infile.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample)
            except csv.Error:
                dialect = csv.get_dialect("excel")

            reader = csv.reader(infile, dialect)
            writer = csv.writer(outfile)  # CSV default delimiter is comma

            header = next(reader)
            writer.writerow(header)

            try:
                id_index = header.index("Id")
                amount_index = header.index("DestinationAmount")
            except ValueError:
                # Try to find the columns with case-insensitive matching
                id_index = None
                amount_index = None
                
                for i, col in enumerate(header):
                    if col.lower() == "id":
                        id_index = i
                    elif col.lower() == "destinationamount":
                        amount_index = i
                
                if id_index is None or amount_index is None:
                    return f"Error: Required headers 'Id' and 'DestinationAmount' not found. Available headers: {', '.join(header)}"


            for row in reader:
                if split_method == "fixed":
                    new_rows = _split_fixed_amount(row, amount_index, id_index, split_value_int)
                elif split_method == "equal":
                    new_rows = _split_equally(row, amount_index, id_index)
                elif split_method == "random":
                    new_rows = _split_randomly(row, amount_index, id_index)
                else:
                    new_rows = [row]

                for new_row in new_rows:
                    writer.writerow(new_row)

        @after_this_request
        def cleanup(response):
            try:
                os.remove(input_path)
                os.remove(output_path)
            except Exception as e:
                print(f"Cleanup error: {e}")
            return response

        return send_file(output_path, as_attachment=True, download_name=output_filename)

    return render_template("index.html")


if __name__ == "__main__":
    app.run(debug=True)
