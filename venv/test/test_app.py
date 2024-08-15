import pytest
from app import luhn_check, get_card_type, get_mii, get_bin_info

def test_luhn_check():
    assert luhn_check("4111111111111111")  # Tarjeta válida de Visa
    assert not luhn_check("4111111111111112")  # Tarjeta inválida

def test_get_card_type():
    assert get_card_type("4111111111111111") == "Visa"
    assert get_card_type("5105105105105100") == "MasterCard"
    assert get_card_type("378282246310005") == "American Express"
    assert get_card_type("6011111111111117") == "Discover"
    assert get_card_type("1234567890123456") == "Unknown"

def test_get_mii():
    assert get_mii("4111111111111111") == "Banking and Financial"
    assert get_mii("378282246310005") == "Travel and Entertainment"
    assert get_mii("1234567890123456") == "Unknown"

# Mock de la respuesta para pruebas de BIN
def test_get_bin_info(monkeypatch):
    def mock_get(*args, **kwargs):
        class MockResponse:
            def json(self):
                return {
                    "bank": {"name": "Test Bank"},
                    "country": {"name": "Test Country"},
                    "scheme": "visa",
                    "type": "debit"
                }
            status_code = 200
        return MockResponse()

    monkeypatch.setattr('requests.get', mock_get)
    bin_info = get_bin_info("411111")
    assert bin_info["bank"] == "Test Bank"
    assert bin_info["country"] == "Test Country"
    assert bin_info["brand"] == "visa"
    assert bin_info["type"] == "debit"
