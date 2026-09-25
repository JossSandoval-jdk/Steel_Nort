import { useState, useEffect, useCallback, useRef } from 'react'
import Sidebar from '../components/Sidebar.jsx'
import Topbar from '../components/Topbar.jsx'
import ModalUsuario from '../components/ModalUsuario.jsx'
import RolesPermisosModal from '../components/RolesPermisosModal.jsx'
import api from '../services/api'
import { useAuth } from '../context/AuthContext'
import '../css/Layout.css'
import '../css/Configuracion.css'

function IconTrash() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="3 6 5 6 21 6" />
      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
      <line x1="10" y1="11" x2="10" y2="17" />
      <line x1="14" y1="11" x2="14" y2="17" />
    </svg>
  )
}

function IconPlus() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="12" y1="5" x2="12" y2="19" />
      <line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  )
}

function IconShield() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    </svg>
  )
}

function IconRefresh() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="23 4 23 10 17 10" />
      <polyline points="1 20 1 14 7 14" />
      <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
    </svg>
  )
}

function IconEye() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  )
}

function InfoRow({ label, value }) {
  return (
    <li className="info-item">
      <span className="info-label">{label}</span>
      <span className="info-value">{value}</span>
    </li>
  )
}

function ImportResultado({ reporte }) {
  if (!reporte) return null
  const nodos = reporte.por_nodo || {}
  return (
    <div className="import-result">
      <div className="import-stats">
        <div className="import-stat">
          <span className="import-stat-num">{reporte.total_recibidas ?? 0}</span>
          <span className="import-stat-label">recibidas</span>
        </div>
        <div className="import-stat">
          <span className="import-stat-num">{reporte.evaluadas ?? 0}</span>
          <span className="import-stat-label">evaluadas</span>
        </div>
        <div className="import-stat good">
          <span className="import-stat-num">{reporte.normales ?? 0}</span>
          <span className="import-stat-label">normales</span>
        </div>
        <div className="import-stat bad">
          <span className="import-stat-num">{reporte.anomalias ?? 0}</span>
          <span className="import-stat-label">anomalías</span>
        </div>
      </div>
      {reporte.mensaje && <p className="import-msg">{reporte.mensaje}</p>}
      {Object.keys(nodos).length > 0 && (
        <ul className="import-nodes">
          {Object.entries(nodos).map(([nombre, info]) => (
            <li key={nombre} className="import-node">
              <span className="import-node-name">{nombre}</span>
              <span className="import-node-detail">
                {info.normales} normales · {info.anomalias} anomalías ·{' '}
                {info.descartadas_primera_ventana} descartadas (1ª ventana)
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function PillConexion({ conectado, textoOk, textoOff, textoNull }) {
  let estado = 'offline'
  let texto = textoOff
  if (conectado === null || conectado === undefined) {
    estado = 'offline'
    texto = textoNull || 'Sin verificar'
  } else if (conectado) {
    estado = 'online'
    texto = textoOk
  }
  return (
    <span className={`conn-pill ${conectado ? '' : 'off'}`}>
      <span className={`status-led ${estado}`} />
      {texto}
    </span>
  )
}

function Configuracion() {
  const [usuarios, setUsuarios] = useState([])
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [isRolesModalOpen, setIsRolesModalOpen] = useState(false)
  const [importFile, setImportFile] = useState(null)
  const [importNodo, setImportNodo] = useState('')
  const [importando, setImportando] = useState(false)
  const [importResult, setImportResult] = useState(null)
  const [importError, setImportError] = useState(null)
  const [sinc, setSinc] = useState(null)
  const [modelo, setModelo] = useState(null)
  const [mostrarVariables, setMostrarVariables] = useState(false)
  const [reentrenando, setReentrenando] = useState(false)
  const [retrainResult, setRetrainResult] = useState(null)
  const { user, accessToken } = useAuth()
  const sincTimer = useRef(null)
  const modeloTimer = useRef(null)

  const csrf = api.getCsrfToken()

  const handleImportar = async () => {
    if (!importFile) return
    setImportando(true)
    setImportError(null)
    setImportResult(null)
    try {
      const formData = new FormData()
      formData.append('archivo', importFile)
      if (importNodo) formData.append('nodo', importNodo)
      const data = await api.upload('/telemetria/import/csv', formData, { token: accessToken })
      setImportResult(data)
    } catch (err) {
      setImportError(err.message || 'Error al importar la carga.')
    } finally {
      setImportando(false)
    }
  }

  const handleSaveUsuario = async (nuevoUsuario) => {
    try {
      await api.post('/usuarios', nuevoUsuario, { token: accessToken, csrf })
      setIsModalOpen(false)
      const data = await api.get('/usuarios', { token: accessToken })
      setUsuarios(data)
    } catch (err) {
      console.error("Error al guardar usuario:", err)
    }
  }

  const handleEliminarUsuario = async (u) => {
    if (!window.confirm(`¿Eliminar al usuario '${u.usu_nom}'?`)) return
    try {
      await api.del(`/usuarios/${u.usu_cod}`, { token: accessToken, csrf })
      setUsuarios((prev) => prev.filter((x) => x.usu_cod !== u.usu_cod))
    } catch (err) {
      console.error("Error al eliminar usuario:", err)
    }
  }

  const cargarUsuarios = useCallback(async () => {
    if (!accessToken) return
    try {
      const data = await api.get('/usuarios', { token: accessToken })
      setUsuarios(data)
    } catch (err) {
      console.error("Error al cargar usuarios:", err)
    }
  }, [accessToken])

  useEffect(() => {
    if (!accessToken) return undefined
    const primerTick = setTimeout(cargarUsuarios, 0)
    return () => clearTimeout(primerTick)
  }, [accessToken, cargarUsuarios])

  // Estado de sincronización (cadena VPS SQL + logs del VPS).
  const cargarSinc = useCallback(async () => {
    if (!accessToken) return
    try {
      const data = await api.get('/telemetria/sincronizacion', { token: accessToken })
      setSinc(data.sincronizacion || null)
    } catch (err) {
      console.error("Error al cargar sincronización:", err)
    }
  }, [accessToken])

  useEffect(() => {
    if (!accessToken) return undefined
    const primerTick = setTimeout(cargarSinc, 0)
    sincTimer.current = setInterval(cargarSinc, 15000)
    return () => {
      clearTimeout(primerTick)
      if (sincTimer.current) {
        clearInterval(sincTimer.current)
        sincTimer.current = null
      }
    }
  }, [accessToken, cargarSinc])

  // Estado del modelo de aprendizaje.
  const cargarModelo = useCallback(async () => {
    if (!accessToken) return
    try {
      const data = await api.get('/reentrenamiento/estado', { token: accessToken })
      setModelo(data)
    } catch (err) {
      console.error("Error al cargar estado del modelo:", err)
    }
  }, [accessToken])

  useEffect(() => {
    if (!accessToken) return undefined
    const primerTick = setTimeout(cargarModelo, 0)
    modeloTimer.current = setInterval(cargarModelo, 30000)
    return () => {
      clearTimeout(primerTick)
      if (modeloTimer.current) {
        clearInterval(modeloTimer.current)
        modeloTimer.current = null
      }
    }
  }, [accessToken, cargarModelo])

  const handleReentrenar = async () => {
    setReentrenando(true)
    setRetrainResult(null)
    try {
      const data = await api.post('/reentrenamiento?dias=7', {}, { token: accessToken })
      setRetrainResult(data)
      await cargarModelo()
    } catch (err) {
      setRetrainResult({ exito: false, mensaje: err.message })
    } finally {
      setReentrenando(false)
    }
  }

  const sqlVps = sinc?.sql_vps || null
  const logsVps = sinc?.logs_vps || null
  const nombre = user?.usu_nom || 'Nombre Usuario'
  const cargo = user?.usu_rol || 'Cargo'
  const fpr = modelo?.fpr_actual
  const fprPct = fpr !== null && fpr !== undefined ? (fpr * 100) : null

  return (
    <div className="layout">
      <Sidebar />
      <div className="layout-main">
        <Topbar nombre={nombre} cargo={cargo} />
        <main className="layout-content">
          <div className="config">
            <section className="config-col">
              <article className="card">
                <div className="card-head">
                  <h3 className="card-title">Gestión de usuarios y roles</h3>
                  <span className="card-subtitle">{usuarios.length} usuarios registrados</span>
                </div>

                <table className="users-table">
                  <thead>
                    <tr>
                      <th>Nombre</th>
                      <th>Rol</th>
                      <th style={{ textAlign: 'right' }}>Acciones</th>
                    </tr>
                  </thead>
                  <tbody>
                    {usuarios.map((u, index) => (
                      <tr key={u.usu_cod || index}>
                        <td>
                          <div className="user-cell">
                            <span className="user-avatar">{u.usu_ini || (u.usu_nom ? u.usu_nom[0] : '?')}</span>
                            <span className="user-name">
                              {u.usu_nom}
                              <span className="user-mail">{u.usu_ema}</span>
                            </span>
                          </div>
                        </td>
                        <td>
                          <span className={`rol-pill ${u.usu_rol ? u.usu_rol.toLowerCase() : ''}`}>{u.usu_rol}</span>
                        </td>
                        <td>
                          <div className="row-actions">
                            {u.usu_rol !== 'Administrador' && (
                              <button
                                type="button"
                                className="icon-btn danger"
                                title="Eliminar usuario"
                                onClick={() => handleEliminarUsuario(u)}
                              >
                                <IconTrash />
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>

                <div className="card-actions">
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={() => setIsModalOpen(true)}
                  >
                    <IconPlus />
                    Crear usuario
                  </button>
                  <button
                    type="button"
                    className="btn btn-outline"
                    onClick={() => setIsRolesModalOpen(true)}
                  >
                    <IconShield />
                    Gestionar roles y permisos
                  </button>
                </div>
              </article>
            </section>

            <section className="config-col">
              <article className="card">
                <div className="card-head">
                  <div className="head-text">
                    <h3 className="card-title">SQL Server (OLTP)</h3>
                    <span className="card-subtitle">Conexión al servidor SQL</span>
                  </div>
                  <PillConexion
                    conectado={sqlVps?.conectado}
                    textoOk="Conectado"
                    textoOff="Desconectado"
                    textoNull="Sin verificar"
                  />
                </div>

                <div className="subhead">
                  <h4 className="subhead-title">Logs del VPS</h4>
                  <PillConexion
                    conectado={logsVps?.conectado}
                    textoOk="En conexión"
                    textoOff="Sin conexión"
                    textoNull="Sin verificar"
                  />
                </div>

                <ul className="info-list">
                  <InfoRow
                    label="Logs reportando"
                    value={logsVps?.detalle === 'logs_ok' ? 'errorlog de SQL Server' : 'Sin logs'}
                  />
                  <InfoRow
                    label="Detalle SQL"
                    value={sqlVps?.detalle || '—'}
                  />
                  <InfoRow
                    label="Detalle logs"
                    value={logsVps?.detalle || '—'}
                  />
                </ul>

                <div className="card-foot">
                  <button type="button" className="btn btn-outline" onClick={cargarSinc}>
                    <IconRefresh />
                    Verificar ahora
                  </button>
                </div>
              </article>

              <article className="card">
                <div className="card-head">
                  <h3 className="card-title">Modelo de aprendizaje</h3>
                </div>

                <ul className="info-list">
                  <li className="info-item">
                    <div className="field-stack">
                      <span className="info-label">Modelo de entrenamiento</span>
                      <div className="input-group">
                        <input
                          className="text-input grow"
                          value={
                            modelo?.hay_modelo
                              ? `${modelo.nombre} (${modelo.tipo})`
                              : 'Sin modelo entrenado'
                          }
                          readOnly
                          aria-label="Modelo de entrenamiento"
                        />
                      </div>
                    </div>
                  </li>
                  {modelo?.hay_modelo && fprPct !== null && (
                    <InfoRow
                      label="FPR del modelo activo"
                      value={`${fprPct.toFixed(1)} %` + (fprPct > 10 ? ' (no apto)' : '')}
                    />
                  )}
                  {modelo?.hay_modelo && modelo.muestras_entrenamiento !== undefined && (
                    <InfoRow label="Muestras de entrenamiento" value={modelo.muestras_entrenamiento} />
                  )}
                  {modelo?.hay_modelo && modelo.fecha_entrenamiento && (
                    <InfoRow label="Fecha de entrenamiento" value={String(modelo.fecha_entrenamiento).slice(0, 19)} />
                  )}
                  <li className="info-item">
                    <span className="info-label">Variables de entrenamiento</span>
                    <button
                      type="button"
                      className="icon-btn"
                      title="Ver variables"
                      onClick={() => setMostrarVariables((v) => !v)}
                    >
                      <IconEye />
                    </button>
                  </li>
                  {mostrarVariables && (
                    <li className="info-item">
                      <ul className="import-nodes" style={{ width: '100%' }}>
                        {(modelo?.hay_modelo ? modelo.features : []).map((f) => (
                          <li key={f} className="import-node">
                            <span className="import-node-name">{f}</span>
                          </li>
                        ))}
                        {(!modelo?.hay_modelo || !modelo.features || modelo.features.length === 0) && (
                          <li className="import-node">
                            <span className="import-node-detail">Sin variables registradas</span>
                          </li>
                        )}
                      </ul>
                    </li>
                  )}
                </ul>

                {retrainResult && (
                  <p className={`import-msg ${retrainResult.exito ? 'good' : 'import-error'}`}>
                    {retrainResult.mensaje || (retrainResult.exito ? 'Reentrenamiento completado.' : 'El reentrenamiento falló.')}
                  </p>
                )}

                <div className="card-foot">
                  <button
                    type="button"
                    className="btn btn-primary"
                    disabled={reentrenando}
                    onClick={handleReentrenar}
                  >
                    <IconRefresh />
                    {reentrenando ? 'Reentrenando…' : 'Reentrenar modelo'}
                  </button>
                </div>
              </article>

              <article className="card">
                <div className="card-head">
                  <div className="head-text">
                    <h3 className="card-title">Importar carga de trabajo</h3>
                    <span className="card-subtitle">
                      El detector separa normal vs anomalía; las normales alimentan el reentrenamiento
                    </span>
                  </div>
                </div>

                <div className="import-form">
                  <label className="import-file pick">
                    <input
                      type="file"
                      accept=".csv,text/csv"
                      onChange={(e) => setImportFile(e.target.files[0] || null)}
                    />
                    <span className="import-file-name">
                      {importFile ? importFile.name : 'Elegir archivo CSV…'}
                    </span>
                  </label>

                  <div className="input-group">
                    <input
                      className="text-input grow"
                      placeholder="Nodo (opcional si el CSV tiene columna nodo)"
                      aria-label="Nodo destino de la carga"
                      value={importNodo}
                      onChange={(e) => setImportNodo(e.target.value)}
                    />
                    <button
                      type="button"
                      className="btn btn-primary btn-sm"
                      disabled={!importFile || importando}
                      onClick={handleImportar}
                    >
                      <IconPlus />
                      {importando ? 'Importando…' : 'Importar y separar'}
                    </button>
                  </div>

                  <p className="import-hint">
                    CSV con columnas de las variables del modelo. Columnas opcionales:{' '}
                    <code>nodo</code>, <code>fec</code> (timestamp original).
                  </p>

                  {importError && <p className="import-error">{importError}</p>}
                  <ImportResultado reporte={importResult} />
                </div>
              </article>
            </section>
          </div>
        </main>
      </div>
      <ModalUsuario
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onSave={handleSaveUsuario}
        accessToken={accessToken}
      />
      <RolesPermisosModal
        isOpen={isRolesModalOpen}
        onClose={() => setIsRolesModalOpen(false)}
      />
    </div>
  )
}

export default Configuracion