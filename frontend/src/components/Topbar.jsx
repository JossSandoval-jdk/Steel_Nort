import { useEffect, useState } from 'react'
import avatar from '../assets/icons/avatar_default.png'
import cerrarIcon from '../assets/icons/cerrar_icon.png'
import ModalNotificaciones from './ModalNotificaciones.jsx'
import { useAuth } from '../context/AuthContext.jsx'
import '../css/Topbar.css'

/*
 * Topbar: Barra superior de la aplicación.
 * Muestra el perfil del usuario actual (nombre y cargo), la campanita de
 * notificaciones con contador de no leídas, y el botón de cerrar sesión.
 */
function Topbar({ nombre = 'Nombre Usuario', cargo = 'Cargo' }) {
  const { accessToken } = useAuth()
  const [modalAbierto, setModalAbierto] = useState(false)
  const [noLeidas, setNoLeidas] = useState(0)

  // Pedir el contador cada 60 s mientras la app está abierta.
  useEffect(() => {
    if (!accessToken) return undefined

    let vigente = true

    const consultar = async () => {
      try {
        const r = await fetch('/api/v2/notificaciones/contador', {
          headers: { Authorization: `Bearer ${accessToken}` },
        })
        if (!r.ok) return
        const data = await r.json()
        if (vigente) setNoLeidas(data.no_leidas || 0)
      } catch {
        // Silencioso: si falla el polling, no rompemos la UI.
      }
    }

    consultar()
    const id = setInterval(consultar, 60_000)

    return () => {
      vigente = false
      clearInterval(id)
    }
  }, [accessToken])

  return (
    <>
      <header className="topbar">
        <div className="topbar-user">
          <img className="topbar-avatar" src={avatar} alt="Avatar" />
          <div className="topbar-info">
            <span className="topbar-nombre">{nombre}</span>
            <span className="topbar-cargo">{cargo}</span>
          </div>
        </div>

        <div className="topbar-acciones">
          <button
            type="button"
            className="topbar-campanita"
            aria-label="Notificaciones"
            title="Notificaciones"
            onClick={() => setModalAbierto(true)}
          >
            🔔
            {noLeidas > 0 && (
              <span className="topbar-badge">{noLeidas > 99 ? '99+' : noLeidas}</span>
            )}
          </button>

          <button
            type="button"
            className="topbar-cerrar"
            aria-label="Cerrar sesión"
          >
            <img src={cerrarIcon} alt="" />
          </button>
        </div>
      </header>

      <ModalNotificaciones
        abierto={modalAbierto}
        onCerrar={() => setModalAbierto(false)}
      />
    </>
  )
}

export default Topbar