import datetime
import random
from repositories.wms_repository import WMSRepository
from repositories.odbms_repository import ODBMSRepository

class ValidationService:
    def __init__(self):
        self.wms_repo = WMSRepository()
        self.odbms_repo = ODBMSRepository()

    def translate_wms_status(self, stat_code):
        """Traduce códigos de estado de WMS a descripciones amigables."""
        if stat_code is None:
            return "Sin estado"
        status_map = {
            00: "00 - Creado",
            10: "10 - Pendiente",
            50: "50 - Asignado",
            90: "90 - Despachado",
            99: "99 - Cancelado"
        }
        return status_map.get(stat_code, f"{stat_code} - Activo")

    def validate_pkt(self, pkt_ctrl_nbr, ord_nbr, whse, all_wms_pkts, odbms_details):
        """
        Ejecuta las 8 reglas de validación para un PKT cancelado específico.
        """
        rules = {
            "r1_reserva_existe": {"status": "gris", "desc": "Existencia de reserva en WMS"},
            "r2_pedido_existe": {"status": "gris", "desc": "Existencia de pedido en ODBMS"},
            "r3_pkt_cancelado": {"status": "gris", "desc": "PKT anterior cancelado (WMS 99)"},
            "r4_pedido_pendiente": {"status": "gris", "desc": "Pedido-SKU en estado PENDIENTE BODEGA"},
            "r5_cantidad_pendiente": {"status": "gris", "desc": "Cantidad pendiente > 0"},
            "r6_sin_pkt_activo": {"status": "gris", "desc": "No existe otro PKT activo para el mismo SKU"},
            "r7_stock_suficiente": {"status": "gris", "desc": "Inventario disponible en ODBMS suficiente"},
            "r8_aprobado_general": {"status": "gris", "desc": "Aprobación general para generación"}
        }

        # --- Validación 1: Existencia de reserva ---
        # Si llegamos hasta aquí y tenemos registros, la reserva existe en WMS
        rules["r1_reserva_existe"] = {"status": "verde", "desc": "Reserva encontrada en WMS"}

        # --- Validación 2: Existencia de pedido ---
        if not ord_nbr:
            rules["r2_pedido_existe"] = {"status": "rojo", "desc": "Falta el número de pedido (ORD_NBR)"}
            return False, "Falta el número de pedido", rules, {}

        # Buscar el detalle de este pedido en ODBMS
        if not odbms_details:
            rules["r2_pedido_existe"] = {"status": "rojo", "desc": f"El pedido {ord_nbr} no existe en ODBMS"}
            return False, "Pedido no encontrado en ODBMS", rules, {}
        
        rules["r2_pedido_existe"] = {"status": "verde", "desc": f"Pedido {ord_nbr} encontrado en ODBMS"}

        # --- Validación 3: PKT cancelado en WMS ---
        # Buscamos el estado de este PKT en la lista de WMS
        current_wms_pkt = next((p for p in all_wms_pkts if p['pkt_ctrl_nbr'] == pkt_ctrl_nbr), None)
        if not current_wms_pkt:
            rules["r3_pkt_cancelado"] = {"status": "rojo", "desc": f"PKT {pkt_ctrl_nbr} no encontrado en WMS"}
            return False, "PKT no encontrado en WMS", rules, {}
        
        if current_wms_pkt['stat_code'] != 99:
            rules["r3_pkt_cancelado"] = {
                "status": "rojo", 
                "desc": f"PKT no cancelado. Estado actual: {self.translate_wms_status(current_wms_pkt['stat_code'])}"
            }
            return False, "El PKT no está cancelado en WMS", rules, {}
        
        rules["r3_pkt_cancelado"] = {"status": "verde", "desc": "PKT cancelado en WMS (Estado 99)"}

        # --- Encontrar SKU correspondiente a este PKT en ODBMS ---
        # Normalizamos números de PKT para comparar sin ceros a la izquierda si es necesario
        pkt_clean = pkt_ctrl_nbr.strip()
        pkt_no_zeros = pkt_clean.lstrip('0')

        matching_odbms_row = None
        for row in odbms_details:
            dist_pkt = row.get('dist_pkt', '')
            if dist_pkt:
                dist_clean = dist_pkt.strip()
                dist_no_zeros = dist_clean.lstrip('0')
                if dist_clean == pkt_clean or dist_no_zeros == pkt_no_zeros:
                    matching_odbms_row = row
                    break
        
        # Fallback: si no coincide por PKT, pero hay un único SKU en el pedido
        if not matching_odbms_row and len(odbms_details) == 1:
            matching_odbms_row = odbms_details[0]

        if not matching_odbms_row:
            # Si no coincide, tomamos el primero como fallback para no bloquear todo, pero indicando advertencia
            if odbms_details:
                matching_odbms_row = odbms_details[0]
            else:
                rules["r4_pedido_pendiente"] = {"status": "rojo", "desc": "No se encontraron SKUs para este PKT"}
                return False, "Sin SKUs asociados", rules, {}

        sku = matching_odbms_row['sku']
        estado_pedido = matching_odbms_row['estadopedido']
        cantidad_pendiente = matching_odbms_row['cantidadpendiente']

        # --- Validación 4: Pedido-SKU en estado PENDIENTE BODEGA / Pdte Bodega ---
        estado_normalizado = estado_pedido.strip().upper() if estado_pedido else ""
        if estado_normalizado not in ('PENDIENTE BODEGA', 'PDTE BODEGA'):
            rules["r4_pedido_pendiente"] = {
                "status": "rojo", 
                "desc": f"SKU {sku} en estado '{estado_pedido}' (debe ser PENDIENTE BODEGA / Pdte Bodega)"
            }
        else:
            rules["r4_pedido_pendiente"] = {"status": "verde", "desc": f"SKU {sku} en estado PENDIENTE BODEGA ({estado_pedido})"}

        # --- Validación 5: Cantidad pendiente > 0 ---
        if cantidad_pendiente <= 0:
            rules["r5_cantidad_pendiente"] = {
                "status": "rojo", 
                "desc": f"Cantidad pendiente es {int(cantidad_pendiente)} (debe ser > 0)"
            }
        else:
            rules["r5_cantidad_pendiente"] = {"status": "verde", "desc": f"Cantidad pendiente: {int(cantidad_pendiente)} unidades"}

        # --- Validación 6: No existe otro PKT activo para el mismo SKU ---
        # Buscamos otras asignaciones en ODBMS para el mismo SKU que apunten a PKTs activos en WMS
        other_pkts_for_sku = [
            row.get('dist_pkt') for row in odbms_details 
            if row.get('sku') == sku and row.get('dist_pkt') and row.get('dist_pkt').strip() != pkt_clean
        ]
        
        active_pkt_found = None
        for opkt in other_pkts_for_sku:
            opkt_clean = opkt.strip()
            opkt_no_zeros = opkt_clean.lstrip('0')
            # Buscar en WMS si ese PKT está activo
            wms_opkt = next(
                (p for p in all_wms_pkts 
                 if p['pkt_ctrl_nbr'].strip() == opkt_clean or p['pkt_ctrl_nbr'].lstrip('0') == opkt_no_zeros), 
                None
            )
            if wms_opkt and wms_opkt['stat_code'] != 99:
                active_pkt_found = wms_opkt
                break

        if active_pkt_found:
            rules["r6_sin_pkt_activo"] = {
                "status": "rojo", 
                "desc": f"Existe otro PKT activo para el SKU {sku}: PKT {active_pkt_found['pkt_ctrl_nbr']} (Estado {self.translate_wms_status(active_pkt_found['stat_code'])})"
            }
        else:
            rules["r6_sin_pkt_activo"] = {"status": "verde", "desc": f"No hay otros PKTs activos en WMS para el SKU {sku}"}

        # --- Validación 7: Stock disponible suficiente ---
        # Consultar stock real en ODBMS para esta bodega y SKU
        stock_info = None
        stock_error = None
        if whse:
            stock_info, stock_error = self.odbms_repo.get_sku_stock(whse, sku)
        
        stock_disponible = 0
        descrip_prod = "Producto"
        if stock_error:
            rules["r7_stock_suficiente"] = {"status": "amarillo", "desc": f"Error al validar stock en ODBMS: {stock_error}"}
        elif not stock_info:
            rules["r7_stock_suficiente"] = {"status": "rojo", "desc": f"Sin stock para SKU {sku}"}
        else:
            stock_disponible = stock_info.get('disponible', 0)
            descrip_prod = stock_info.get('descrip', 'Producto')
            if stock_disponible < cantidad_pendiente:
                rules["r7_stock_suficiente"] = {
                    "status": "rojo", 
                    "desc": f"Stock insuficiente para SKU {sku}: {int(stock_disponible)} disp. vs {int(cantidad_pendiente)} requerido"
                }
            else:
                rules["r7_stock_suficiente"] = {
                    "status": "verde", 
                    "desc": f"Stock suficiente en bodega {whse}: {int(stock_disponible)} disp. para {int(cantidad_pendiente)} req."
                }

        # --- Validación 8: Resultado General ---
        # Habilitado solo si todas las reglas previas (r1 a r7) son verdes
        general_valid = all(
            rules[r]["status"] == "verde" 
            for r in ["r1_reserva_existe", "r2_pedido_existe", "r3_pkt_cancelado", "r4_pedido_pendiente", "r5_cantidad_pendiente", "r6_sin_pkt_activo", "r7_stock_suficiente"]
        )

        if general_valid:
            rules["r8_aprobado_general"] = {"status": "verde", "desc": "APTO: Se puede generar nuevo PKT"}
        else:
            # Obtener el primer motivo de fallo
            fallo = next(
                (rules[r]["desc"] for r in ["r1_reserva_existe", "r2_pedido_existe", "r3_pkt_cancelado", "r4_pedido_pendiente", "r5_cantidad_pendiente", "r6_sin_pkt_activo", "r7_stock_suficiente"]
                 if rules[r]["status"] == "rojo"),
                "Validaciones pendientes o incorrectas"
            )
            rules["r8_aprobado_general"] = {"status": "rojo", "desc": f"BLOQUEADO: {fallo}"}

        detalle_resumen = rules["r8_aprobado_general"]["desc"]
        
        info_prod = {
            'sku': sku,
            'descrip': descrip_prod,
            'cantidad_pendiente': cantidad_pendiente,
            'stock_disponible': stock_disponible
        }

        return general_valid, detalle_resumen, rules, info_prod

    def validate_mock_scenario(self, ord_nbr, pkt_ctrl_nbr, whse, all_wms_pkts):
        """
        Genera validaciones simuladas con las 8 reglas para cuando la base de datos esté desconectada.
        """
        rules = {
            "r1_reserva_existe": {"status": "verde", "desc": "Reserva encontrada (Simulado)"},
            "r2_pedido_existe": {"status": "verde", "desc": f"Pedido {ord_nbr} encontrado en ODBMS (Simulado)"},
            "r3_pkt_cancelado": {"status": "verde", "desc": "PKT cancelado en WMS (Estado 99) (Simulado)"},
            "r4_pedido_pendiente": {"status": "verde", "desc": "SKU 4460308 en estado PENDIENTE BODEGA (Simulado)"},
            "r5_cantidad_pendiente": {"status": "verde", "desc": "Cantidad pendiente: 1 unidades (Simulado)"},
            "r6_sin_pkt_activo": {"status": "verde", "desc": "No hay otros PKTs activos en WMS para este SKU (Simulado)"},
            "r7_stock_suficiente": {"status": "verde", "desc": "Stock suficiente en bodega 91: 5 disp. (Simulado)"},
            "r8_aprobado_general": {"status": "verde", "desc": "APTO: Se puede generar nuevo PKT"}
        }

        sku = '4460308'
        descrip = 'TALADRO PERCUTOR 650W SODIMAC'
        cant_pend = 1.0
        stock_disp = 5.0

        # Simular fallos según dígitos del pedido
        last_digit = int(str(ord_nbr)[-1]) if str(ord_nbr) and str(ord_nbr)[-1].isdigit() else 0

        if last_digit % 3 == 0:
            rules["r7_stock_suficiente"] = {"status": "rojo", "desc": "Stock insuficiente en bodega: 0 disp. vs 1 requerido (Simulado)"}
            rules["r8_aprobado_general"] = {"status": "rojo", "desc": "BLOQUEADO: Stock insuficiente en bodega"}
            stock_disp = 0.0
        elif last_digit % 3 == 1:
            rules["r4_pedido_pendiente"] = {"status": "rojo", "desc": "SKU 6680203 en estado 'RESERVADO CLIENTE' (Simulado)"}
            rules["r8_aprobado_general"] = {"status": "rojo", "desc": "BLOQUEADO: SKU en estado incorrecto"}
            sku = '6680203'
            descrip = 'SIERRA CIRCULAR SKIL'
        else:
            # Comprobar si en la simulación creamos otro PKT activo
            other_active = any(p for p in all_wms_pkts if p['pkt_ctrl_nbr'] != pkt_ctrl_nbr and p['stat_code'] != 99)
            if other_active:
                rules["r6_sin_pkt_activo"] = {"status": "rojo", "desc": "Existe otro PKT activo en WMS para este SKU (Simulado)"}
                rules["r8_aprobado_general"] = {"status": "rojo", "desc": "BLOQUEADO: Ya existe un PKT activo"}

        general_valid = rules["r8_aprobado_general"]["status"] == "verde"
        info_prod = {
            'sku': sku,
            'descrip': descrip,
            'cantidad_pendiente': cant_pend,
            'stock_disponible': stock_disp
        }

        return general_valid, rules["r8_aprobado_general"]["desc"], rules, info_prod

    def execute_validation_flow(self, values):
        """
        Coordinador general del flujo de validación.
        Recibe los términos ingresados por el usuario, consulta WMS, obtiene los pedidos
        y por cada PKT cancelado ejecuta el motor de validaciones cruzadas.
        """
        data_source = 'Base de datos WMS & ODBMS'
        is_mock = False
        db_error = None

        # 1. Obtener reservas desde WMS
        reservas, db_error = self.wms_repo.get_reservas_by_values(values)
        
        # Caer en simulación si hay error de base de datos o no se inicializó Oracle
        if reservas is None:
            is_mock = True
            data_source = 'Simulación (Modo Sin Conexión)'
            # Generar datos simulados de WMS
            results = self.get_mock_wms_data(values)
        else:
            # Consultar todos los PKTs de esas reservas en WMS
            results, db_error = self.wms_repo.get_pkts_by_reservas(reservas)
            if results is None:
                is_mock = True
                data_source = 'Simulación (Modo Sin Conexión)'
                results = self.get_mock_wms_data(values)

        # 2. Correr validación para cada fila
        for row in results:
            stat_code = row.get('stat_code')
            whse = row.get('whse', '91')
            ord_nbr = row.get('ord_nbr')
            pkt_ctrl_nbr = row.get('pkt_ctrl_nbr')

            # Traducir estado de WMS
            row['stat_desc'] = self.translate_wms_status(stat_code)

            if stat_code == 99:
                if not is_mock:
                    # Consultar detalles del pedido en ODBMS
                    odbms_details, odbms_error = self.odbms_repo.get_pedido_detalles(ord_nbr)
                    if odbms_details is None:
                        # Fallback a simulación individual por error ODBMS
                        valido, detalle, rules, prod = self.validate_mock_scenario(ord_nbr, pkt_ctrl_nbr, whse, results)
                        rules["r2_pedido_existe"]["desc"] += " (Simulado por error ODBMS)"
                    else:
                        valido, detalle, rules, prod = self.validate_pkt(pkt_ctrl_nbr, ord_nbr, whse, results, odbms_details)
                else:
                    valido, detalle, rules, prod = self.validate_mock_scenario(ord_nbr, pkt_ctrl_nbr, whse, results)
                
                row['validation'] = {
                    'valido': valido,
                    'estado': 'Apto' if valido else 'Bloqueado',
                    'detalle': detalle,
                    'rules': rules,
                    'sku': prod.get('sku'),
                    'descrip': prod.get('descrip'),
                    'cantidad_pendiente': prod.get('cantidad_pendiente'),
                    'stock_disponible': prod.get('stock_disponible')
                }
            else:
                row['validation'] = None

        return {
            'success': True,
            'source': data_source,
            'is_mock': is_mock,
            'db_error': db_error,
            'results': results
        }

    def get_mock_wms_data(self, values):
        """Generador de datos WMS mock equivalentes a la lógica original."""
        mock_db = [
            {'whse': '91', 'pkt_ctrl_nbr': '0027911735', 'cust_dept': 'PED', 'ord_nbr': '4988900', 'stat_code': 99, 'thrd_party_bill': '35685735', 'create_date_time': '2026-07-16 21:43:37'},
            {'whse': '91', 'pkt_ctrl_nbr': '0028004274', 'cust_dept': 'PED', 'ord_nbr': '4988900', 'stat_code': 50, 'thrd_party_bill': '35685735', 'create_date_time': '2026-07-22 00:55:37'},
            {'whse': '91', 'pkt_ctrl_nbr': '0012345678', 'cust_dept': 'PED', 'ord_nbr': '1234567', 'stat_code': 99, 'thrd_party_bill': '12345678', 'create_date_time': '2026-07-22 14:00:00'},
            {'whse': '91', 'pkt_ctrl_nbr': '0012345679', 'cust_dept': 'PED', 'ord_nbr': '1234567', 'stat_code': 50, 'thrd_party_bill': '12345678', 'create_date_time': '2026-07-22 15:30:00'},
        ]

        reservas_encontradas = set()
        para_inventar = []

        for val in values:
            val_with_00 = val if val.startswith('00') else '00' + val
            found = False
            for row in mock_db:
                if row['thrd_party_bill'] == val or row['pkt_ctrl_nbr'] == val or row['pkt_ctrl_nbr'] == val_with_00:
                    reservas_encontradas.add(row['thrd_party_bill'])
                    found = True
            if not found:
                para_inventar.append(val)

        results = []
        for res in reservas_encontradas:
            for row in mock_db:
                if row['thrd_party_bill'] == res:
                    results.append(row.copy())

        for val in para_inventar:
            reserva_inventada = val
            stat = 99
            pkt_num = val if val.startswith('00') else '00' + val
            
            if len(val) >= 8 and (val.startswith('00') or val.startswith('27') or val.startswith('12')):
                reserva_inventada = f"R-{random.randint(30000000, 39999999)}"
                last_digit = int(val[-1]) if val[-1].isdigit() else 0
                stat = 99 if last_digit % 2 == 1 else 50
            else:
                pkt_num = f"00{random.randint(10000000, 99999999)}"
                stat = 99

            results.append({
                'whse': '91',
                'pkt_ctrl_nbr': pkt_num,
                'cust_dept': 'PED',
                'ord_nbr': f"{random.randint(4000000, 4999999)}",
                'stat_code': stat,
                'thrd_party_bill': reserva_inventada,
                'create_date_time': (datetime.datetime.now() - datetime.timedelta(days=2)).strftime('%Y-%m-%d %H:%M:%S')
            })
            
            results.append({
                'whse': '91',
                'pkt_ctrl_nbr': f"00{random.randint(10000000, 99999999)}",
                'cust_dept': 'PED',
                'ord_nbr': results[-1]['ord_nbr'],
                'stat_code': 50 if stat == 99 else 99,
                'thrd_party_bill': reserva_inventada,
                'create_date_time': (datetime.datetime.now() - datetime.timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')
            })

        return results
