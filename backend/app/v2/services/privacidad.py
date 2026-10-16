"""Enmascarado de datos sensibles del SQL crudo antes de mostrarlo.

Los eventos guardan el texto SQL que ejecuto el sistema monitoreado
(``eventos.eve_sql``). Ese texto puede traer literales con datos de clientes
(nombres, DNIs, correos, importes), y la Ley N.° 29733 (Proteccion de Datos
Personales del Peru) pide no exponerlos.

``enmascarar_sql`` reemplaza esos literales por ``***`` **al responder la API**;
la fila original queda intacta en la base para el analisis forense. Asi el
usuario ve la *estructura* de la consulta sin ver los valores.
"""

from __future__ import annotations

import re

# Literales de texto: 'algo' o N'algo' (con comillas escapadas '').
_TEXTO = re.compile(r"(N?)'(?:[^']|'')*'", re.IGNORECASE)
# Numero de tarjeta: 16 digitos, con o sin separadores.
_TARJETA = re.compile(r"\b\d{4}[ -]?\d{4}[ -]?\d{4}[ -]?\d{4}\b")
# Correos electronicos.
_CORREO = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# Cadenas largas de digitos: DNI (8), RUC (11), telefonos, cuentas.
_DIGITOS = re.compile(r"\b\d{6,}\b")
# Valores ligados: @P1=16002 o @id = 45.
_LIGADO = re.compile(r"(@\w+)\s*=\s*[^,\s)]+")
# Valores numericos comparados: dni=45123456, saldo = 15000, id>1000.
_NUMERO = re.compile(r"([=<>])\s*\d+(?:\.\d+)?")

MASCARA = "***"
LIMITE = 800


def enmascarar_sql(texto: str | None, limite: int = LIMITE) -> str | None:
    """Devuelve el SQL con los literales sensibles cambiados por ``***``.

    El orden importa: primero los literales completos (que pueden contener
    comillas, correos o digitos), despues los valores ligados y al final los
    numeros comparados.
    """
    if not texto:
        return texto

    resultado = _TEXTO.sub("'***'", texto)
    resultado = _TARJETA.sub(MASCARA, resultado)
    resultado = _CORREO.sub(MASCARA, resultado)
    resultado = _DIGITOS.sub(MASCARA, resultado)
    resultado = _LIGADO.sub(lambda m: f"{m.group(1)}={MASCARA}", resultado)
    resultado = _NUMERO.sub(lambda m: f"{m.group(1)} {MASCARA}", resultado)

    if len(resultado) > limite:
        resultado = resultado[:limite] + " …[recortado]"
    return resultado
