import { useEffect, useState } from 'react'
import Sidebar from '../../components/Sidebar.jsx'
import Topbar from '../../components/Topbar.jsx'
import { useAuth } from '../../hooks/useAuth.js'
import api from '../../services/api.js'
import '../../css/Layout.css'
import './Reportes_v2.css'

// ==================== PESTAÑAS ====================
const PESTANAS = [
  { id: 'rendimiento',   titulo: 'Informe de Rendimiento' },
  { id: 'anomalias',     titulo: 'Informe de Anomalías Detallado' },
  { id: 'alertas',       titulo: 'Historial de Alertas Generales' },
  { id: 'exportaciones', titulo: 'Exportaciones' },
]

const TAMANO = 50

// Etiquetas de severidad y estado (los codigos vienen de la base v2).
const SEV = { C: 'Crítica', A: 'Alta', M: 'Media', B: 'Baja' }
const EST = { A: 'Abierta', R: 'En revisión', S: 'Resuelta', F: 'Descartada' }

// Tipos de dataset exportables y formatos (sin PDF/Excel: no hay librerias).
const TIPOS = [
  { id: 'resumen',   texto: 'Resumen del periodo' },
  { id: 'alertas',   texto: 'Alertas' },
  { id: 'anomalias', texto: 'Anomalías' },
]

// ==================== HELPERS ====================
function fechaHora(valor) {
  if (!valor) return '—'
  const d = new Date(valor)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString('es', { dateStyle: 'short', timeStyle: 'short' })
}

function numero(valor, decimales = 2) {
  if (valor === null || valor === undefined) return '—'
  return Number(valor).toLocaleString('es', {
    minimumFractionDigits: decimales,
    maximumFractionDigits: decimales,
  })
}

function bytes(valor) {
  if (!valor && valor !== 0) return '—'
  if (valor < 1024) return `${valor} B`
  if (valor < 1024 * 1024) return `${numero(valor / 1024, 1)} KB`
  return `${numero(valor / (1024 * 1024), 1)} MB`
}

// Extrae la extension (csv/json) del nombre del archivo exportado.
function formatoDe(nombre) {
  const ext = (nombre || '').split('.').pop().toLowerCase()
  return ['csv', 'json'].includes(ext) ? ext : 'csv'
}

// ==================== COMPONENTE ====================
function Reportes_v2() {
  const { user, accessToken } = useAuth()
  const nombre = user?.usu_nom || 'Nombre Usuario'
  const cargo = user?.usu_rol || 'Cargo'

  // --- Pestaña activa ---
  const [pestana, setPestana] = useState('rendimiento')

  // --- Filtros ---
  const [desde, setDesde] = useState('')
  const [hasta, setHasta] = useState('')
  const [severidad, setSeveridad] = useState('')
  const [estado, setEstado] = useState('')
  const [tipoInforme, setTipoInforme] = useState('resumen')
  const [formato, setFormato] = useState('csv')

  // --- Datos reales ---
  const [resumen, setResumen] = useState(null)
  const [anomalias, setAnomalias] = useState([])
  const [alertas, setAlertas] = useState([])
  const [exportados, setExportados] = useState([])
  const [total, setTotal] = useState(0)

  const [pagina, setPagina] = useState(1)
  const [cargando, setCargando] = useState(true)
  const [generando, setGenerando] = useState(false)
  const [error, setError] = useState('')
  const [recarga, setRecarga] = useState(0)

  // Carga los datos de la pestaña activa cada vez que cambian filtros o pagina.
  useEffect(() => {
    if (!accessToken) return undefined
    let vivo = true

    const p = new URLSearchParams()
    if (desde) p.set('desde', `${desde}T00:00:00`)
    if (hasta) p.set('hasta', `${hasta}T23:59:59`)
    if (severidad) p.set('severidad', severidad)
    if (estado) p.set('estado', estado)
    const q = p.toString()

    let tarea
    if (pestana === 'rendimiento') {
      tarea = Promise.all([
        api.get(`/informes/resumen?${q}`, { token: accessToken }),
        api.get('/informes/exportados', { token: accessToken }),
      ]).then(([res, exp]) => {
        if (!vivo) return
        setResumen(res)
        setExportados(exp)
      })
    } else if (pestana === 'anomalias') {
      tarea = api
        .get(`/informes/anomalias?${q}&pagina=${pagina}&tamano=${TAMANO}`, { token: accessToken })
        .then((r) => {
          if (!vivo) return
          setAnomalias(r.items || [])
          setTotal(r.total || 0)
        })
    } else if (pestana === 'alertas') {
      tarea = api
        .get(`/informes/alertas?${q}&pagina=${pagina}&tamano=${TAMANO}`, { token: accessToken })
        .then((r) => {
          if (!vivo) return
          setAlertas(r.items || [])
          setTotal(r.total || 0)
        })
    } else {
      tarea = api.get('/informes/exportados', { token: accessToken }).then((r) => {
        if (vivo) setExportados(r)
      })
    }

    tarea
      .catch((e) => { if (vivo) setError(e.message || 'No se pudieron cargar los informes.') })
      .finally(() => { if (vivo) setCargando(false) })

    return () => { vivo = false }
  }, [accessToken, pestana, pagina, recarga, desde, hasta, severidad, estado])

  // --- Acciones ---
  // Marca el inicio de una carga; el effect solo la apaga al terminar.
  const marcarCarga = () => {
    setCargando(true)
    setError('')
  }

  const cambiarPestana = (id) => {
    marcarCarga()
    setPagina(1)
    setPestana(id)
  }

  const irPagina = (n) => {
    marcarCarga()
    setPagina(n)
  }

  const cambiarFecha = (campo, valor) => {
    marcarCarga()
    setPagina(1)
    if (campo === 'desde') setDesde(valor)
    else setHasta(valor)
  }

  const cambiarFiltro = (campo, valor) => {
    marcarCarga()
    setPagina(1)
    if (campo === 'severidad') setSeveridad(valor)
    else setEstado(valor)
  }

  const generar = async (tipo = tipoInforme, formatoSel = formato) => {
    setGenerando(true)
    setError('')
    try {
      await api.post(
        '/informes/generar',
        {
          tipo,
          formato: formatoSel,
          desde: desde ? `${desde}T00:00:00` : null,
          hasta: hasta ? `${hasta}T23:59:59` : null,
        },
        { token: accessToken },
      )
      marcarCarga()
      setRecarga((r) => r + 1)
    } catch (e) {
      setError(e.message || 'No se pudo generar el informe.')
    } finally {
      setGenerando(false)
    }
  }

  const descargar = async (archivoNombre) => {
    setError('')
    try {
      const blob = await api.archivo(
        `/informes/exportados/${encodeURIComponent(archivoNombre)}`,
        { token: accessToken },
      )
      const url = URL.createObjectURL(blob)
      const enlace = document.createElement('a')
      enlace.href = url
      enlace.download = archivoNombre
      document.body.appendChild(enlace)
      enlace.click()
      enlace.remove()
      URL.revokeObjectURL(url)
    } catch (e) {
      setError(e.message || 'No se pudo descargar el archivo.')
    }
  }

  const borrar = async (archivoNombre) => {
    if (!window.confirm(`¿Eliminar ${archivoNombre}?`)) return
    setError('')
    try {
      await api.del(`/informes/exportados/${encodeURIComponent(archivoNombre)}`, { token: accessToken })
      marcarCarga()
      setRecarga((r) => r + 1)
    } catch (e) {
      setError(e.message || 'No se pudo eliminar el archivo.')
    }
  }

  const paginas = Math.max(1, Math.ceil(total / TAMANO))
  const porSev = resumen?.por_severidad || {}

  return (
    <div className="layout">
      <Sidebar />
      <div className="layout-main">
        <Topbar nombre={nombre} cargo={cargo} />
        <main className="layout-content">
          <section className="informes">

            {/* ===== PESTAÑAS ===== */}
            <div className="informes-tabs" role="tablist">
              {PESTANAS.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  role="tab"
                  aria-selected={pestana === p.id}
                  className={pestana === p.id ? 'informes-tab activa' : 'informes-tab'}
                  onClick={() => cambiarPestana(p.id)}
                >
                  {p.titulo}
                </button>
              ))}
            </div>

            {error && <p className="informes-error">{error}</p>}
            {cargando && <p className="informes-subtitulo">Actualizando…</p>}

            {/* ================================================== */}
            {/* PESTAÑA 1 — RENDIMIENTO                            */}
            {/* ================================================== */}
            {pestana === 'rendimiento' && (
              <>
                <header className="informes-cabecera">
                  <h1>Generador de Informes Personalizado</h1>
                  <p className="informes-subtitulo">
                    Resumen real del periodo tomado de la base v2. Los informes se exportan en CSV/JSON.
                  </p>
                </header>

                <div className="informes-filtros-grid">
                  <div className="informes-campo">
                    <label className="informes-etiqueta">Rango de fechas</label>
                    <div className="informes-fila">
                      <input type="date" value={desde} onChange={(e) => cambiarFecha('desde', e.target.value)} />
                      <input type="date" value={hasta} onChange={(e) => cambiarFecha('hasta', e.target.value)} />
                    </div>
                  </div>

                  <div className="informes-campo">
                    <label className="informes-etiqueta">Tipo de reporte</label>
                    <div className="informes-fila">
                      <select value={tipoInforme} onChange={(e) => setTipoInforme(e.target.value)}>
                        {TIPOS.map((t) => (
                          <option key={t.id} value={t.id}>{t.texto}</option>
                        ))}
                      </select>
                      <select value={formato} onChange={(e) => setFormato(e.target.value)}>
                        <option value="csv">CSV</option>
                        <option value="json">JSON</option>
                      </select>
                    </div>
                  </div>
                </div>

                <div className="informes-acciones">
                  <button type="button" className="informes-btn-generar" disabled={generando} onClick={() => generar()}>
                    {generando ? 'Generando…' : 'Generar Informe'}
                  </button>
                </div>

                {/* KPIs reales */}
                <section className="informes-seccion">
                  <h2>Resumen del Periodo</h2>
                  <div className="informes-kpis">
                    <div className="informes-kpi">
                      <span className="informes-kpi-valor">{resumen?.ventanas ?? 0}</span>
                      <span className="informes-kpi-etiqueta">Ventanas evaluadas</span>
                    </div>
                    <div className="informes-kpi">
                      <span className="informes-kpi-valor">{resumen?.anomalias ?? 0}</span>
                      <span className="informes-kpi-etiqueta">Anomalías</span>
                    </div>
                    <div className="informes-kpi">
                      <span className="informes-kpi-valor">{resumen?.alertas ?? 0}</span>
                      <span className="informes-kpi-etiqueta">Alertas</span>
                    </div>
                    <div className="informes-kpi">
                      <span className="informes-kpi-valor">{resumen?.eventos ?? 0}</span>
                      <span className="informes-kpi-etiqueta">Eventos SQL</span>
                    </div>
                    <div className="informes-kpi">
                      <span className="informes-kpi-valor">{resumen?.logs ?? 0}</span>
                      <span className="informes-kpi-etiqueta">Logs SQL</span>
                    </div>
                  </div>
                  <p className="informes-subtitulo">
                    Alertas por severidad: Crítica {porSev.C ?? 0} · Alta {porSev.A ?? 0} ·
                    Media {porSev.M ?? 0} · Baja {porSev.B ?? 0}
                  </p>
                </section>

                {/* Resumen por nodo */}
                <section className="informes-seccion">
                  <h2>Resumen por Nodo</h2>
                  <div className="informes-tabla-scroll">
                    <table className="informes-tabla">
                      <thead>
                        <tr>
                          <th>Instancia</th>
                          <th>Ventanas</th>
                          <th>Anomalías</th>
                          <th>Alertas</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(resumen?.por_instancia || []).map((fila) => (
                          <tr key={fila.instancia}>
                            <td>{fila.instancia || '—'}</td>
                            <td>{fila.ventanas}</td>
                            <td>{fila.anomalias}</td>
                            <td>{fila.alertas}</td>
                          </tr>
                        ))}
                        {!resumen?.por_instancia?.length && (
                          <tr><td className="informes-detalle-col" colSpan={4}>Sin datos en el rango.</td></tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </section>

                {/* Resumen por tipo de evento */}
                <section className="informes-seccion">
                  <h2>Resumen por Tipo de Evento SQL</h2>
                  <div className="informes-tabla-scroll">
                    <table className="informes-tabla">
                      <thead>
                        <tr>
                          <th>Tipo de Evento</th>
                          <th>Ejecuciones</th>
                          <th>Duración Promedio (ms)</th>
                          <th>Con espera</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(resumen?.por_evento || []).map((fila) => (
                          <tr key={fila.tipo}>
                            <td>{fila.tipo}</td>
                            <td>{fila.ejecuciones}</td>
                            <td>{numero(fila.dur_prom_ms, 2)}</td>
                            <td>{fila.con_espera}</td>
                          </tr>
                        ))}
                        {!resumen?.por_evento?.length && (
                          <tr><td className="informes-detalle-col" colSpan={4}>Sin datos en el rango.</td></tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </section>

                {/* Informes generados recientemente */}
                <section className="informes-seccion">
                  <h2>Informes Generados Recientemente</h2>
                  <div className="informes-tabla-scroll">
                    <table className="informes-tabla">
                      <thead>
                        <tr>
                          <th>Marca de Tiempo</th>
                          <th>Archivo</th>
                          <th>Formato</th>
                          <th>Tamaño</th>
                          <th>Acciones</th>
                        </tr>
                      </thead>
                      <tbody>
                        {exportados.slice(0, 8).map((arch) => (
                          <tr key={arch.nombre}>
                            <td>{fechaHora(arch.modificado)}</td>
                            <td>{arch.nombre}</td>
                            <td>
                              <span className={`informes-formato formato-${formatoDe(arch.nombre)}`}>
                                {formatoDe(arch.nombre).toUpperCase()}
                              </span>
                            </td>
                            <td>{bytes(arch.bytes)}</td>
                            <td>
                              <div className="informes-acciones-col">
                                <button type="button" className="informes-btn-icono" title="Descargar" onClick={() => descargar(arch.nombre)}>⬇</button>
                                <button type="button" className="informes-btn-icono" title="Eliminar" onClick={() => borrar(arch.nombre)}>🗑</button>
                              </div>
                            </td>
                          </tr>
                        ))}
                        {!exportados.length && (
                          <tr><td className="informes-detalle-col" colSpan={5}>Aún no se ha generado ningún informe.</td></tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </section>
              </>
            )}

            {/* ================================================== */}
            {/* PESTAÑA 2 — ANOMALÍAS DETALLADO                    */}
            {/* ================================================== */}
            {pestana === 'anomalias' && (
              <>
                <header className="informes-cabecera">
                  <h1>Informe de Anomalías Detallado</h1>
                  <p className="informes-subtitulo">
                    Variables fuera de rango detectadas por el modelo ML, con su severidad y nodo.
                  </p>
                </header>

                <div className="informes-filtros-grid">
                  <div className="informes-campo">
                    <label className="informes-etiqueta">Rango de fechas</label>
                    <div className="informes-fila">
                      <input type="date" value={desde} onChange={(e) => cambiarFecha('desde', e.target.value)} />
                      <input type="date" value={hasta} onChange={(e) => cambiarFecha('hasta', e.target.value)} />
                    </div>
                  </div>

                  <div className="informes-campo">
                    <label className="informes-etiqueta">Filtros de anomalía</label>
                    <div className="informes-fila">
                      <select value={severidad} onChange={(e) => cambiarFiltro('severidad', e.target.value)}>
                        <option value="">Todas las severidades</option>
                        <option value="C">Crítica</option>
                        <option value="A">Alta</option>
                        <option value="M">Media</option>
                        <option value="B">Baja</option>
                      </select>
                    </div>
                  </div>
                </div>

                <div className="informes-acciones">
                  <button type="button" className="informes-btn-secundario" disabled={generando} onClick={() => generar('anomalias', 'csv')}>Exportar CSV</button>
                  <button type="button" className="informes-btn-secundario" disabled={generando} onClick={() => generar('anomalias', 'json')}>Exportar JSON</button>
                </div>

                <section className="informes-seccion">
                  <h2>Anomalías Detectadas ({total} registros)</h2>
                  <div className="informes-tabla-scroll">
                    <table className="informes-tabla">
                      <thead>
                        <tr>
                          <th>Fecha</th>
                          <th>Variable</th>
                          <th>Valor</th>
                          <th>Z-Score</th>
                          <th>Severidad</th>
                          <th>Instancia</th>
                        </tr>
                      </thead>
                      <tbody>
                        {anomalias.map((a) => (
                          <tr key={a.alv_cod}>
                            <td>{fechaHora(a.fecha)}</td>
                            <td>{a.variable}</td>
                            <td>{numero(a.valor, 2)}</td>
                            <td>{a.z === null || a.z === undefined ? 'sin base' : numero(a.z, 2)}</td>
                            <td><span className={`informes-sev sev-${a.severidad}`}>{SEV[a.severidad] || a.severidad}</span></td>
                            <td>{a.instancia || '—'}</td>
                          </tr>
                        ))}
                        {!anomalias.length && (
                          <tr><td className="informes-detalle-col" colSpan={6}>No hay anomalías para estos filtros.</td></tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                  {paginas > 1 && (
                    <div className="informes-acciones">
                      <button type="button" className="informes-btn-secundario" disabled={pagina <= 1} onClick={() => irPagina(pagina - 1)}>Anterior</button>
                      <span className="informes-subtitulo">Página {pagina} de {paginas}</span>
                      <button type="button" className="informes-btn-secundario" disabled={pagina >= paginas} onClick={() => irPagina(pagina + 1)}>Siguiente</button>
                    </div>
                  )}
                </section>
              </>
            )}

            {/* ================================================== */}
            {/* PESTAÑA 3 — HISTORIAL DE ALERTAS                   */}
            {/* ================================================== */}
            {pestana === 'alertas' && (
              <>
                <header className="informes-cabecera">
                  <h1>Historial de Alertas Generales</h1>
                  <p className="informes-subtitulo">
                    Registro de alertas generadas por el sistema, con su severidad y estado.
                  </p>
                </header>

                <div className="informes-filtros-grid">
                  <div className="informes-campo">
                    <label className="informes-etiqueta">Rango de fechas</label>
                    <div className="informes-fila">
                      <input type="date" value={desde} onChange={(e) => cambiarFecha('desde', e.target.value)} />
                      <input type="date" value={hasta} onChange={(e) => cambiarFecha('hasta', e.target.value)} />
                    </div>
                  </div>

                  <div className="informes-campo">
                    <label className="informes-etiqueta">Filtros de alertas</label>
                    <div className="informes-fila">
                      <select value={severidad} onChange={(e) => cambiarFiltro('severidad', e.target.value)}>
                        <option value="">Todas las prioridades</option>
                        <option value="C">Crítica</option>
                        <option value="A">Alta</option>
                        <option value="M">Media</option>
                        <option value="B">Baja</option>
                      </select>
                      <select value={estado} onChange={(e) => cambiarFiltro('estado', e.target.value)}>
                        <option value="">Todos los estados</option>
                        <option value="A">Abierta</option>
                        <option value="R">En revisión</option>
                        <option value="S">Resuelta</option>
                        <option value="F">Descartada</option>
                      </select>
                    </div>
                  </div>
                </div>

                <div className="informes-acciones">
                  <button type="button" className="informes-btn-secundario" disabled={generando} onClick={() => generar('alertas', 'csv')}>Exportar CSV</button>
                  <button type="button" className="informes-btn-secundario" disabled={generando} onClick={() => generar('alertas', 'json')}>Exportar JSON</button>
                </div>

                <section className="informes-seccion">
                  <h2>Alertas Registradas ({total} registros)</h2>
                  <div className="informes-tabla-scroll">
                    <table className="informes-tabla">
                      <thead>
                        <tr>
                          <th>Fecha</th>
                          <th>Título</th>
                          <th>Prioridad</th>
                          <th>Estado</th>
                          <th>Detalle</th>
                          <th>Instancia</th>
                        </tr>
                      </thead>
                      <tbody>
                        {alertas.map((a) => (
                          <tr key={a.alt_cod}>
                            <td>{fechaHora(a.alt_fec)}</td>
                            <td>{a.alt_titulo}</td>
                            <td><span className={`informes-sev sev-${a.alt_sev}`}>{SEV[a.alt_sev] || a.alt_sev}</span></td>
                            <td><span className={`informes-est est-${a.alt_est}`}>{EST[a.alt_est] || a.alt_est}</span></td>
                            <td className="informes-detalle-col" title={a.alt_diag || ''}>{a.alt_diag || '—'}</td>
                            <td>{a.instancia || '—'}</td>
                          </tr>
                        ))}
                        {!alertas.length && (
                          <tr><td className="informes-detalle-col" colSpan={6}>No hay alertas para estos filtros.</td></tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                  {paginas > 1 && (
                    <div className="informes-acciones">
                      <button type="button" className="informes-btn-secundario" disabled={pagina <= 1} onClick={() => irPagina(pagina - 1)}>Anterior</button>
                      <span className="informes-subtitulo">Página {pagina} de {paginas}</span>
                      <button type="button" className="informes-btn-secundario" disabled={pagina >= paginas} onClick={() => irPagina(pagina + 1)}>Siguiente</button>
                    </div>
                  )}
                </section>
              </>
            )}

            {/* ================================================== */}
            {/* PESTAÑA 4 — EXPORTACIONES                          */}
            {/* ================================================== */}
            {pestana === 'exportaciones' && (
              <>
                <header className="informes-cabecera">
                  <h1>Exportaciones</h1>
                  <p className="informes-subtitulo">
                    Archivos reales (CSV/JSON) generados desde la base v2 y disponibles para descarga.
                  </p>
                </header>

                <section className="informes-seccion">
                  <h2>Archivos Exportados ({exportados.length})</h2>
                  <div className="informes-tabla-scroll">
                    <table className="informes-tabla">
                      <thead>
                        <tr>
                          <th>Fecha</th>
                          <th>Nombre del Archivo</th>
                          <th>Formato</th>
                          <th>Tamaño</th>
                          <th>Acciones</th>
                        </tr>
                      </thead>
                      <tbody>
                        {exportados.map((arch) => (
                          <tr key={arch.nombre}>
                            <td>{fechaHora(arch.modificado)}</td>
                            <td>{arch.nombre}</td>
                            <td>
                              <span className={`informes-formato formato-${formatoDe(arch.nombre)}`}>
                                {formatoDe(arch.nombre).toUpperCase()}
                              </span>
                            </td>
                            <td>{bytes(arch.bytes)}</td>
                            <td>
                              <div className="informes-acciones-col">
                                <button type="button" className="informes-btn-icono" title="Descargar" onClick={() => descargar(arch.nombre)}>⬇</button>
                                <button type="button" className="informes-btn-icono" title="Eliminar" onClick={() => borrar(arch.nombre)}>🗑</button>
                              </div>
                            </td>
                          </tr>
                        ))}
                        {!exportados.length && (
                          <tr><td className="informes-detalle-col" colSpan={5}>Aún no hay exportaciones.</td></tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </section>
              </>
            )}

          </section>
        </main>
      </div>
    </div>
  )
}

export default Reportes_v2
