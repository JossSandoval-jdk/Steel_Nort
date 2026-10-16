"""Pruebas del enmascarado de SQL (Ley N.° 29733).

``enmascarar_sql`` es una función pura: no toca base de datos ni servicios.
"""

from app.v2.services.privacidad import MASCARA, enmascarar_sql


def test_enmascara_literal_de_texto():
    salida = enmascarar_sql("SELECT * FROM t WHERE dni = '45123456'")
    assert "'***'" in salida
    assert "45123456" not in salida


def test_enmascara_correo_suelto():
    salida = enmascarar_sql("mail a@b.com")
    assert "a@b.com" not in salida
    assert MASCARA in salida


def test_enmascara_numero_de_tarjeta():
    salida = enmascarar_sql("tarjeta 4111 1111 1111 1111")
    assert "4111" not in salida
    assert MASCARA in salida


def test_enmascara_cadena_larga_de_digitos():
    salida = enmascarar_sql("cuenta 123456789")
    assert "123456789" not in salida
    assert MASCARA in salida


def test_enmascara_valor_ligado():
    salida = enmascarar_sql("@P1=16002")
    assert "@P1=" in salida
    assert "16002" not in salida


def test_none_y_vacio_se_devuelven_igual():
    assert enmascarar_sql(None) is None
    assert enmascarar_sql("") == ""


def test_recorta_textos_muy_largos():
    salida = enmascarar_sql("x" * 900)
    assert salida.endswith("…[recortado]")
    assert len(salida) < 900
