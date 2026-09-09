import avatar from '../assets/icons/avatar_default.png'
import cerrarIcon from '../assets/icons/cerrar_icon.png'
import '../css/Topbar.css'

/*
 * Topbar: Barra superior de la aplicación.
 * Muestra el perfil del usuario actual (nombre y cargo) y proporciona
 * la opción de cerrar la sesión.
 */
function Topbar({ nombre = 'Nombre Usuario', cargo = 'Cargo' }) {
  return (
    <header className="topbar">
      <div className="topbar-user">
        <img className="topbar-avatar" src={avatar} alt="Avatar" />
        <div className="topbar-info">
          <span className="topbar-nombre">{nombre}</span>
          <span className="topbar-cargo">{cargo}</span>
        </div>
      </div>

      <button
        type="button"
        className="topbar-cerrar"
        aria-label="Cerrar sesión"
      >
        <img src={cerrarIcon} alt="" />
      </button>
    </header>
  )
}

export default Topbar

