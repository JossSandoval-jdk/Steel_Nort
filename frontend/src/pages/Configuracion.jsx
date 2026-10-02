// Pantalla de Configuracion.
//
// Solo entra quien tiene el permiso "sistema:leer" (el backend lo exige otra
// vez en cada llamada, esto solo evita ofrecer la pantalla).
//
// Esta es la parte que la API v2 ya soporta:
//   GET    /acceso/usuarios        -> alta, edicion y baja de usuarios
//   POST   /acceso/usuarios
//   PATCH  /acceso/usuarios/{cod}
//   DELETE /acceso/usuarios/{cod}
//   GET    /acceso/roles           -> para traducir rol_cod a su nombre
//   Roles y permisos              -> ventana "RolesPermisosModal"
//
// Las secciones de Conexiones, Modelo de aprendizaje e Importar carga quedan
// pendientes: la v2 todavia no tiene esos endpoints.
import { useCallback, useEffect, useState } from 'react'
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

function IconEdit() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
      <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
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

// Una fila de "etiqueta: valor" de las listas de informacion.
function InfoRow({ label, value }) {
  return (
    <li className="info-item">
      <span className="info-label">{label}</span>
      <span className="info-value">{value}</span>
    </li>
  )
}

// Pastilla con el punto verde/rojo de una conexion.
function PillConexion({ conectado, textoOk, textoOff, textoNull }) {
  if (conectado === null || conectado === undefined) {
    return (
      <span className="conn-pill off">
        <span className="status-led offline" />
        {textoNull || 'Sin verificar'}
      </span>
    )
  }
  return (
    <span className={`conn-pill ${conectado ? '' : 'off'}`}>
      <span className={`status-led ${conectado ? 'online' : 'offline'}`} />
      {conectado ? textoOk : textoOff}
    </span>
  )
}

function Configuracion() {
  const { user, accessToken, rol, tiene } = useAuth()
  const [usuarios, setUsuarios] = useState([])
  // rol_cod -> nombre del rol, para pintar la columna "Rol".
  const [nombreDeRol, setNombreDeRol] = useState({})
  const [cargando, setCargando] = useState(true)
  const [modalUsuario, setModalUsuario] = useState(false)
  const [usuarioEditando, setUsuarioEditando] = useState(null)
  const [modalRoles, setModalRoles] = useState(false)
  const [error, setError] = useState(null)
  // Cada vez que sube, el efecto de abajo vuelve a pedir los datos. Asi las
  // altas, las ediciones y las bajas se ven sin repetir la llamada a mano.
  const [version, setVersion] = useState(0)

  // ---- Estado de los bloques de Conexiones y Modelo ----
  // Las conexiones se piden a GET /sistema/conexiones, que comprueba de verdad
  // la base de la v2 y el SQL Server del sistema que monitoreamos.
  const [conexiones, setConexiones] = useState(null)
  const [verificando, setVerificando] = useState(false)
  const [modelo, setModelo] = useState(null)
  const [mostrarVariables, setMostrarVariables] = useState(false)
  const [reentrenando, setReentrenando] = useState(false)
  const [retrainResult, setRetrainResult] = useState(null)

  const recargar = useCallback(() => setVersion((actual) => actual + 1), [])

// Comprueba las conexiones contra el backend.
  const cargarConexiones = useCallback(async () => {
    if (!accessToken) return
    setVerificando(true)
    try {
      // CORREGIDO: Apunta al endpoint correcto que creamos (/estado/conexiones)
      setConexiones(await api.get('/estado/conexiones', { token: accessToken }))
    } catch {
      setConexiones(null)
    } finally {
      setVerificando(false)
    }
  }, [accessToken])

  useEffect(() => {
    if (!accessToken) return undefined
    const primero = setTimeout(cargarConexiones, 0)
    const repetido = setInterval(cargarConexiones, 30000)
    return () => {
      clearTimeout(primero)
      clearInterval(repetido)
    }
  }, [accessToken, cargarConexiones])

  useEffect(() => {
    if (!accessToken) return undefined
    const primero = setTimeout(cargarConexiones, 0)
    const repetido = setInterval(cargarConexiones, 30000)
    return () => {
      clearTimeout(primero)
      clearInterval(repetido)
    }
  }, [accessToken, cargarConexiones])

  // Los permisos vienen del login (AuthContext), no hace falta volver a pedirlos.
  const puedeCrear = tiene('acceso:crear')
  const puedeEditar = tiene('acceso:editar')
  const puedeEliminar = tiene('acceso:eliminar')
  const puedeVerRoles = tiene('acceso:leer')

  // Estado del modelo de aprendizaje.
  // La v2 no tiene un endpoint único "estado del modelo" (la v1 usaba
  // /reentrenamiento/estado). Se arma la misma forma que consume la pantalla
  // combining dos fuentes reales:
  //   /modelo/modelos?estado=A    -> el modelo activo en produccion
  //   /modelo/reentrenamientos    -> el ultimo pedido, con sus metricas
  const cargarModelo = useCallback(async () => {
    if (!accessToken) return
    try {
      const [activos, reentrenamientos] = await Promise.all([
        api.get('/modelo/modelos?estado=A&tamano=1', { token: accessToken }),
        api.get('/modelo/reentrenamientos?tamano=1', { token: accessToken }),
      ])
      const mdl = activos?.items?.[0] || null
      const ren = reentrenamientos?.items?.[0] || null
      setModelo({
        hay_modelo: Boolean(mdl),
        codigo: mdl?.mdl_cod ?? null,
        nombre: mdl?.mdl_nom || '',
        tipo: mdl?.mdl_tipo || '',
        umbral: mdl?.mdl_umbral ?? null,
        fecha_entrenamiento: mdl?.mdl_fec_entr || null,
        // mdl_vars es una lista separada por comas en la base.
        features: mdl?.mdl_vars ? mdl.mdl_vars.split(',').map((v) => v.trim()).filter(Boolean) : [],
        muestras_entrenamiento: ren?.ren_n_train ?? null,
        // FPR medida: la del reentrenamiento mas reciente, antes o despues.
        fpr_actual: ren?.ren_fpr_desp ?? ren?.ren_fpr_antes ?? null,
        reentrenamiento_est: ren?.ren_est || null,
      })
    } catch {
      setModelo(null)
    }
  }, [accessToken])

  useEffect(() => {
    if (!accessToken) return undefined
    const primero = setTimeout(cargarModelo, 0)
    const repetido = setInterval(cargarModelo, 30000)
    return () => {
      clearTimeout(primero)
      clearInterval(repetido)
    }
  }, [accessToken, cargarModelo])

  // Pide un reentrenamiento del modelo.
  // OJO con el cambio de semantica: en la v2 esto NO entrena aqui, registra
  // un pedido (ren_est = 'P') que el pipeline toma despues. Por eso el boton
  // dice "Solicitar" y el mensaje confirma que quedo pendiente.
  // ren_mdl_origen es NOT NULL (FK al modelo) y ren_disparo solo admite
  // D/F/P/M, asi que sin modelo activo la accion no tiene sentido.
  async function handleReentrenar() {
    if (!modelo?.codigo) return
    setReentrenando(true)
    setRetrainResult(null)
    try {
      const pedido = await api.post(
        '/modelo/reentrenamientos',
        {
          ren_mdl_origen: modelo.codigo,
          ren_disparo: 'M',
          ren_motivo: 'Solicitado desde Configuracion',
        },
        { token: accessToken }
      )
      setRetrainResult({ exito: true, mensaje: `Reentrenamiento ${pedido.ren_cod} solicitado.` })
      await cargarModelo()
    } catch (err) {
      setRetrainResult({ exito: false, mensaje: err.message })
    } finally {
      setReentrenando(false)
    }
  }

  // Carga usuarios y el nombre de su rol.
  useEffect(() => {
    let cancelado = false

    async function cargar() {
      try {
        const [usuariosData, rolesData] = await Promise.all([
          api.get('/acceso/usuarios', { token: accessToken }),
          api.get('/acceso/roles', { token: accessToken }),
        ])
        if (cancelado) return
        setUsuarios(usuariosData.items)
        const nombres = {}
        for (const item of rolesData.items) {
          nombres[item.rol_cod] = item.rol_nom
        }
        setNombreDeRol(nombres)
        setError(null)
      } catch (err) {
        if (!cancelado) setError(err.message || 'No se pudieron cargar los usuarios.')
      } finally {
        if (!cancelado) setCargando(false)
      }
    }

    cargar()
    return () => {
      cancelado = true
    }
  }, [accessToken, version])

  // Crea o edita segun haya un usuario abierto en el modal.
  async function guardarUsuario(cuerpo) {
    try {
      if (usuarioEditando) {
        await api.patch(`/acceso/usuarios/${usuarioEditando.usu_cod}`, cuerpo, { token: accessToken })
      } else {
        await api.post('/acceso/usuarios', cuerpo, { token: accessToken })
      }
      setModalUsuario(false)
      setUsuarioEditando(null)
      setError(null)
      recargar()
    } catch (err) {
      setError(err.message || 'No se pudo guardar el usuario.')
    }
  }

  async function darDeBajaUsuario(usuario) {
    const aviso = `¿Dar de baja a '${usuario.usu_nom}'? Podra volver a activarse editandolo.`
    if (!window.confirm(aviso)) return
    try {
      await api.del(`/acceso/usuarios/${usuario.usu_cod}`, { token: accessToken })
      recargar()
    } catch (err) {
      setError(err.message || 'No se pudo dar de baja el usuario.')
    }
  }

// CORREGIDO: Coincide exactamente con la llave "monitored" que devuelve el backend
  const monitored = conexiones?.monitored
  const logs = conexiones?.logs
  const fpr = modelo?.fpr_actual
  const fprPct = fpr !== null && fpr !== undefined ? fpr * 100 : null

  return (
    <div className="layout">
      <Sidebar />
      <div className="layout-main">
        <Topbar nombre={user?.usu_nom || 'Usuario'} cargo={rol} />

        <main className="layout-content">
          <div className="config">
            {/* ============ USUARIOS ============ */}
            <section className="config-col">
              <article className="card">
                <div className="card-head">
                  <h3 className="card-title">Gestión de usuarios y roles</h3>
                  <span className="card-subtitle">
                    {cargando ? 'Cargando…' : `${usuarios.length} usuarios registrados`}
                  </span>
                </div>

                <table className="users-table">
                  <thead>
                    <tr>
                      <th>Nombre</th>
                      <th>Rol</th>
                      <th>Estado</th>
                      <th style={{ textAlign: 'right' }}>Acciones</th>
                    </tr>
                  </thead>
                  <tbody>
                    {usuarios.map((item) => (
                      <tr key={item.usu_cod}>
                        <td>
                          <div className="user-cell">
                            <span className="user-avatar">{item.usu_nom?.[0] || '?'}</span>
                            <span className="user-name">
                              {item.usu_nom}
                              <span className="user-mail">{item.usu_ema || item.usu_log}</span>
                            </span>
                          </div>
                        </td>
                        <td>
                          <span className="rol-pill">
                            {nombreDeRol[item.rol_cod] || 'Sin rol'}
                          </span>
                        </td>
                        <td>
                          <span className={`conn-pill ${item.usu_est === 'A' ? '' : 'off'}`}>
                            <span className={`status-led ${item.usu_est === 'A' ? 'online' : 'offline'}`} />
                            {item.usu_est === 'A' ? 'Activo' : 'Inactivo'}
                          </span>
                        </td>
                        <td>
                          <div className="row-actions">
                            {puedeEditar && (
                              <button
                                type="button"
                                className="icon-btn"
                                title="Editar usuario"
                                onClick={() => {
                                  setUsuarioEditando(item)
                                  setError(null)
                                  setModalUsuario(true)
                                }}
                              >
                                <IconEdit />
                              </button>
                            )}
                            {puedeEliminar && (
                              <button
                                type="button"
                                className="icon-btn danger"
                                title="Dar de baja el usuario"
                                onClick={() => darDeBajaUsuario(item)}
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

                {error && <p className="import-error">{error}</p>}

                <div className="card-actions">
                  {puedeCrear && (
                    <button
                      type="button"
                      className="btn btn-primary"
                      onClick={() => {
                        setUsuarioEditando(null)
                        setError(null)
                        setModalUsuario(true)
                      }}
                    >
                      <IconPlus />
                      Crear usuario
                    </button>
                  )}
                  {puedeVerRoles && (
                    <button
                      type="button"
                      className="btn btn-outline"
                      onClick={() => setModalRoles(true)}
                    >
                      <IconShield />
                      Gestionar roles y permisos
                    </button>
                  )}
                </div>
              </article>
            </section>

            {/* ============ MODELO DE APRENDIZAJE ============ */}
            {/* Pide su estado a la v1 (/reentrenamiento/estado); la v2 todavia
                no expone ese endpoint, asi que se queda en "Sin modelo". */}
            <section className="config-col">
              <article className="card">
                <div className="card-head">
                  <div className="head-text">
                    <h3 className="card-title">SQL Server (Sistema monitoreado)</h3>
                    <span className="card-subtitle">Conexión al servidor SQL que se vigila</span>
                  </div>
                  <PillConexion
                    conectado={monitored?.conectado}
                    textoOk="Conectado"
                    textoOff="Desconectado"
                    textoNull="Sin conexión"
                  />
                </div>

                <div className="card-foot">
                  <button type="button" className="btn btn-outline" onClick={cargarConexiones} disabled={verificando}>
                    <IconRefresh />
                    {verificando ? 'Verificando…' : 'Verificar ahora'}
                  </button>
                </div>
              </article>

              {/* ============ LOGS ============ */}
              <article className="card">
                <div className="card-head">
                  <div className="head-text">
                    <h3 className="card-title">Logs</h3>
                    <span className="card-subtitle">Conexión a los logs del sistema monitoreado</span>
                  </div>
                  <PillConexion
                    conectado={logs?.conectado}
                    textoOk="Conectado"
                    textoOff="Desconectado"
                    textoNull="Sin conexión"
                  />
                </div>

                <div className="card-foot">
                  <button type="button" className="btn btn-outline" onClick={cargarConexiones} disabled={verificando}>
                    <IconRefresh />
                    {verificando ? 'Verificando…' : 'Verificar ahora'}
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
                  {modelo?.hay_modelo && modelo.muestras_entrenamiento != null && (
                    <InfoRow label="Muestras de entrenamiento" value={modelo.muestras_entrenamiento} />
                  )}
                  {modelo?.hay_modelo && modelo.fecha_entrenamiento && (
                    <InfoRow
                      label="Fecha de entrenamiento"
                      value={String(modelo.fecha_entrenamiento).slice(0, 19)}
                    />
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
                        {(modelo?.hay_modelo ? modelo.features : []).map((variable) => (
                          <li key={variable} className="import-node">
                            <span className="import-node-name">{variable}</span>
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
                    {retrainResult.mensaje ||
                      (retrainResult.exito ? 'Reentrenamiento completado.' : 'El reentrenamiento falló.')}
                  </p>
                )}

                <div className="card-foot">
                  <button
                    type="button"
                    className="btn btn-primary"
                    disabled={reentrenando || !modelo?.codigo}
                    onClick={handleReentrenar}
                    title={
                      modelo?.codigo
                        ? 'Registrar un pedido de reentrenamiento'
                        : 'No hay modelo activo del que partir'
                    }
                  >
                    <IconRefresh />
                    {reentrenando ? 'Solicitando…' : 'Solicitar reentrenamiento'}
                  </button>
                </div>
              </article>
            </section>
          </div>
        </main>
      </div>

      <ModalUsuario
        isOpen={modalUsuario}
        onClose={() => {
          setModalUsuario(false)
          setUsuarioEditando(null)
        }}
        onSave={guardarUsuario}
        accessToken={accessToken}
        usuario={usuarioEditando}
        error={error}
      />

      <RolesPermisosModal isOpen={modalRoles} onClose={() => setModalRoles(false)} />
    </div>
  )
}

export default Configuracion
