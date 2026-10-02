import { useEffect, useState } from 'react'
import Sidebar from '../components/Sidebar.jsx'
import Topbar from '../components/Topbar.jsx'
import { useAuth } from '../context/AuthContext.jsx'
import api from '../services/api.js'
import { alertasDesdePagina } from '../services/severidad.js'
import '../css/Layout.css'
import '../css/Reportes.css'

const PESTANAS = [
  { id: 'alertas', titulo: 'Alertas', descripcion: 'Anomalías confirmadas por el sistema.' },
  { id: 'eventos', titulo: 'Eventos SQL', descripcion: 'Consultas y actividad relacionada con las alertas.' },
  { id: 'logs', titulo: 'Logs SQL', descripcion: 'Errores y avisos reportados por SQL Server.' },
  { id: 'sesiones', titulo: 'Sesiones SQL', descripcion: 'Conexiones observadas durante la actividad.' },
]
const TAMANO_PAGINA = 50
//const FILTROS_VACIOS = { desde: '', hasta: '', severidad: '', nivel: '', tipo: '', estado: '' }

function fecha(valor) {
  if (!valor) return '—'
  const dato = new Date(valor)
  return Number.isNaN(dato.getTime())
    ? '—'
    : dato.toLocaleString('es', { dateStyle: 'short', timeStyle: 'short' })
}

function fechaHoyLocal() {
  const ahora = new Date()
  const dia = `${ahora.getFullYear()}-${String(ahora.getMonth() + 1).padStart(2, '0')}-${String(ahora.getDate()).padStart(2, '0')}`
  return { desde: `${dia}T00:00`, hasta: `${dia}T23:59` }
}

function fechaHoraUtc(valor) {
  if (!valor) return ''
  const fechaLocal = new Date(valor)
  return Number.isNaN(fechaLocal.getTime()) ? '' : fechaLocal.toISOString().slice(0, 23)
}

function textoEvento(valor) {
  return {
    'xe.error_reported': 'Error SQL',
    'xe.xml_deadlock_report': 'Interbloqueo',
    'xe.sql_batch_completed': 'Consulta completada',
    'xe.rpc_completed': 'Procedimiento ejecutado',
  }[valor] || valor || 'Actividad SQL'
}

function Reportes() {
  const { user, accessToken } = useAuth()
  const [pestana, setPestana] = useState('alertas')
  const [datos, setDatos] = useState([])
  const [total, setTotal] = useState(0)
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState('')
  const [recarga, setRecarga] = useState(0)
  const [pagina, setPagina] = useState(1)
  const [filtros, setFiltros] = useState(() => ({
    ...fechaHoyLocal(), severidad: '', nivel: '', tipo: '', estado: '',
  }))

  useEffect(() => {
    if (!accessToken) return undefined
    let vigente = true
    const configuracion = {
      alertas: { ruta: '/deteccion/alertas', orden: '-alt_fec' },
      eventos: { ruta: '/datos/eventos', orden: '-eve_fec' },
      logs: { ruta: '/datos/logs', orden: '-lgs_fec' },
      sesiones: { ruta: '/nodos/sesiones-sql', orden: '-ssq_fec_ini' },
    }
    const parametros = new URLSearchParams({
      pagina: String(pagina),
      tamano: String(TAMANO_PAGINA),
      orden: configuracion[pestana].orden,
    })
    const desde = fechaHoraUtc(filtros.desde)
    const hasta = fechaHoraUtc(filtros.hasta)
    if (desde) parametros.set('desde', desde)
    if (hasta) parametros.set('hasta', hasta)
    if (pestana === 'alertas') {
      if (filtros.severidad) parametros.set('severidad', filtros.severidad)
      if (filtros.estado) parametros.set('estado', filtros.estado)
    }
    if (pestana === 'eventos' && filtros.tipo) parametros.set('tipo', filtros.tipo)
    if (pestana === 'logs' && filtros.nivel) parametros.set('nivel', filtros.nivel)
    if (pestana === 'sesiones' && filtros.estado) parametros.set('estado', filtros.estado)

    api.get(`${configuracion[pestana].ruta}?${parametros.toString()}`, { token: accessToken })
      .then((respuesta) => {
        if (!vigente) return
        const items = pestana === 'alertas'
          ? alertasDesdePagina(respuesta)
          : respuesta?.items || []
        setDatos(items)
        setTotal(respuesta?.total ?? items.length)
      })
      .catch((err) => {
        if (!vigente) return
        setError(err.message || 'No se pudieron cargar los reportes.')
        setDatos([])
        setTotal(0)
      })
      .finally(() => {
        if (vigente) setCargando(false)
      })

    return () => { vigente = false }
  }, [accessToken, pestana, recarga, pagina, filtros])

  const activa = PESTANAS.find((item) => item.id === pestana)
  const nombre = user?.usu_nom || 'Nombre Usuario'
  const cargo = user?.usu_rol || 'Cargo'
  const paginas = Math.max(1, Math.ceil(total / TAMANO_PAGINA))

  const cambiarFiltro = (nombre, valor) => {
    setCargando(true)
    setError('')
    setFiltros((actuales) => ({ ...actuales, [nombre]: valor }))
    setPagina(1)
  }

  const limpiarFiltros = () => {
    setCargando(true)
    setError('')
    setFiltros({ ...fechaHoyLocal(), severidad: '', nivel: '', tipo: '', estado: '' })
    setPagina(1)
  }

  const columnas = { alertas: 5, eventos: 5, logs: 4, sesiones: 6 }[pestana]

  return (
    <div className="layout">
      <Sidebar />
      <div className="layout-main">
        <Topbar nombre={nombre} cargo={cargo} />
        <main className="layout-content">
          <section className="reportes">
            <header className="reportes-cabecera">
              <div>
                <h1>Reportes</h1>
                <p>{activa?.descripcion}</p>
              </div>
              <button
                type="button"
                className="reportes-recargar"
                aria-label="Recargar reporte"
                title="Recargar"
                disabled={cargando}
                onClick={() => {
                  setCargando(true)
                  setRecarga((valor) => valor + 1)
                }}
              >
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M20 7v5h-5M4 17v-5h5" />
                  <path d="M5.6 9a7 7 0 0 1 11.7-2L20 12M4 12l2.7 5a7 7 0 0 0 11.7-2" />
                </svg>
              </button>
            </header>

            <div className="reportes-tabs" role="tablist" aria-label="Secciones de reportes">
              {PESTANAS.map((item) => (
                <button
                  key={item.id}
                  id={`tab-${item.id}`}
                  type="button"
                  role="tab"
                  aria-selected={pestana === item.id}
                  aria-controls="reportes-panel"
                  className={pestana === item.id ? 'reportes-tab activa' : 'reportes-tab'}
                  onClick={() => {
                    setCargando(true)
                    setError('')
                    setPagina(1)
                    setPestana(item.id)
                  }}
                >
                  {item.titulo}
                </button>
              ))}
            </div>

            <form className="reportes-filtros" onSubmit={(evento) => evento.preventDefault()}>
              <label>
                Desde
                <input
                  type="datetime-local"
                  value={filtros.desde}
                  onChange={(evento) => cambiarFiltro('desde', evento.target.value)}
                />
              </label>
              <label>
                Hasta
                <input
                  type="datetime-local"
                  value={filtros.hasta}
                  onChange={(evento) => cambiarFiltro('hasta', evento.target.value)}
                />
              </label>
              {pestana === 'alertas' && (
                <>
                  <label>
                    Severidad
                    <select value={filtros.severidad} onChange={(evento) => cambiarFiltro('severidad', evento.target.value)}>
                      <option value="">Todas</option>
                      <option value="C">Crítica</option>
                      <option value="A">Alta</option>
                      <option value="M">Media</option>
                      <option value="B">Baja</option>
                    </select>
                  </label>
                  <label>
                    Estado
                    <select value={filtros.estado} onChange={(evento) => cambiarFiltro('estado', evento.target.value)}>
                      <option value="">Todos</option>
                      <option value="A">Abierta</option>
                      <option value="R">En revisión</option>
                      <option value="S">Resuelta</option>
                      <option value="F">Descartada</option>
                    </select>
                  </label>
                </>
              )}
              {pestana === 'eventos' && (
                <label>
                  Actividad SQL
                  <select value={filtros.tipo} onChange={(evento) => cambiarFiltro('tipo', evento.target.value)}>
                    <option value="">Todas</option>
                    <option value="xe.error_reported">Error SQL</option>
                    <option value="xe.xml_deadlock_report">Interbloqueo</option>
                    <option value="xe.sql_batch_completed">Consulta completada</option>
                    <option value="xe.rpc_completed">Procedimiento ejecutado</option>
                  </select>
                </label>
              )}
              {pestana === 'logs' && (
                <label>
                  Nivel
                  <select value={filtros.nivel} onChange={(evento) => cambiarFiltro('nivel', evento.target.value)}>
                    <option value="">Todos</option>
                    <option value="E">Error</option>
                    <option value="W">Aviso</option>
                    <option value="I">Información</option>
                  </select>
                </label>
              )}
              {pestana === 'sesiones' && (
                <label>
                  Estado de sesión
                  <select value={filtros.estado} onChange={(evento) => cambiarFiltro('estado', evento.target.value)}>
                    <option value="">Todas</option>
                    <option value="A">Activa</option>
                    <option value="C">Cerrada</option>
                  </select>
                </label>
              )}
              <div className="reportes-filtros-acciones">
                <span className="reportes-filtros-auto">Actualiza al cambiar filtros</span>
                <button type="button" className="reportes-limpiar" onClick={limpiarFiltros}>Hoy / limpiar</button>
              </div>
            </form>

            <section
              id="reportes-panel"
              role="tabpanel"
              aria-labelledby={`tab-${pestana}`}
              className="reportes-panel card"
            >
              <div className="reportes-panel-cabecera">
                <div>
                  <h2>{activa?.titulo}</h2>
                  <p>{total} registros</p>
                </div>
                {cargando && <span className="reportes-estado">Actualizando…</span>}
              </div>

              {error ? (
                <p className="reportes-error">{error}</p>
              ) : (
                <div className="reportes-tabla-scroll">
                  <table className="reportes-tabla">
                    {pestana === 'alertas' && (
                      <>
                        <thead><tr><th>Fecha</th><th>Alerta</th><th>Prioridad</th><th>Estado</th><th>Detalle</th></tr></thead>
                        <tbody>
                          {datos.map((a) => (
                            <tr key={a.alt_cod}>
                              <td>{fecha(a.alt_fec)}</td>
                              <td>{a.alt_tipo === 'anomalia_ml' ? 'Cambio inusual en el servidor' : a.alt_titulo}</td>
                              <td><span className={`reportes-severidad ${a.alt_sev}`}>{a.alt_sev}</span></td>
                              <td>{({ A: 'Abierta', R: 'En revisión', S: 'Resuelta', F: 'Descartada' })[a.alt_est] || a.alt_est}</td>
                              <td className="reportes-detalle-col">{a.alt_desc || '—'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </>
                    )}
                    {pestana === 'eventos' && (
                      <>
                        <thead><tr><th>Fecha</th><th>Actividad</th><th>Sesión SQL</th><th>Duración</th><th>Detalle</th></tr></thead>
                        <tbody>
                          {datos.map((e) => (
                            <tr key={`${e.eve_cod}-${e.eve_fec}`}>
                              <td>{fecha(e.eve_fec)}</td>
                              <td>{textoEvento(e.eve_wait)}</td>
                              <td>{e.eve_sid ?? 'No identificada'}</td>
                              <td>{e.eve_dur == null ? '—' : `${(Number(e.eve_dur) / 1000).toFixed(2)} ms`}</td>
                              <td>{e.eve_sql || 'Sin texto SQL'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </>
                    )}
                    {pestana === 'logs' && (
                      <>
                        <thead><tr><th>Fecha</th><th>Nivel</th><th>Mensaje</th><th>Detalle</th></tr></thead>
                        <tbody>
                          {datos.map((l) => (
                            <tr key={`${l.lgs_cod}-${l.lgs_fec}`}>
                              <td>{fecha(l.lgs_fec)}</td>
                              <td>{{ E: 'Error', W: 'Aviso', I: 'Información' }[l.lgs_niv] || 'Registro'}</td>
                              <td>{l.lgs_msg || 'Sin mensaje'}</td>
                              <td className="reportes-detalle-col">{l.lgs_data || '—'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </>
                    )}
                    {pestana === 'sesiones' && (
                      <>
                        <thead><tr><th>Usuario</th><th>Equipo</th><th>Aplicación</th><th>Inicio</th><th>Fin</th><th>Estado</th></tr></thead>
                        <tbody>
                          {datos.map((s) => (
                            <tr key={s.ssq_cod}>
                              <td>{s.ssq_usr || 'Sin usuario'}</td>
                              <td>{s.ssq_host || 'No identificado'}</td>
                              <td>{s.ssq_prog || 'No identificada'}</td>
                              <td>{fecha(s.ssq_fec_ini)}</td>
                              <td>{fecha(s.ssq_fec_fin)}</td>
                              <td>{s.ssq_est === 'A' ? 'Activa' : 'Cerrada'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </>
                    )}
                    {!cargando && datos.length === 0 && !error && (
                      <tbody><tr><td className="reportes-vacio" colSpan={columnas}>No hay registros para estos filtros.</td></tr></tbody>
                    )}
                  </table>
                </div>
              )}
              <footer className="reportes-paginacion">
                <span>Página {pagina} de {paginas}</span>
                <div>
                  <button type="button" disabled={pagina <= 1 || cargando} onClick={() => { setCargando(true); setPagina((actual) => actual - 1) }}>Anterior</button>
                  <button type="button" disabled={pagina >= paginas || cargando} onClick={() => { setCargando(true); setPagina((actual) => actual + 1) }}>Siguiente</button>
                </div>
              </footer>
            </section>
          </section>
        </main>
      </div>
    </div>
  )
}

export default Reportes

