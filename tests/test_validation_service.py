import unittest
from unittest.mock import MagicMock, patch
from services.validation_service import ValidationService

class TestValidationService(unittest.TestCase):
    def setUp(self):
        # Parchear los repositorios en la inicialización para que no intenten conectarse a Oracle
        self.wms_repo_patcher = patch('services.validation_service.WMSRepository')
        self.odbms_repo_patcher = patch('services.validation_service.ODBMSRepository')
        
        self.mock_wms_repo_cls = self.wms_repo_patcher.start()
        self.mock_odbms_repo_cls = self.odbms_repo_patcher.start()
        
        self.mock_wms_repo = self.mock_wms_repo_cls.return_value
        self.mock_odbms_repo = self.mock_odbms_repo_cls.return_value
        
        self.service = ValidationService()

    def tearDown(self):
        self.wms_repo_patcher.stop()
        self.odbms_repo_patcher.stop()

    def test_translate_wms_status(self):
        self.assertEqual(self.service.translate_wms_status(99), "99 - Cancelado")
        self.assertEqual(self.service.translate_wms_status(50), "50 - Asignado")
        self.assertEqual(self.service.translate_wms_status(12), "12 - Activo")
        self.assertEqual(self.service.translate_wms_status(None), "Sin estado")

    def test_validate_pkt_success(self):
        # Datos del PKT y orden a probar
        pkt_ctrl_nbr = '0027911735'
        ord_nbr = '4988900'
        whse = '91'

        # Todos los PKTs de la reserva en WMS (uno cancelado y uno que no es del mismo SKU o que también está cancelado)
        all_wms_pkts = [
            {'pkt_ctrl_nbr': '0027911735', 'stat_code': 99},
            {'pkt_ctrl_nbr': '0028004274', 'stat_code': 99} # también cancelado, no debe interferir
        ]

        # Detalles del pedido en ODBMS
        odbms_details = [
            {
                'pedido': '4988900',
                'sku': '4460308',
                'estadopedido': 'PENDIENTE BODEGA',
                'est_pkt': 'CANCELADO',
                'cantidadpendiente': 1.0,
                'dist_pkt': '0027911735',
                'bodega': '91'
            }
        ]

        # Mockear consulta de stock (Query 4) para retornar stock suficiente
        self.mock_odbms_repo.get_sku_stock.return_value = (
            {
                'cc': '91',
                'sku': '4460308',
                'descrip': 'PRODUCTO DE PRUEBA',
                'disponible': 10.0,
                'total': 15.0
            },
            None
        )

        valido, detalle, rules, prod = self.service.validate_pkt(
            pkt_ctrl_nbr, ord_nbr, whse, all_wms_pkts, odbms_details
        )

        self.assertTrue(valido)
        self.assertEqual(rules["r8_aprobado_general"]["status"], "verde")
        self.assertEqual(prod["sku"], "4460308")
        self.assertEqual(prod["stock_disponible"], 10.0)

    def test_validate_pkt_insufficient_stock(self):
        pkt_ctrl_nbr = '0027911735'
        ord_nbr = '4988900'
        whse = '91'

        all_wms_pkts = [{'pkt_ctrl_nbr': '0027911735', 'stat_code': 99}]
        odbms_details = [{
            'pedido': '4988900',
            'sku': '4460308',
            'estadopedido': 'PENDIENTE BODEGA',
            'est_pkt': 'CANCELADO',
            'cantidadpendiente': 5.0,
            'dist_pkt': '0027911735',
            'bodega': '91'
        }]

        # Retorna stock disponible de 2 unidades, pero se requieren 5
        self.mock_odbms_repo.get_sku_stock.return_value = (
            {
                'cc': '91',
                'sku': '4460308',
                'descrip': 'PRODUCTO DE PRUEBA',
                'disponible': 2.0,
                'total': 5.0
            },
            None
        )

        valido, detalle, rules, prod = self.service.validate_pkt(
            pkt_ctrl_nbr, ord_nbr, whse, all_wms_pkts, odbms_details
        )

        self.assertFalse(valido)
        self.assertEqual(rules["r7_stock_suficiente"]["status"], "rojo")
        self.assertIn("insuficiente", rules["r7_stock_suficiente"]["desc"])

    def test_validate_pkt_other_active_pkt(self):
        pkt_ctrl_nbr = '0027911735'
        ord_nbr = '4988900'
        whse = '91'

        # Hay otro PKT activo (stat_code = 50) para el mismo pedido/reserva
        all_wms_pkts = [
            {'pkt_ctrl_nbr': '0027911735', 'stat_code': 99},
            {'pkt_ctrl_nbr': '0028004274', 'stat_code': 50}
        ]

        # En ODBMS ambos PKTs están asignados al mismo SKU
        odbms_details = [
            {
                'pedido': '4988900',
                'sku': '4460308',
                'estadopedido': 'PENDIENTE BODEGA',
                'est_pkt': 'CANCELADO',
                'cantidadpendiente': 1.0,
                'dist_pkt': '0027911735',
                'bodega': '91'
            },
            {
                'pedido': '4988900',
                'sku': '4460308',
                'estadopedido': 'PENDIENTE BODEGA',
                'est_pkt': 'PDTE.',
                'cantidadpendiente': 1.0,
                'dist_pkt': '0028004274',
                'bodega': '91'
            }
        ]

        self.mock_odbms_repo.get_sku_stock.return_value = (
            {
                'cc': '91',
                'sku': '4460308',
                'descrip': 'PRODUCTO DE PRUEBA',
                'disponible': 10.0,
                'total': 15.0
            },
            None
        )

        valido, detalle, rules, prod = self.service.validate_pkt(
            pkt_ctrl_nbr, ord_nbr, whse, all_wms_pkts, odbms_details
        )

        self.assertFalse(valido)
        self.assertEqual(rules["r6_sin_pkt_activo"]["status"], "rojo")
        self.assertIn("Existe otro PKT activo", rules["r6_sin_pkt_activo"]["desc"])

    def test_validate_pkt_pdte_bodega_status(self):
        pkt_ctrl_nbr = '0027911735'
        ord_nbr = '4988900'
        whse = '91'

        all_wms_pkts = [{'pkt_ctrl_nbr': '0027911735', 'stat_code': 99}]
        odbms_details = [{
            'pedido': '4988900',
            'sku': '4460308',
            'estadopedido': 'Pdte Bodega',
            'est_pkt': 'CANCELADO',
            'cantidadpendiente': 1.0,
            'dist_pkt': '0027911735',
            'bodega': '91'
        }]

        self.mock_odbms_repo.get_sku_stock.return_value = (
            {
                'cc': '91',
                'sku': '4460308',
                'descrip': 'PRODUCTO DE PRUEBA',
                'disponible': 10.0,
                'total': 15.0
            },
            None
        )

        valido, detalle, rules, prod = self.service.validate_pkt(
            pkt_ctrl_nbr, ord_nbr, whse, all_wms_pkts, odbms_details
        )

        self.assertTrue(valido)
        self.assertEqual(rules["r4_pedido_pendiente"]["status"], "verde")
        self.assertIn("Pdte Bodega", rules["r4_pedido_pendiente"]["desc"])

if __name__ == '__main__':
    unittest.main()
