// Modal de alta/edicion de un usuario (pantalla de Configuracion).
//
// Trabaja contra la API v2:
//   GET   /acceso/roles    -> lista de roles para el desplegable
//   (el alta y la edicion las hace la pagina que abre este modal)
//
// Campos segun el schema v2:
//   UsuarioCreate  -> usu_nom, usu_log, password, usu_dni, rol_cod, usu_ema, usu_tel
//   UsuarioUpdate  -> usu_nom, usu_ema, usu_dni, usu_tel, rol_cod, usu_est, password
// El usuario (usu_log) y el DNI no se pueden cambiar al editar: no vienen en
// UsuarioUpdate.
import { useEffect, useState } from 'react'
import api from '../services/api'
import '../css/Modal.css'

// Estado inicial del formulario. Los mismos nombres que usa el backend.
const FORMULARIO_VACIO = {
  usu_nom: '',
  usu_log: '',
  password: '',
  usu_dni: '',
  usu_ema: '',
  usu_tel: '',
  rol_cod: '',
  usu_est: 'A',
}

function ModalUsuario({ isOpen, onClose, onSave, accessToken, usuario, error }) {
  const [form, setForm] = useState(FORMULARIO_VACIO)
  const [roles, setRoles] = useState([])
  const esEdicion = Boolean(usuario)

  // Carga los roles activos para el desplegable.
  useEffect(() => {
    if (!isOpen || !accessToken) return
    let sigueMontado = true

    api
      .get('/acceso/roles', { token: accessToken })
      .then((data) => {
        if (sigueMontado) setRoles(data.items.filter((r) => r.rol_est === 'A'))
      })
      .catch((err) => console.error('Error al cargar roles:', err))

    return () => {
      sigueMontado = false
    }
  }, [isOpen, accessToken])

  // Rellena el formulario con el usuario que se esta editando.
  useEffect(() => {
    if (!isOpen) return
    if (!usuario) {
      setForm(FORMULARIO_VACIO)
      return
    }
    setForm({
      usu_nom: usuario.usu_nom || '',
      usu_log: usuario.usu_log || '',
      password: '',
      usu_dni: usuario.usu_dni || '',
      usu_ema: usuario.usu_ema || '',
      usu_tel: usuario.usu_tel || '',
      rol_cod: String(usuario.rol_cod ?? ''),
      usu_est: usuario.usu_est || 'A',
    })
  }, [isOpen, usuario])

  // Un solo manejador para todos los campos.
  function cambiarCampo(evento) {
    const { name, value, type, checked } = evento.target
    setForm((anterior) => ({ ...anterior, [name]: type === 'checkbox' ? checked : value }))
  }

  // Arma el cuerpo que espera el backend y se lo pasa a la pagina.
  function enviar(evento) {
    evento.preventDefault()

    const cuerpo = {
      usu_nom: form.usu_nom.trim(),
      usu_ema: form.usu_ema.trim() || null,
      usu_tel: form.usu_tel.trim() || null,
      rol_cod: Number(form.rol_cod),
    }
    // La clave solo se manda si se escribio algo: en edicion, vacio = no cambia.
    if (form.password) cuerpo.password = form.password

    if (esEdicion) {
      cuerpo.usu_dni = form.usu_dni.trim() || null
      cuerpo.usu_est = form.usu_est
    } else {
      cuerpo.usu_log = form.usu_log.trim()
      cuerpo.usu_dni = form.usu_dni.trim()
    }

    onSave(cuerpo)
  }

  if (!isOpen) return null

  return (
    <div className="modal-overlay">
      <div className="modal">
        <div className="modal-head">
          <h3 className="modal-title">{esEdicion ? 'Editar usuario' : 'Crear nuevo usuario'}</h3>
        </div>

        <form onSubmit={enviar}>
          <div className="form-group">
            <label className="form-label" htmlFor="usu_nom">Nombre</label>
            <input
              id="usu_nom"
              name="usu_nom"
              className="form-input"
              value={form.usu_nom}
              onChange={cambiarCampo}
              maxLength={100}
              required
            />
          </div>

          {/* El usuario es la clave con la que se inicia sesion: solo al crear. */}
          <div className="form-group">
            <label className="form-label" htmlFor="usu_log">Usuario</label>
            <input
              id="usu_log"
              name="usu_log"
              className="form-input"
              value={form.usu_log}
              onChange={cambiarCampo}
              minLength={3}
              maxLength={50}
              readOnly={esEdicion}
              required={!esEdicion}
            />
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="usu_dni">DNI</label>
            <input
              id="usu_dni"
              name="usu_dni"
              className="form-input"
              value={form.usu_dni}
              onChange={cambiarCampo}
              maxLength={12}
              required
            />
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="usu_ema">Email</label>
            <input
              id="usu_ema"
              name="usu_ema"
              type="email"
              className="form-input"
              value={form.usu_ema}
              onChange={cambiarCampo}
            />
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="usu_tel">Teléfono</label>
            <input
              id="usu_tel"
              name="usu_tel"
              className="form-input"
              value={form.usu_tel}
              onChange={cambiarCampo}
              maxLength={20}
            />
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="password">
              Contraseña{esEdicion && ' (vacío = no cambiarla)'}
            </label>
            <input
              id="password"
              name="password"
              type="password"
              className="form-input"
              value={form.password}
              onChange={cambiarCampo}
              minLength={8}
              required={!esEdicion}
            />
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="rol_cod">Rol</label>
            <select
              id="rol_cod"
              name="rol_cod"
              className="form-input"
              value={form.rol_cod}
              onChange={cambiarCampo}
              required
            >
              <option value="">Selecciona un rol…</option>
              {roles.map((rol) => (
                <option key={rol.rol_cod} value={rol.rol_cod}>
                  {rol.rol_nom}
                </option>
              ))}
            </select>
          </div>

          {esEdicion && (
            <div className="form-group">
              <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <input
                  type="checkbox"
                  name="usu_est"
                  checked={form.usu_est === 'A'}
                  onChange={cambiarCampo}
                />
                <span>Usuario activo</span>
              </label>
            </div>
          )}

          {error && <p className="modal-error">{error}</p>}

          <div className="modal-actions">
            <button type="button" onClick={onClose} className="btn btn-outline">Cancelar</button>
            <button type="submit" className="btn btn-primary">Guardar</button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default ModalUsuario
