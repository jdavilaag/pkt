import re
import datetime
import random
from flask import Blueprint, request, jsonify
from services.validation_service import ValidationService

validation_bp = Blueprint('validation', __name__)
validation_service = ValidationService()

@validation_bp.route('/api/consultar', methods=['POST'])
def consultar():
    data = request.get_json() or {}
    input_text = data.get('input_text', '')

    if not input_text:
        return jsonify({'error': 'Falta el texto a buscar.'}), 400

    raw_vals = re.split(r'[\s,;\n]+', input_text)
    values = []
    for val in raw_vals:
        val_clean = val.strip()
        if val_clean:
            values.append(val_clean)

    if not values:
        return jsonify({'error': 'No se ingresaron códigos válidos.'}), 400

    try:
        response_data = validation_service.execute_validation_flow(values)
        return jsonify(response_data)
    except Exception as e:
        return jsonify({'error': f'Error interno en el servidor: {str(e)}'}), 500

@validation_bp.route('/api/generar', methods=['POST'])
def generar_nuevo_pkt():
    data = request.get_json() or {}
    pkt_original = data.get('pkt_original')
    reserva = data.get('reserva')

    if not pkt_original:
        return jsonify({'success': False, 'error': 'Falta el número de PKT original.'}), 400

    # Lógica de simulación de creación de nuevo PKT (según Versión 1 del plan)
    nuevo_pkt_ctrl = f"00{random.randint(10000000, 99999999)}"

    return jsonify({
        'success': True,
        'message': f'Nuevo PKT {nuevo_pkt_ctrl} generado con éxito por la cancelación del PKT {pkt_original}.',
        'nuevo_pkt': nuevo_pkt_ctrl,
        'pkt_original': pkt_original,
        'reserva': reserva,
        'timestamp': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })
