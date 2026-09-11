import { useState, useEffect } from 'react'
import Sidebar from '../components/Sidebar.jsx'
import Topbar from '../components/Topbar.jsx'
import api from '../services/api'
import { useAuth } from '../context/AuthContext'
import '../css/Layout.css'
import '../css/RolesPermisos.css'

function IconPlus() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="12" y1="5" x2="12" y2="19" />
      <line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  )
}

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

// Agrupa los permisos por módulo para mostrarlos ordenados.
function agruparPorModulo(permisos) {
  const grupos = {}
  permisos.forEach((p) => {
    if (!grupos[p.prm_mod]) grupos[p.prm_mod] = []
    grupos[p.prm_mod].push(p)
  })
  return grupos
}

function RolesPermisos() {
  const { accessToken } = useAuth()
  const [roles, setRoles] = useState([])
  const [permisos, setPermisos] = useState([])
  const [permisosPorRol, setPermisosPorRol] = useState({}) // rol_id -> Set(prm_cod)
  const [selectedRolId, setSelectedRolId] = useState(null)
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [mensaje, setMensaje] = useState(null)
  const [error, setError] = useState(null)

  const csrf = api.getCsrfToken()

  const notificar = (msg) => {
    setMensaje(msg)
    setError(null)
    setTimeout(() => setMensaje(null), 3000)
  }

  const notificarError = (msg) => {
    setError(msg)
    setMensaje(null)
    setTimeout(() => setError(null), 4000)
  }

  // ============ CARGA INICIAL DE DATOS ============
  useEffect(() => {
    if (!accessToken) return
    let mounted = true

    async function load() {
      try {
        const [rolesData, permisosData] = await Promise.all([
          api.get('/roles', { token: accessToken }),
          api.get('/roles/permisos', { token: accessToken }),
        ])
        if (!mounted) return
        setRoles(rolesData)
        setPermisos(permisosData)
        if (rolesData.length > 0) {
          setSelectedRolId(rolesData[0].rol_cod)
          // Cargar los permisos del primer rol.
          const permisosRol = await api.get(`/roles/${rolesData[0].rol_cod}/permisos`, {
            token: accessToken,
          })
          if (!mounted) return
          setPermisosPorRol({
            [rolesData[0].rol_cod]: new Set(permisosRol.map((p) => p.prm_cod)),
          })
        }
      } catch (err) {
        if (mounted) notificarError(`Error al cargar datos: ${err.message}`)
      }
    }

    load()
    return () => {
      mounted = false
    }
  }, [accessToken])

  // Recarga la lista de roles (usado tras crear/editar/eliminar).
  const recargarRoles = async () => {
    try {
      const data = await api.get('/roles', { token: accessToken })
      setRoles(data)
      return data
    } catch (err) {
      notificarError(`Error al cargar roles: ${err.message}`)
      return []
    }
  }

  // Carga y muestra los permisos de un rol (al seleccionarlo).
  const seleccionarRol = (rolId) => {
    setSelectedRolId(rolId)
    api
      .get(`/roles/${rolId}/permisos`, { token: accessToken })
      .then((data) => {
        setPermisosPorRol((prev) => ({
          ...prev,
          [rolId]: new Set(data.map((p) => p.prm_cod)),
        }))
      })
      .catch((err) => notificarError(`Error al cargar permisos del rol: ${err.message}`))
  }

  const rolSeleccionado = roles.find((r) => r.rol_cod === selectedRolId) || null

  const handleCrearRol = async (nombre, descripcion) => {
    try {
      await api.post('/roles', { rol_nom: nombre, rol_desc: descripcion }, { token: accessToken, csrf })
      setIsModalOpen(false)
      notificar(`Rol '${nombre}' creado correctamente.`)
      const data = await recargarRoles()
      if (data.length > 0) seleccionarRol(data[data.length - 1].rol_cod)
    } catch (err) {
      notificarError(`No se pudo crear el rol: ${err.message}`)
    }
  }

  const handleEditRol = async (rolId, cambios) => {
    try {
      await api.patch(`/roles/${rolId}`, cambios, { token: accessToken, csrf })
      notificar('Rol actualizado.')
      await recargarRoles()
    } catch (err) {
      notificarError(`No se pudo actualizar el rol: ${err.message}`)
    }
  }

  const handleEliminarRol = async (rol) => {
    if (!window.confirm(`¿Eliminar el rol '${rol.rol_nom}'?`)) return
    try {
      await api.del(`/roles/${rol.rol_cod}`, { token: accessToken, csrf })
      notificar(`Rol '${rol.rol_nom}' eliminado.`)
      const data = await recargarRoles()
      if (selectedRolId === rol.rol_cod) {
        setSelectedRolId(data.length > 0 ? data[0].rol_cod : null)
      }
    } catch (err) {
      notificarError(`No se pudo eliminar el rol: ${err.message}`)
    }
  }

  const handleTogglePermiso = async (rolId, prmId, checked) => {
    // Calcular la nueva lista ANTES de actualizar el estado.
    const actuales = permisosPorRol[rolId] ? [...permisosPorRol[rolId]] : []
    let ids
    if (checked) {
      ids = actuales.includes(prmId) ? actuales : [...actuales, prmId]
    } else {
      ids = actuales.filter((id) => id !== prmId)
    }

    // Actualizar la UI inmediatamente.
    setPermisosPorRol((prev) => {
      const set = new Set(prev[rolId] || [])
      if (checked) set.add(prmId)
      else set.delete(prmId)
      return { ...prev, [rolId]: set }
    })

    try {
      await api.post(
        `/roles/${rolId}/permisos`,
        { prm_ids: ids },
        { token: accessToken, csrf }
      )
    } catch (err) {
      notificarError(`No se pudo actualizar el permiso: ${err.message}`)
      // Revertir recargando los permisos del rol.
      api
        .get(`/roles/${rolId}/permisos`, { token: accessToken })
        .then((data) => {
          setPermisosPorRol((prev) => ({
            ...prev,
            [rolId]: new Set(data.map((p) => p.prm_cod)),
          }))
        })
        .catch(() => {})
    }
  }

  // Almacena el rol que se está editando por nombre (inline).
  const [rolEditandoNombre, setRolEditandoNombre] = useState(null)

  const gruposPermisos = agruparPorModulo(permisos)
  const modulos = Object.keys(gruposPermisos)

  return (
    <div className="layout">
      <Sidebar />
      <div className="layout-main">
        <Topbar nombre="Nombre Usuario" cargo="Cargo" />
        <main className="layout-content">
          {mensaje && <div className="rp-toast success">{mensaje}</div>}
          {error && <div className="rp-toast error">{error}</div>}
          <div className="roles-grid">
            {/* ============ ROLES ============ */}
            <section className="roles-col">
              <article className="card">
                <div className="card-head">
                  <h3 className="card-title">Roles</h3>
                  <span className="card-subtitle">{roles.length} roles registrados</span>
                </div>

                <table className="roles-table">
                  <thead>
                    <tr>
                      <th>Rol</th>
                      <th>Descripción</th>
                      <th style={{ textAlign: 'center' }}>Permisos</th>
                      <th style={{ textAlign: 'right' }}>Acciones</th>
                    </tr>
                  </thead>
                  <tbody>
                    {roles.map((rol) => {
                      const cantPermisos = (permisosPorRol[rol.rol_cod] || new Set()).size
                      return (
                        <tr
                          key={rol.rol_cod}
                          className={rol.rol_cod === selectedRolId ? 'selected' : ''}
                          onClick={() => seleccionarRol(rol.rol_cod)}
                        >
                          <td>
                            <span className={`rol-pill ${rol.rol_nom.toLowerCase()}`}>{rol.rol_nom}</span>
                          </td>
                          <td className="rol-desc">{rol.rol_desc || '—'}</td>
                          <td style={{ textAlign: 'center' }}>
                            <span className="perm-count">{cantPermisos}</span>
                          </td>
                          <td style={{ textAlign: 'right' }}>
                            <div className="row-actions" onClick={(e) => e.stopPropagation()}>
                              <button
                                type="button"
                                className="icon-btn"
                                title="Editar rol"
                                onClick={() => {
                                  setRolEditandoNombre(rol)
                                }}
                              >
                                <IconEdit />
                              </button>
                              <button
                                type="button"
                                className="icon-btn danger"
                                title="Eliminar rol"
                                onClick={() => handleEliminarRol(rol)}
                              >
                                <IconTrash />
                              </button>
                            </div>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>

                <div className="card-actions">
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={() => {
                      setIsModalOpen(true)
                    }}
                  >
                    <IconPlus />
                    Nuevo rol
                  </button>
                </div>
              </article>

              {/* ============ DETALLE DEL ROL ============ */}
              <article className="card">
                <div className="card-head">
                  <div className="head-text">
                    <h3 className="card-title">Detalle del rol</h3>
                    <span className="card-subtitle">
                      {rolSeleccionado ? `Permisos de '${rolSeleccionado.rol_nom}'` : 'Selecciona un rol'}
                    </span>
                  </div>
                </div>

                {rolSeleccionado && (
                  <div className="rp-detail">
                    {rolEditandoNombre?.rol_cod === rolSeleccionado.rol_cod ? (
                      <form
                        className="rp-edit-form"
                        onSubmit={(e) => {
                          e.preventDefault()
                          const fd = new FormData(e.target)
                          const cambios = {}
                          const nombre = fd.get('rol_nom').toString().trim()
                          const desc = fd.get('rol_desc').toString().trim()
                          if (nombre && nombre !== rolSeleccionado.rol_nom) cambios.rol_nom = nombre
                          if (desc !== (rolSeleccionado.rol_desc || '')) cambios.rol_desc = desc
                          setRolEditandoNombre(null)
                          if (Object.keys(cambios).length > 0) {
                            handleEditRol(rolSeleccionado.rol_cod, cambios)
                          }
                        }}
                      >
                        <div className="form-group">
                          <label className="form-label">Nombre</label>
                          <input
                            className="form-input"
                            name="rol_nom"
                            defaultValue={rolSeleccionado.rol_nom}
                            maxLength={30}
                          />
                        </div>
                        <div className="form-group">
                          <label className="form-label">Descripción</label>
                          <input
                            className="form-input"
                            name="rol_desc"
                            defaultValue={rolSeleccionado.rol_desc || ''}
                            maxLength={200}
                          />
                        </div>
                        <div className="modal-actions">
                          <button type="button" className="btn btn-outline" onClick={() => setRolEditandoNombre(null)}>
                            Cancelar
                          </button>
                          <button type="submit" className="btn btn-primary">
                            Guardar
                          </button>
                        </div>
                      </form>
                    ) : (
                      <ul className="info-list">
                        <li className="info-item">
                          <span className="info-label">Descripción</span>
                          <span className="info-value">{rolSeleccionado.rol_desc || '—'}</span>
                        </li>
                        <li className="info-item">
                          <span className="info-label">Permisos asignados</span>
                          <span className="info-value">
                            {(permisosPorRol[rolSeleccionado.rol_cod] || new Set()).size} de {permisos.length}
                          </span>
                        </li>
                        <li className="info-item">
                          <span className="info-label">Estado</span>
                          <span className="info-value">
                            <span className={`conn-pill ${rolSeleccionado.rol_act ? '' : 'off'}`}>
                              <span className={`status-led ${rolSeleccionado.rol_act ? 'online' : 'offline'}`} />
                              {rolSeleccionado.rol_act ? 'Activo' : 'Inactivo'}
                            </span>
                          </span>
                        </li>
                      </ul>
                    )}
                  </div>
                )}
              </article>
            </section>

            {/* ============ MATRIZ DE PERMISOS ============ */}
            <section className="roles-col">
              <article className="card">
                <div className="card-head">
                  <div className="head-text">
                    <h3 className="card-title">Matriz de permisos</h3>
                    <span className="card-subtitle">Haz clic en un permiso para asignarlo o quitarlo del rol seleccionado</span>
                  </div>
                  <IconShield />
                </div>

                {rolSeleccionado ? (
                  <div className="perm-matrix">
                    {modulos.map((modulo) => (
                      <div key={modulo} className="perm-group">
                        <div className="perm-group-head">
                          <h4 className="perm-modulo">{modulo}</h4>
                          <span className="card-subtitle">{gruposPermisos[modulo].length} permisos</span>
                        </div>
                        <ul className="perm-list">
                          {gruposPermisos[modulo].map((permiso) => (
                            <li key={permiso.prm_cod}>
                              <label className="perm-item">
                                <input
                                  type="checkbox"
                                  className="perm-checkbox"
                                  checked={(permisosPorRol[rolSeleccionado.rol_cod] || new Set()).has(permiso.prm_cod)}
                                  onChange={(e) =>
                                    handleTogglePermiso(
                                      rolSeleccionado.rol_cod,
                                      permiso.prm_cod,
                                      e.target.checked
                                    )
                                  }
                                />
                                <span>
                                  <span className="perm-clave">{permiso.prm_clave}</span>
                                  <span className="perm-nom">{permiso.prm_nom}</span>
                                </span>
                              </label>
                            </li>
                          ))}
                        </ul>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="empty-state">No hay roles para configurar.</p>
                )}
              </article>
            </section>
          </div>
        </main>
      </div>

      {/* ============ MODAL NUEVO ROL ============ */}
      {isModalOpen && (
        <div className="modal-overlay">
          <div className="modal">
            <div className="modal-head">
              <h3 className="modal-title">Nuevo rol</h3>
            </div>
            <form
              onSubmit={(e) => {
                e.preventDefault()
                const fd = new FormData(e.target)
                handleCrearRol(fd.get('rol_nom').trim(), fd.get('rol_desc').trim())
              }}
            >
              <div className="form-group">
                <label className="form-label">Nombre</label>
                <input name="rol_nom" className="form-input" required maxLength={30} />
              </div>
              <div className="form-group">
                <label className="form-label">Descripción</label>
                <input name="rol_desc" className="form-input" maxLength={200} />
              </div>
              <div className="modal-actions">
                <button type="button" className="btn btn-outline" onClick={() => setIsModalOpen(false)}>
                  Cancelar
                </button>
                <button type="submit" className="btn btn-primary">
                  Guardar
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}

export default RolesPermisos