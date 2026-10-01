import { useEffect, useState } from 'react'
import api from '../services/api'
import '../css/Modal.css'

function ModalUsuario({ isOpen, onClose, onSave, accessToken, usuario, error }) {
  const [roles, setRoles] = useState([])
  const esEdicion = Boolean(usuario)

  useEffect(() => {
    async function loadRoles() {
      if (!isOpen || !accessToken) return
      try {
        const data = await api.get('/roles', { token: accessToken })
        setRoles(data.filter((r) => r.rol_act || (usuario && r.rol_nom === usuario.usu_rol)))
      } catch (err) {
        console.error("Error al cargar roles:", err)
      }
    }
    loadRoles()
  }, [isOpen, accessToken, usuario])

  if (!isOpen) return null

  return (
    <div className="modal-overlay">
      <div className="modal">
        <div className="modal-head">
          <h3 className="modal-title">{esEdicion ? 'Editar usuario' : 'Crear nuevo usuario'}</h3>
        </div>
        <form onSubmit={(e) => {
          e.preventDefault();
          const formData = new FormData(e.target);
          onSave(Object.fromEntries(formData));
        }}>
          <div className="form-group">
            <label className="form-label">Nombre</label>
            <input name="usu_nom" className="form-input" required defaultValue={usuario?.usu_nom} />
          </div>
          <div className="form-group">
            <label className="form-label">Email</label>
            <input name="usu_ema" type="email" className="form-input" required defaultValue={usuario?.usu_ema} />
          </div>
          <div className="form-group">
            <label className="form-label">{esEdicion ? 'Contraseña (dejar vacío para no cambiar)' : 'Contraseña'}</label>
            <input name="password" type="password" className="form-input" minLength={8} required={!esEdicion} />
          </div>
          <div className="form-group">
            <label className="form-label">Iniciales</label>
            <input name="usu_ini" className="form-input" maxLength={4} required defaultValue={usuario?.usu_ini} />
          </div>
          <div className="form-group">
            <label className="form-label">Rol</label>
            <select name="usu_rol" className="form-input" required defaultValue={usuario?.usu_rol}>
              {roles.length === 0 && <option value="">Cargando roles...</option>}
              {roles.map((rol) => (
                <option key={rol.rol_cod} value={rol.rol_nom}>{rol.rol_nom}</option>
              ))}
            </select>
          </div>
          {esEdicion && (
            <div className="form-group">
              <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <input type="checkbox" name="usu_act" defaultChecked={usuario.usu_act} />
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
  );
}

export default ModalUsuario;