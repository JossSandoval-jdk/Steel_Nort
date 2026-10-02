// Traduccion entre los codigos de la base y las palabras que usa la interfaz.
//
// La tabla alertas y el mapa de calor guardan una letra (los CHECK del
// esquema lo obligan): C/A/M/B para severidad, y el trigger
// TR_alertas_hma_rollup aplasta a dos niveles en el heatmap.
//
// El frontend, en cambio, trabaja con palabras porque las clases CSS estan
// escritas asi: .rol-pill.critica, .alert-dot.alta, .leyenda-item.criticas.
// Si se pintara la letra suelta, esas reglas no aplicarian y el badge saldria
// sin color.
//
// Por eso la conversion se hace una sola vez, al entrar el dato de la API, y
// de ahi para adelante todo el codigo sigue viendo palabras.

// CK_alt_sev: C = critica, A = alta, M = media, B = baja.
export const SEVERIDAD_A_PALABRA = {
  C: 'critica',
  A: 'alta',
  M: 'media',
  B: 'baja',
}

// heatmap_anomalias.hma_sev solo tiene 'A' (critica o alta) y 'B' (media o baja).
export const NIVEL_A_PALABRA = {
  A: 'alta',
  B: 'baja',
}

export function severidad(alt_sev) {
  return SEVERIDAD_A_PALABRA[alt_sev] || 'media'
}

// Convierte una fila de /deteccion/alertas para que alt_sev sea una palabra.
export function normalizarAlerta(alerta) {
  if (!alerta) return alerta
  return { ...alerta, alt_sev: severidad(alerta.alt_sev) }
}

// La v2 pagina: {total, pagina, tamano, items}. Las pantallas pintan la lista
// directamente, asi que se devuelve solo items ya normalizada.
export function alertasDesdePagina(pagina) {
  const items = (pagina && pagina.items) || []
  return items.map(normalizarAlerta)
}