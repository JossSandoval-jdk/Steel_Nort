import { useState } from 'react'
import Sidebar from '../../components/Sidebar.jsx'
import Topbar from '../../components/Topbar.jsx'
import { useAuth } from '../../context/AuthContext.jsx'
import '../../css/Layout.css'
import './Reportes_v2.css'

// ==================== PESTAÑAS ====================
const PESTANAS = [
  { id: 'rendimiento',   titulo: 'Informe de Rendimiento (Último Mes)' },
  { id: 'anomalias',     titulo: 'Informe de Anomalías Detallado' },
  { id: 'alertas',       titulo: 'Historial de Alertas Generales' },
  { id: 'exportaciones', titulo: 'Exportaciones' },
]

// ==================== DATOS MOCK ====================
const INFORMES_RECIENTES_MOCK = [
  { id: 1, fecha: '2026-05-07T16:03:20', titulo: 'Resumen Mensual de Métricas SQL - Mayo 2026', tipo: 'Métricas de Rendimiento', estado: 'generando' },
  { id: 2, fecha: '2026-05-07T13:32:01', titulo: 'Resumen Mensual de Métricas SQL', tipo: 'Diagnósticos de Anomalías', estado: 'completado' },
  { id: 3, fecha: '2026-05-07T14:15:02', titulo: 'Resumen Mensual de Métricas SQL', tipo: 'Métricas de Anomalías', estado: 'fallido' },
]

const RESUMEN_MOCK = [
  { procedimiento: 'Índice de Bloqueo', tiempo: '10.82 ms', ejecuciones: 47, espera: '0.09 min', anomalias: 3 },
  { procedimiento: 'Total de Bloqueos', tiempo: '5.28 ms', ejecuciones: 12, espera: '0.12 min', anomalias: 0 },
  { procedimiento: 'Consultas Lentas', tiempo: '4.34 ms', ejecuciones: 12, espera: '0.12 min', anomalias: 0 },
  { procedimiento: 'Procediment Tempor SQL', tiempo: '4.34 ms', ejecuciones: 12, espera: '0.12 min', anomalias: 0 },
  { procedimiento: 'Desgaste Componente Hardware', tiempo: '0.51 sec', ejecuciones: 6, espera: '0.12 min', anomalias: 0 },
  { procedimiento: 'SQL Procediation', tiempo: '0.00 sec', ejecuciones: 2, espera: '0.00 min', anomalias: 0 },
]

// ==================== HELPERS ====================
function fechaBonita(valor) {
  if (!valor) return '—'
  const d = new Date(valor)
  if (Number.isNaN(d.getTime())) return '—'
  const dia = String(d.getDate()).padStart(2, '0')
  const mes = String(d.getMonth() + 1).padStart(2, '0')
  const anio = d.getFullYear()
  const hora = String(d.getHours()).padStart(2, '0')
  const min = String(d.getMinutes()).padStart(2, '0')
  const seg = String(d.getSeconds()).padStart(2, '0')
  return `${dia}/${mes}/${anio} ${hora}:${min}:${seg}`
}

const BADGES_ESTADO = {
  generando:  { texto: 'Generando',  clase: 'badge-generando'  },
  completado: { texto: 'Completado', clase: 'badge-completado' },
  fallido:    { texto: 'Fallido',    clase: 'badge-fallido'    },
}

// ==================== COMPONENTE ====================
function Reportes_v2() {
  const { user } = useAuth()
  const nombre = user?.usu_nom || 'Nombre Usuario'
  const cargo = user?.usu_rol || 'Cargo'

  // --- Pestaña activa ---
  const [pestana, setPestana] = useState('rendimiento')

  // --- Filtros ---
  const [rangoInicio, setRangoInicio] = useState('')
  const [rangoFin, setRangoFin] = useState('')
  const [tipoReporte, setTipoReporte] = useState('')
  const [diagnostico, setDiagnostico] = useState('')
  const [bdTabla, setBdTabla] = useState('')
  const [procTabla, setProcTabla] = useState('')
  const [bdFiltro, setBdFiltro] = useState('')
  const [procFiltro, setProcFiltro] = useState('')

  // --- Datos (mock) ---
  const [informes] = useState(INFORMES_RECIENTES_MOCK)
  const [resumen] = useState(RESUMEN_MOCK)

  const generarInforme = () => {
    alert('Generar informe - próximamente conectado a FastAPI')
  }

  const descargar = (id, formato) => {
    alert(`Descargar informe #${id} en ${formato}`)
  }

  return (
    <div className="layout">
      <Sidebar />
      <div className="layout-main">
        <Topbar nombre={nombre} cargo={cargo} />
        <main className="layout-content">
          <section className="informes">

            {/* ===== PESTAÑAS (arriba) ===== */}
            <div className="informes-tabs" role="tablist">
              {PESTANAS.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  role="tab"
                  aria-selected={pestana === p.id}
                  className={pestana === p.id ? 'informes-tab activa' : 'informes-tab'}
                  onClick={() => setPestana(p.id)}
                >
                  {p.titulo}
                </button>
              ))}
            </div>

            {/* ================================================== */}
            {/* PESTAÑA 1 — RENDIMIENTO (tu contenido actual)      */}
            {/* ================================================== */}
            {pestana === 'rendimiento' && (
              <>
                <header className="informes-cabecera">
                  <h1>Generador de Informes Personalizado</h1>
                </header>

                <div className="informes-filtros-grid">
                  <div className="informes-campo">
                    <label className="informes-etiqueta">Rango de fechas</label>
                    <div className="informes-fila">
                      <input type="date" value={rangoInicio} onChange={(e) => setRangoInicio(e.target.value)} placeholder="Fecha de Inicio" />
                      <input type="date" value={rangoFin} onChange={(e) => setRangoFin(e.target.value)} placeholder="Fecha de Fin" />
                    </div>
                  </div>

                  <div className="informes-campo">
                    <label className="informes-etiqueta">Tipo de Reporte</label>
                    <div className="informes-fila">
                      <select value={tipoReporte} onChange={(e) => setTipoReporte(e.target.value)}>
                        <option value="">Métricas de Rendimiento</option>
                        <option value="metricas">Métricas de Rendimiento</option>
                        <option value="anomalias">Diagnósticos de Anomalías</option>
                      </select>
                      <select value={diagnostico} onChange={(e) => setDiagnostico(e.target.value)}>
                        <option value="">Diagnósticos de Anomalías</option>
                        <option value="basico">Básico</option>
                        <option value="detallado">Detallado</option>
                      </select>
                    </div>
                  </div>

                  <div className="informes-campo">
                    <label className="informes-etiqueta">Tabla de base de datos</label>
                    <div className="informes-fila">
                      <select value={bdTabla} onChange={(e) => setBdTabla(e.target.value)}>
                        <option value="">Base de Datos</option>
                        <option value="bdSteelNort_v2">bdSteelNort_v2</option>
                        <option value="master">master</option>
                      </select>
                      <select value={procTabla} onChange={(e) => setProcTabla(e.target.value)}>
                        <option value="">Procedimiento</option>
                        <option value="sp_metricas">sp_metricas</option>
                        <option value="sp_bloqueos">sp_bloqueos</option>
                      </select>
                    </div>
                  </div>

                  <div className="informes-campo">
                    <label className="informes-etiqueta">Tabla de Procedimiento</label>
                    <div className="informes-fila">
                      <select value={bdFiltro} onChange={(e) => setBdFiltro(e.target.value)}>
                        <option value="">Filtros</option>
                        <option value="bdSteelNort_v2">bdSteelNort_v2</option>
                      </select>
                      <select value={procFiltro} onChange={(e) => setProcFiltro(e.target.value)}>
                        <option value="">Procedimiento</option>
                        <option value="todos">Todos</option>
                      </select>
                    </div>
                  </div>
                </div>

                <div className="informes-acciones">
                  <button type="button" className="informes-btn-generar" onClick={generarInforme}>
                    Generar Informe
                  </button>
                </div>

                <section className="informes-seccion">
                  <h2>Informes Generados Recientemente</h2>
                  <div className="informes-tabla-scroll">
                    <table className="informes-tabla">
                      <thead>
                        <tr>
                          <th>Marca de Tiempo ↓</th>
                          <th>Título del Reporte</th>
                          <th>Tipo</th>
                          <th>Estado</th>
                          <th>Descargar</th>
                        </tr>
                      </thead>
                      <tbody>
                        {informes.map((inf) => {
                          const badge = BADGES_ESTADO[inf.estado] || BADGES_ESTADO.fallido
                          return (
                            <tr key={inf.id}>
                              <td>{fechaBonita(inf.fecha)}</td>
                              <td>{inf.titulo}</td>
                              <td>{inf.tipo}</td>
                              <td>
                                <span className={`informes-badge ${badge.clase}`}>
                                  {badge.texto}
                                </span>
                              </td>
                              <td>
                                <div className="informes-acciones-col">
                                  <button type="button" className="informes-btn-descargar pdf" onClick={() => descargar(inf.id, 'PDF')}>PDF</button>
                                  <button type="button" className="informes-btn-descargar excel" onClick={() => descargar(inf.id, 'Excel')}>Excel</button>
                                </div>
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                </section>

                <section className="informes-seccion">
                  <h2>Resumen Mensual de Métricas SQL - Mayo 2026</h2>
                  <div className="informes-tabla-scroll">
                    <table className="informes-tabla">
                      <thead>
                        <tr>
                          <th>Nombre del Procedimiento</th>
                          <th>Tiempo de Ejecución Promedio</th>
                          <th>Ejecuciones</th>
                          <th>Tiempo de Espera por Bloqueo</th>
                          <th>Anomalías Detectadas</th>
                          <th>Acciones</th>
                        </tr>
                      </thead>
                      <tbody>
                        {resumen.map((fila, i) => (
                          <tr key={i}>
                            <td>{fila.procedimiento}</td>
                            <td>{fila.tiempo}</td>
                            <td>{fila.ejecuciones}</td>
                            <td>{fila.espera}</td>
                            <td>{fila.anomalias}</td>
                            <td>
                              <div className="informes-acciones-col">
                                <button type="button" className="informes-btn-icono" title="Ver detalle">👁</button>
                                <button type="button" className="informes-btn-icono" title="Editar">✎</button>
                                <button type="button" className="informes-btn-icono" title="Descargar">⬇</button>
                              </div>
                            </td>
                          </tr>
                        ))}
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
                    Análisis de las variables fuera de rango detectadas por el modelo ML.
                  </p>
                </header>

                <div className="informes-filtros-grid">
                  <div className="informes-campo">
                    <label className="informes-etiqueta">Rango de fechas</label>
                    <div className="informes-fila">
                      <input type="date" />
                      <input type="date" />
                    </div>
                  </div>

                  <div className="informes-campo">
                    <label className="informes-etiqueta">Filtros de anomalía</label>
                    <div className="informes-fila">
                      <select>
                        <option value="">Todas las severidades</option>
                        <option value="C">Crítica</option>
                        <option value="A">Alta</option>
                        <option value="M">Media</option>
                        <option value="B">Baja</option>
                      </select>
                      <select>
                        <option value="">Todas las instancias</option>
                        <option value="SRV-SQL-01">SRV-SQL-01</option>
                        <option value="SRV-SQL-02">SRV-SQL-02</option>
                        <option value="SRV-SQL-03">SRV-SQL-03</option>
                      </select>
                    </div>
                  </div>
                </div>

                <div className="informes-acciones">
                  <button type="button" className="informes-btn-secundario">Exportar a Excel</button>
                  <button type="button" className="informes-btn-generar">Generar PDF</button>
                </div>

                <section className="informes-seccion">
                  <h2>Anomalías Detectadas (6 registros)</h2>
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
                          <th>Acciones</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr>
                          <td>07/05/2026 16:03:20</td>
                          <td>CPU %</td>
                          <td>98.4</td>
                          <td>3.21</td>
                          <td><span className="informes-sev sev-C">Crítica</span></td>
                          <td>SRV-SQL-01</td>
                          <td><button type="button" className="informes-btn-icono" title="Ver detalle">👁</button></td>
                        </tr>
                        <tr>
                          <td>07/05/2026 15:42:11</td>
                          <td>Memoria disponible</td>
                          <td>1.2</td>
                          <td>2.87</td>
                          <td><span className="informes-sev sev-A">Alta</span></td>
                          <td>SRV-SQL-01</td>
                          <td><button type="button" className="informes-btn-icono" title="Ver detalle">👁</button></td>
                        </tr>
                        <tr>
                          <td>07/05/2026 14:15:02</td>
                          <td>Tiempo de espera</td>
                          <td>842</td>
                          <td>2.44</td>
                          <td><span className="informes-sev sev-M">Media</span></td>
                          <td>SRV-SQL-02</td>
                          <td><button type="button" className="informes-btn-icono" title="Ver detalle">👁</button></td>
                        </tr>
                        <tr>
                          <td>07/05/2026 12:30:00</td>
                          <td>Consultas lentas</td>
                          <td>47</td>
                          <td>2.10</td>
                          <td><span className="informes-sev sev-M">Media</span></td>
                          <td>SRV-SQL-01</td>
                          <td><button type="button" className="informes-btn-icono" title="Ver detalle">👁</button></td>
                        </tr>
                        <tr>
                          <td>07/05/2026 11:18:45</td>
                          <td>Transacciones/seg</td>
                          <td>12</td>
                          <td>1.98</td>
                          <td><span className="informes-sev sev-B">Baja</span></td>
                          <td>SRV-SQL-03</td>
                          <td><button type="button" className="informes-btn-icono" title="Ver detalle">👁</button></td>
                        </tr>
                        <tr>
                          <td>07/05/2026 09:05:12</td>
                          <td>Bloqueos activos</td>
                          <td>8</td>
                          <td>1.85</td>
                          <td><span className="informes-sev sev-B">Baja</span></td>
                          <td>SRV-SQL-02</td>
                          <td><button type="button" className="informes-btn-icono" title="Ver detalle">👁</button></td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
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
                    Registro completo de alertas generadas por el sistema, con su estado y responsable.
                  </p>
                </header>

                <div className="informes-filtros-grid">
                  <div className="informes-campo">
                    <label className="informes-etiqueta">Rango de fechas</label>
                    <div className="informes-fila">
                      <input type="date" />
                      <input type="date" />
                    </div>
                  </div>

                  <div className="informes-campo">
                    <label className="informes-etiqueta">Filtros de alertas</label>
                    <div className="informes-fila">
                      <select>
                        <option value="">Todas las prioridades</option>
                        <option value="C">Crítica</option>
                        <option value="A">Alta</option>
                        <option value="M">Media</option>
                        <option value="B">Baja</option>
                      </select>
                      <select>
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
                  <button type="button" className="informes-btn-secundario">Exportar a Excel</button>
                  <button type="button" className="informes-btn-generar">Generar PDF</button>
                </div>

                <section className="informes-seccion">
                  <h2>Alertas Registradas (5 registros)</h2>
                  <div className="informes-tabla-scroll">
                    <table className="informes-tabla">
                      <thead>
                        <tr>
                          <th>Fecha</th>
                          <th>Título</th>
                          <th>Prioridad</th>
                          <th>Estado</th>
                          <th>Detalle</th>
                          <th>Responsable</th>
                          <th>Acciones</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr>
                          <td>07/05/2026 16:03:20</td>
                          <td>Cambio inusual en el servidor</td>
                          <td><span className="informes-sev sev-C">Crítica</span></td>
                          <td><span className="informes-est est-A">Abierta</span></td>
                          <td className="informes-detalle-col">La CPU superó el 95% durante más de 5 minutos</td>
                          <td>sistema</td>
                          <td><button type="button" className="informes-btn-icono" title="Ver detalle">👁</button></td>
                        </tr>
                        <tr>
                          <td>07/05/2026 15:22:10</td>
                          <td>Memoria disponible crítica</td>
                          <td><span className="informes-sev sev-A">Alta</span></td>
                          <td><span className="informes-est est-R">En revisión</span></td>
                          <td className="informes-detalle-col">Quedan menos de 2 GB de memoria libre</td>
                          <td>jperez</td>
                          <td><button type="button" className="informes-btn-icono" title="Ver detalle">👁</button></td>
                        </tr>
                        <tr>
                          <td>07/05/2026 13:48:55</td>
                          <td>Bloqueo detectado</td>
                          <td><span className="informes-sev sev-M">Media</span></td>
                          <td><span className="informes-est est-S">Resuelta</span></td>
                          <td className="informes-detalle-col">Se detectó un bloqueo de 8 segundos en la tabla métricas</td>
                          <td>jperez</td>
                          <td><button type="button" className="informes-btn-icono" title="Ver detalle">👁</button></td>
                        </tr>
                        <tr>
                          <td>07/05/2026 11:30:00</td>
                          <td>Consultas lentas incrementadas</td>
                          <td><span className="informes-sev sev-M">Media</span></td>
                          <td><span className="informes-est est-S">Resuelta</span></td>
                          <td className="informes-detalle-col">Incremento del 40% en consultas lentas</td>
                          <td>sistema</td>
                          <td><button type="button" className="informes-btn-icono" title="Ver detalle">👁</button></td>
                        </tr>
                        <tr>
                          <td>07/05/2026 09:15:33</td>
                          <td>Desgaste de hardware</td>
                          <td><span className="informes-sev sev-B">Baja</span></td>
                          <td><span className="informes-est est-F">Descartada</span></td>
                          <td className="informes-detalle-col">Posible desgaste en disco SSD</td>
                          <td>mgomez</td>
                          <td><button type="button" className="informes-btn-icono" title="Ver detalle">👁</button></td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
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
                    Historial de archivos generados (PDF/Excel) y disponibles para descarga.
                  </p>
                </header>

                <div className="informes-filtros-grid">
                  <div className="informes-campo">
                    <label className="informes-etiqueta">Rango de fechas</label>
                    <div className="informes-fila">
                      <input type="date" />
                      <input type="date" />
                    </div>
                  </div>

                  <div className="informes-campo">
                    <label className="informes-etiqueta">Filtros de exportaciones</label>
                    <div className="informes-fila">
                      <select>
                        <option value="">Todos los formatos</option>
                        <option value="PDF">PDF</option>
                        <option value="Excel">Excel</option>
                      </select>
                      <select>
                        <option value="">Todos los estados</option>
                        <option value="completado">Completado</option>
                        <option value="fallido">Fallido</option>
                      </select>
                    </div>
                  </div>
                </div>

                <div className="informes-acciones">
                  <button type="button" className="informes-btn-generar">Nueva Exportación</button>
                </div>

                <section className="informes-seccion">
                  <h2>Archivos Exportados (4 registros)</h2>
                  <div className="informes-tabla-scroll">
                    <table className="informes-tabla">
                      <thead>
                        <tr>
                          <th>Fecha</th>
                          <th>Nombre del Archivo</th>
                          <th>Formato</th>
                          <th>Tamaño</th>
                          <th>Estado</th>
                          <th>Acciones</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr>
                          <td>01/05/2026 08:00:00</td>
                          <td>Métricas Mensuales - Abril 2026</td>
                          <td><span className="informes-formato formato-excel">Excel</span></td>
                          <td>2.4 MB</td>
                          <td><span className="informes-badge badge-completado">Completado</span></td>
                          <td>
                            <div className="informes-acciones-col">
                              <button type="button" className="informes-btn-icono" title="Descargar">⬇</button>
                              <button type="button" className="informes-btn-icono" title="Eliminar">🗑</button>
                            </div>
                          </td>
                        </tr>
                        <tr>
                          <td>15/04/2026 10:30:00</td>
                          <td>Alertas Q1 2026</td>
                          <td><span className="informes-formato formato-pdf">PDF</span></td>
                          <td>1.8 MB</td>
                          <td><span className="informes-badge badge-completado">Completado</span></td>
                          <td>
                            <div className="informes-acciones-col">
                              <button type="button" className="informes-btn-icono" title="Descargar">⬇</button>
                              <button type="button" className="informes-btn-icono" title="Eliminar">🗑</button>
                            </div>
                          </td>
                        </tr>
                        <tr>
                          <td>02/04/2026 16:45:00</td>
                          <td>Anomalías Marzo 2026</td>
                          <td><span className="informes-formato formato-excel">Excel</span></td>
                          <td>892 KB</td>
                          <td><span className="informes-badge badge-completado">Completado</span></td>
                          <td>
                            <div className="informes-acciones-col">
                              <button type="button" className="informes-btn-icono" title="Descargar">⬇</button>
                              <button type="button" className="informes-btn-icono" title="Eliminar">🗑</button>
                            </div>
                          </td>
                        </tr>
                        <tr>
                          <td>01/03/2026 09:00:00</td>
                          <td>Reporte Completo Febrero 2026</td>
                          <td><span className="informes-formato formato-pdf">PDF</span></td>
                          <td>—</td>
                          <td><span className="informes-badge badge-fallido">Fallido</span></td>
                          <td>
                            <div className="informes-acciones-col">
                              <button type="button" className="informes-btn-icono" title="Eliminar">🗑</button>
                            </div>
                          </td>
                        </tr>
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