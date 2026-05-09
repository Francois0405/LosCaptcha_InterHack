import pandas as pd
import json
import os
import re
import csv

CSV_DIR = "csv"
JSON_DIR = "json"

os.makedirs(JSON_DIR, exist_ok=True)


def clean_column_name(col):
    col = str(col).strip().lower()

    replacements = {
        " ": "_",
        ".": "",
        "/": "_",
        "º": "o",
        "ª": "a",
        "á": "a",
        "à": "a",
        "é": "e",
        "è": "e",
        "í": "i",
        "ï": "i",
        "ó": "o",
        "ò": "o",
        "ú": "u",
        "ü": "u",
        "ñ": "n",
        "ç": "c"
    }

    for old, new in replacements.items():
        col = col.replace(old, new)

    col = re.sub(r"[^a-z0-9_]", "", col)
    col = re.sub(r"_+", "_", col)
    col = col.strip("_")

    return col


def detect_separator(path, encoding):
    with open(path, "r", encoding=encoding, errors="ignore") as file:
        sample = file.read(4096)

    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=[",", ";", "\t", "|"])
        return dialect.delimiter
    except Exception:
        return ";"


def read_csv_safely(path):
    encodings = ["utf-8-sig", "utf-8", "latin1", "cp1252"]

    for encoding in encodings:
        try:
            separator = detect_separator(path, encoding)
            print(f"  Encoding: {encoding} | Separador detectado: '{separator}'")

            return pd.read_csv(
                path,
                encoding=encoding,
                sep=separator,
                engine="python",
                on_bad_lines="skip"
            )

        except Exception as error:
            print(f"  No se pudo con encoding {encoding}: {error}")

    raise Exception(f"No se pudo leer el archivo: {path}")


def csv_to_json(csv_filename, json_filename):
    input_path = os.path.join(CSV_DIR, csv_filename)
    output_path = os.path.join(JSON_DIR, json_filename)

    if not os.path.exists(input_path):
        print(f"No encontrado: {input_path}")
        return

    print(f"\nProcesando: {input_path}")

    df = read_csv_safely(input_path)

    df.columns = [clean_column_name(col) for col in df.columns]

    # Convertir NaN/NaT a None para que en JSON salga null
    df = df.replace({pd.NA: None})
    df = df.astype(object).where(pd.notnull(df), None)

    data = df.to_dict(orient="records")

    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2, allow_nan=False)

    print(f"JSON creado: {output_path}")
    print(f"Filas exportadas: {len(data)}")


files = {
    "Cabecera Transporte.csv": "cabecera_transporte.json",
    "Direcciones.csv": "direcciones.json",
    "Hackaton.csv": "hackaton.json",
    "HorariosEntrega.csv": "horarios_entrega.json",
    "MaterialesZubic.csv": "materiales_zubic.json",
    "ZM040.csv": "zm040.json",
    "Zonas.csv": "zonas.json"
}


for csv_filename, json_filename in files.items():
    csv_to_json(csv_filename, json_filename)

print("\nConversión terminada.")