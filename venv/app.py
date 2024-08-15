from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for
import paypalrestsdk
from dotenv import load_dotenv
import os
import requests
import csv
from io import StringIO, BytesIO

# Cargar las variables de entorno desde el archivo .env
load_dotenv()

app = Flask(__name__)

# Configurar las credenciales de PayPal (Sandbox)
paypalrestsdk.configure({
    "mode": "sandbox",  # Cambiar a "live" en producción
    "client_id": os.getenv("PAYPAL_CLIENT_ID"),
    "client_secret": os.getenv("PAYPAL_CLIENT_SECRET")
})

# Crear carpeta temporal si no existe
TEMP_DIR = os.path.join(app.root_path, 'temp')
if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR)

# Funciones necesarias antes de las rutas

def luhn_check(card_number):
    """Realiza la validación del algoritmo de Luhn"""
    sum = 0
    reverse_digits = card_number[::-1]
    for i, digit in enumerate(reverse_digits):
        n = int(digit)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        sum += n
    return sum % 10 == 0

def get_card_type(card_number):
    """Determina el tipo de tarjeta basado en los primeros dígitos"""
    card_number = str(card_number)
    if card_number.startswith('4'):
        return 'Visa'
    elif card_number.startswith(('51', '52', '53', '54', '55')):
        return 'MasterCard'
    elif card_number.startswith('34') or card_number.startswith('37'):
        return 'American Express'
    elif card_number.startswith('6'):
        return 'Discover'
    else:
        return 'Unknown'

def get_mii(card_number):
    """Obtiene el Major Industry Identifier (MII)"""
    mii_dict = {
        '1': 'Airlines',
        '2': 'Airlines',
        '3': 'Travel and Entertainment',
        '4': 'Banking and Financial',
        '5': 'Banking and Financial',
        '6': 'Merchandising and Banking',
        '7': 'Petroleum',
        '8': 'Healthcare, Telecommunications',
        '9': 'National Assignment'
    }
    return mii_dict.get(card_number[0], 'Unknown')

def get_bin_info(bin_number):
    """Obtiene información del BIN/IIN"""
    try:
        response = requests.get(f'https://lookup.binlist.net/{bin_number}')
        response.raise_for_status()  # Lanzar excepción para códigos de estado 4xx/5xx
        data = response.json()
        return {
            "bank": data.get("bank", {}).get("name", "Unknown"),
            "country": data.get("country", {}).get("name", "Unknown"),
            "brand": data.get("scheme", "Unknown"),
            "type": data.get("type", "Unknown")
        }
    except requests.RequestException as e:
        return {
            "bank": "Unknown",
            "country": "Unknown",
            "brand": "Unknown",
            "type": "Unknown",
            "error": str(e)  # Añadir detalle del error para depuración
        }

def simulate_transaction(card_number, exp_month, exp_year, cvc):
    """Simula una transacción para verificar capacidad de compra usando la API de PayPal"""
    payment = paypalrestsdk.Payment({
        "intent": "sale",
        "payer": {
            "payment_method": "credit_card",
            "funding_instruments": [{
                "credit_card": {
                    "number": card_number,
                    "type": get_card_type(card_number).lower(),
                    "expire_month": exp_month,
                    "expire_year": exp_year,
                    "cvv2": cvc,
                    "first_name": "Test",
                    "last_name": "User"
                }
            }]
        },
        "transactions": [{
            "amount": {
                "total": "1.00",
                "currency": "USD"
            },
            "description": "This is a test transaction."
        }]
    })

    if payment.create():
        return {"can_purchase": True, "bin_info": get_bin_info(card_number[:6])}
    else:
        return {"can_purchase": False, "error": payment.error}

# Rutas de la aplicación

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/check_card', methods=['POST'])
def check_card():
    card_number = request.form['card_number']
    exp_month = request.form['exp_month']
    exp_year = request.form['exp_year']
    cvc = request.form['cvc']
    
    # Validar el número de tarjeta usando el algoritmo de Luhn
    luhn_valid = luhn_check(card_number)
    
    # Obtener información de la tarjeta
    card_info = {
        "luhn_valid": luhn_valid,
        "card_type": get_card_type(card_number),
        "mii": get_mii(card_number),
        "bin_info": get_bin_info(card_number[:6]),
    }
    
    # Simular una transacción para verificar capacidad de compra
    transaction_result = simulate_transaction(card_number, exp_month, exp_year, cvc)
    
    # Agregar información sobre la transacción
    card_info["can_purchase"] = transaction_result["can_purchase"]
    card_info["transaction_error"] = transaction_result.get("error")
    
    return jsonify(card_info)

@app.route('/upload', methods=['POST'])
def upload_file():
    file = request.files['file']
    if not file:
        return "No file uploaded", 400
    
    # Leer el archivo CSV
    csv_data = file.stream.read().decode("utf-8")
    csv_reader = csv.DictReader(StringIO(csv_data))
    
    valid_cards = []
    invalid_cards = []
    for row in csv_reader:
        card_number = row['card_number']
        exp_month = row['exp_month']
        exp_year = row['exp_year']
        cvc = row['cvc']
        
        # Validar la tarjeta
        luhn_valid = luhn_check(card_number)
        card_info = {
            "card_number": card_number,
            "exp_month": exp_month,
            "exp_year": exp_year,
            "cvc": cvc,
            "card_type": get_card_type(card_number),
            "mii": get_mii(card_number),
            "bank": "Unknown",
            "country": "Unknown",
            "brand": "Unknown",
            "type": "Unknown"
        }

        if luhn_valid:
            transaction_result = simulate_transaction(card_number, exp_month, exp_year, cvc)
            card_info.update({
                "can_purchase": transaction_result["can_purchase"],
                "transaction_error": transaction_result.get("error")
            })

            # Solo intenta agregar bin_info si está disponible
            if "bin_info" in transaction_result:
                card_info.update({
                    "bank": transaction_result["bin_info"].get("bank", "Unknown"),
                    "country": transaction_result["bin_info"].get("country", "Unknown"),
                    "brand": transaction_result["bin_info"].get("brand", "Unknown"),
                    "type": transaction_result["bin_info"].get("type", "Unknown")
                })

            if transaction_result["can_purchase"]:
                valid_cards.append(card_info)
            else:
                invalid_cards.append(card_info)
        else:
            card_info.update({
                "can_purchase": False,
                "transaction_error": "Failed Luhn check"
            })
            invalid_cards.append(card_info)
    
    # Generar el archivo CSV con tarjetas válidas
    valid_output = StringIO()
    invalid_output = StringIO()
    fieldnames = ["card_number", "exp_month", "exp_year", "cvc", "card_type", "mii", "bank", "country", "brand", "type", "can_purchase", "transaction_error"]
    
    writer = csv.DictWriter(valid_output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(valid_cards)

    writer = csv.DictWriter(invalid_output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(invalid_cards)
    
    # Guardar ambos archivos en la carpeta 'temp'
    valid_output.seek(0)
    invalid_output.seek(0)
    
    valid_file_path = os.path.join(TEMP_DIR, 'valid_cards.csv')
    invalid_file_path = os.path.join(TEMP_DIR, 'invalid_cards.csv')
    
    with open(valid_file_path, "w", newline='') as valid_file:
        valid_file.write(valid_output.getvalue())

    with open(invalid_file_path, "w", newline='') as invalid_file:
        invalid_file.write(invalid_output.getvalue())

    return redirect(url_for('download_file', filename='valid_cards.csv'))

@app.route('/download/<filename>', methods=['GET'])
def download_file(filename):
    # Descargar el archivo CSV especificado desde la carpeta 'temp'
    file_path = os.path.join(TEMP_DIR, filename)
    if not os.path.exists(file_path):
        return f"Error: {filename} no se encuentra en la ruta {file_path}", 404
    return send_file(file_path, mimetype="text/csv", as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)
