"""Testes unitários das regras de domínio do cardápio.

Executar em um ambiente com as dependências do backend:
    python -m unittest backend.test_cardapio
"""

import unittest

from routes.stores import _parse_price, _validate_selection_limits, _validate_status


class CardapioValidationTest(unittest.TestCase):
    def test_parse_price_accepts_decimal_comma(self):
        self.assertEqual(_parse_price("4,50"), 4.5)

    def test_parse_price_rejects_negative(self):
        with self.assertRaisesRegex(ValueError, "não pode ser negativo"):
            _parse_price(-1)

    def test_option_group_limits_must_be_coherent(self):
        self.assertEqual(_validate_selection_limits("0", "3"), (0, 3))
        with self.assertRaisesRegex(ValueError, "não pode superar"):
            _validate_selection_limits(3, 2)

    def test_status_is_restricted_to_contract_values(self):
        self.assertEqual(_validate_status("available"), "AVAILABLE")
        with self.assertRaisesRegex(ValueError, "Status inválido"):
            _validate_status("ARCHIVED")


if __name__ == "__main__":
    unittest.main()
