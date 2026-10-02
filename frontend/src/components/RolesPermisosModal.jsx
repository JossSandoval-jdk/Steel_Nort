// Modal de Roles y Permisos (se abre desde la pantalla de Configuracion).
//
// Trabaja contra la API v2:
//   GET    /acceso/roles            -> roles           {total, pagina, tamano, items}
//   POST   /acceso/roles            -> crear rol       {rol_nom}
//   DELETE /acceso/roles/{cod}      -> dar de baja un rol
//   GET    /acceso/permisos         -> permisos        {items: [{per_cod, per_mod, per_acc}]}
//   GET    /acceso/roles-permisos   -> asignaciones    {items: [{rp_cod, rol_cod, per_cod}]}
//   POST   /acceso/roles-permisos   -> asignar         {rol_cod, per_cod}
//   DELETE /acceso/roles-permisos/{rp_cod} -> quitar
//
// En la v2 el permiso se pone o se quita de uno en uno: no hay endpoint que
// reemplace la lista entera del rol, asi que cada casilla hace un POST o un
// DELETE. La v2 tampoco tiene descripcion de rol ni edicion de rol, por eso
// aqui solo se crean y se dan de baja.
//
// Ojo: el backend vuelve a sembrar la matriz de permisos al arrancar, asi que
// lo que se asigne aqui se reescribe en el siguiente reinicio del servidor.
import { useEffect, useState } from 'react'
import api from '../services/api'
import { useAuth } from '../context/AuthContext'
import '../css/RolesPermisos.css'
import '../css/Modal.css'

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

function IconShield() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    </svg>
  )
}

function IconClose() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  )
}

// Agrupa los permisos por modulo para pintarlos en bloques.
function agruparPorModulo(permisos) {
  const grupos = {}
  for (const permiso of permisos) {
    if (!grupos[permiso.per_mod]) grupos[permiso.per_mod] = []
    grupos[permiso.per_mod].push(permiso)
  }
  return grupos
}

// Nombre legible del permiso: "sistema" + "editar" -> "sistema:editar".
function nombrePermiso(permiso) {
  return `${permiso.per_mod}:${permiso.per_acc}`
}

function RolesPermisosModal({ isOpen, onClose }) {
  const { accessToken, tiene } = useAuth()
  const [roles, setRoles] = useState([])
  const [permisos, setPermisos] = useState([])
  // rol_cod -> Set de per_cod asignados a ese rol.
  const [asignados, setAsignados] = useState({})
  // rp_cod -> per_cod, para poder quitar la asignacion concreta.
  const [idsAsignacion, setIdsAsignacion] = useState({})
  const [rolElegido, setRolElegido] = useState(null)
  const [creandoRol, setCreandoRol] = useState(false)
  const [nombreRol, setNombreRol] = useState('')
  const [mensaje, setMensaje] = useState(null)
  const [error, setError] = useState(null)

  // Solo quien puede editar la parte de acceso toca estos botones.
  const puedeEditar = tiene('acceso:editar')
  const puedeCrear = tiene('acceso:crear')
  const puedeEliminar = tiene('acceso:eliminar')

  function avisar(texto) {
    setMensaje(texto)
    setError(null)
    setTimeout(() => setMensaje(null), 3000)
  }

  function avisarError(texto) {
    setError(texto)
    setMensaje(null)
    setTimeout(() => setError(null), 4000)
  }

  // Al abrir el modal se cargan roles, permisos y todas las asignaciones.
  useEffect(() => {
    if (!isOpen || !accessToken) return
    let sigueMontado = true

    async function cargar() {
      try {
        const [rolesData, permisosData, asignacionesData] = await Promise.all([
          api.get('/acceso/roles', { token: accessToken }),
          api.get('/acceso/permisos', { token: accessToken }),
          api.get('/acceso/roles-permisos', { token: accessToken }),
        ])
        if (!sigueMontado) return

        const rolesActivos = rolesData.items.filter((r) => r.rol_est === 'A')
        setRoles(rolesActivos)
        setPermisos(permisosData.items)

        // Las asignaciones vienen todas juntas: se reparten en dos mapas,
        // rol_cod -> Set de per_cod, y rp_cod -> per_cod.
        const porRol = {}
        const idDe = {}
        for (const asignacion of asignacionesData.items) {
          if (asignacion.rp_est !== 'A') continue
          if (!porRol[asignacion.rol_cod]) porRol[asignacion.rol_cod] = new Set()
          porRol[asignacion.rol_cod].add(asignacion.per_cod)
          idDe[`${asignacion.rol_cod}:${asignacion.per_cod}`] = asignacion.rp_cod
        }
        setAsignados(porRol)
        setIdsAsignacion(idDe)
        setRolElegido(rolesActivos[0]?.rol_cod ?? null)
      } catch (err) {
        if (sigueMontado) avisarError(`Error al cargar datos: ${err.message}`)
      }
    }

    cargar()
    return () => {
      sigueMontado = false
    }
  }, [isOpen, accessToken])

  async function crearRol(evento) {
    evento.preventDefault()
    const nombre = nombreRol.trim()
    if (!nombre) return

    try {
      await api.post('/acceso/roles', { rol_nom: nombre }, { token: accessToken })
      const datos = await api.get('/acceso/roles', { token: accessToken })
      const activos = datos.items.filter((r) => r.rol_est === 'A')
      setRoles(activos)
      setCreandoRol(false)
      setNombreRol('')
      setRolElegido(activos.find((r) => r.rol_nom === nombre)?.rol_cod ?? null)
      avisar(`Rol '${nombre}' creado.`)
    } catch (err) {
      avisarError(`No se pudo crear el rol: ${err.message}`)
    }
  }

  async function darDeBajaRol(rol) {
    if (!window.confirm(`¿Dar de baja el rol '${rol.rol_nom}'?`)) return
    try {
      await api.del(`/acceso/roles/${rol.rol_cod}`, { token: accessToken })
      const datos = await api.get('/acceso/roles', { token: accessToken })
      const activos = datos.items.filter((r) => r.rol_est === 'A')
      setRoles(activos)
      if (rolElegido === rol.rol_cod) setRolElegido(activos[0]?.rol_cod ?? null)
      avisar(`Rol '${rol.rol_nom}' dado de baja.`)
    } catch (err) {
      avisarError(`No se pudo dar de baja el rol: ${err.message}`)
    }
  }

  // Marca o desmarca un permiso del rol elegido y lo guarda en el backend.
  async function alternarPermiso(per_cod, marcado) {
    const clave = `${rolElegido}:${per_cod}`

    // Primero se refleja en pantalla; si el backend rechaza, se revierte.
    setAsignados((anterior) => {
      const copia = new Set(anterior[rolElegido] || [])
      if (marcado) copia.add(per_cod)
      else copia.delete(per_cod)
      return { ...anterior, [rolElegido]: copia }
    })

    try {
      if (marcado) {
        await api.post('/acceso/roles-permisos', { rol_cod: rolElegido, per_cod }, { token: accessToken })
        avisar('Permiso asignado.')
      } else {
        const id = idsAsignacion[clave]
        await api.del(`/acceso/roles-permisos/${id}`, { token: accessToken })
        avisar('Permiso quitado.')
      }
      // Se recargan las asignaciones para tener los ids al dia.
      const datos = await api.get('/acceso/roles-permisos', { token: accessToken })
      const porRol = {}
      const idDe = {}
      for (const asignacion of datos.items) {
        if (asignacion.rp_est !== 'A') continue
        if (!porRol[asignacion.rol_cod]) porRol[asignacion.rol_cod] = new Set()
        porRol[asignacion.rol_cod].add(asignacion.per_cod)
        idDe[`${asignacion.rol_cod}:${asignacion.per_cod}`] = asignacion.rp_cod
      }
      setAsignados(porRol)
      setIdsAsignacion(idDe)
    } catch (err) {
      avisarError(`No se pudo guardar el permiso: ${err.message}`)
      const copia = new Set(asignados[rolElegido] || [])
      if (marcado) copia.delete(per_cod)
      else copia.add(per_cod)
      setAsignados((anterior) => ({ ...anterior, [rolElegido]: copia }))
    }
  }

  const grupos = agruparPorModulo(permisos)
  const modulos = Object.keys(grupos)
  const permisosDelRol = asignados[rolElegido] || new Set()

  if (!isOpen) return null

  return (
    <div className="modal-overlay roles-modal-overlay" onClick={onClose}>
      <div className="roles-modal" onClick={(e) => e.stopPropagation()}>
        <div className="roles-modal-head">
          <div>
            <h2 className="roles-modal-title">Roles y permisos</h2>
            <p className="roles-modal-sub">Crea roles y decide qué puede hacer cada uno</p>
          </div>
          <button type="button" className="icon-btn" title="Cerrar" onClick={onClose}>
            <IconClose />
          </button>
        </div>

        {mensaje && <div className="rp-toast success">{mensaje}</div>}
        {error && <div className="rp-toast error">{error}</div>}

        <div className="roles-grid">
          {/* ============ ROLES ============ */}
          <section className="roles-col">
            <article className="card">
              <div className="card-head">
                <h3 className="card-title">Roles</h3>
                <span className="card-subtitle">{roles.length} roles activos</span>
              </div>

              <table className="roles-table">
                <thead>
                  <tr>
                    <th>Rol</th>
                    <th style={{ textAlign: 'center' }}>Permisos</th>
                    <th style={{ textAlign: 'right' }}>Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  {roles.map((rol) => (
                    <tr
                      key={rol.rol_cod}
                      className={rol.rol_cod === rolElegido ? 'selected' : ''}
                      onClick={() => setRolElegido(rol.rol_cod)}
                    >
                      <td>
                        <span className={`rol-pill ${rol.rol_nom.toLowerCase()}`}>{rol.rol_nom}</span>
                      </td>
                      <td style={{ textAlign: 'center' }}>
                        <span className="perm-count">{(asignados[rol.rol_cod] || new Set()).size}</span>
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        <div className="row-actions" onClick={(e) => e.stopPropagation()}>
                          {puedeEliminar && (
                            <button
                              type="button"
                              className="icon-btn danger"
                              title="Dar de baja el rol"
                              onClick={() => darDeBajaRol(rol)}
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
                {puedeCrear && !creandoRol && (
                  <button type="button" className="btn btn-primary" onClick={() => setCreandoRol(true)}>
                    <IconPlus />
                    Nuevo rol
                  </button>
                )}
                {puedeCrear && creandoRol && (
                  <form className="rp-edit-form" onSubmit={crearRol}>
                    <input
                      className="form-input"
                      value={nombreRol}
                      onChange={(e) => setNombreRol(e.target.value)}
                      placeholder="Nombre del rol"
                      maxLength={50}
                      autoFocus
                    />
                    <button type="submit" className="btn btn-primary">Guardar</button>
                    <button
                      type="button"
                      className="btn btn-outline"
                      onClick={() => {
                        setCreandoRol(false)
                        setNombreRol('')
                      }}
                    >
                      Cancelar
                    </button>
                  </form>
                )}
              </div>
            </article>
          </section>

          {/* ============ MATRIZ DE PERMISOS ============ */}
          <section className="roles-col">
            <article className="card">
              <div className="card-head">
                <div className="head-text">
                  <h3 className="card-title">Permisos</h3>
                  <span className="card-subtitle">
                    {rolElegido
                      ? `Marca lo que puede hacer el rol '${roles.find((r) => r.rol_cod === rolElegido)?.rol_nom}'`
                      : 'Selecciona un rol'}
                  </span>
                </div>
                <IconShield />
              </div>

              {rolElegido ? (
                <div className="perm-matrix">
                  {modulos.map((modulo) => (
                    <div key={modulo} className="perm-group">
                      <div className="perm-group-head">
                        <h4 className="perm-modulo">{modulo}</h4>
                        <span className="card-subtitle">{grupos[modulo].length} permisos</span>
                      </div>
                      <ul className="perm-list">
                        {grupos[modulo].map((permiso) => (
                          <li key={permiso.per_cod}>
                            <label className="perm-item">
                              <input
                                type="checkbox"
                                className="perm-checkbox"
                                checked={permisosDelRol.has(permiso.per_cod)}
                                disabled={!puedeEditar}
                                onChange={(e) => alternarPermiso(permiso.per_cod, e.target.checked)}
                              />
                              <span className="perm-nom">{nombrePermiso(permiso)}</span>
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
      </div>
    </div>
  )
}

export default RolesPermisosModal
