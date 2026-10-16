import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { usePushSubscription } from '../hooks/usePushSubscription.js'
import { useAuth } from '../hooks/useAuth.js'
import '../css/ModalNotificaciones.css'

// Etiquetas de severidad (los codigos vienen de la base v2).
const SEV = { C: 'Crítica', A: 'Alta', M: 'Media', B: 'Baja' }

// Fecha corta en es-ES para el historial de la campanita.
function fecha(valor) {
  if (!valor) return '—'
  const d = new Date(valor)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString('es', { dateStyle: 'short', timeStyle: 'short' })
}

/*
 * ModalNotificaciones: lo que abre la campanita de la barra superior.
 *
 * Tiene dos partes:
 *   1. El HISTORIAL real de notificaciones del usuario (tabla `notificaciones`),
 *      con marcar-leída por notificación y "marcar todas".
 *   2. El aviso de ESCRITORIO (Web Push), que es opcional y se activa aparte.
 *
 * `onLeidas` avisa al Topbar para que refresque el contador del badge.
 */
export default function ModalNotificaciones({ abierto, onCerrar, onLeidas }) {
  const { accessToken } = useAuth()
  const navigate = useNavigate()
  const { soportado, permiso, suscrito, cargando, error, suscribir, desuscribir } = usePushSubscription()

  const [items, setItems] = useState([])
  const [cargandoLista, setCargandoLista] = useState(false)
  const [errorLista, setErrorLista] = useState('')

  // Carga el historial cada vez que se abre la campanita.
  useEffect(() => {
    if (!abierto || !accessToken) return undefined
    let vivo = true

    const cargar = async () => {
      setCargandoLista(true)
      setErrorLista('')
      try {
        const r = await fetch('/api/v2/notificaciones?tamano=20', {
          headers: { Authorization: `Bearer ${accessToken}` },
        })
        if (!r.ok) throw new Error('No se pudieron cargar las notificaciones.')
        const d = await r.json()
        if (vivo) setItems(d.items || [])
      } catch (e) {
        if (vivo) setErrorLista(e.message || 'No se pudieron cargar las notificaciones.')
      } finally {
        if (vivo) setCargandoLista(false)
      }
    }

    cargar()
    return () => { vivo = false }
  }, [abierto, accessToken])

  if (!abierto) return null

  const sinLeer = items.filter((n) => !n.not_leida).length

  // Marca una notificación como leída (si no lo estaba).
  const leer = async (n) => {
    if (n.not_leida) return
    try {
      await fetch(`/api/v2/notificaciones/${n.not_cod}/leer`, {
        method: 'PATCH',
        headers: { Authorization: `Bearer ${accessToken}` },
      })
      setItems((lista) => lista.map((x) => (x.not_cod === n.not_cod ? { ...x, not_leida: true } : x)))
      onLeidas?.()
    } catch {
      // Silencioso: el contador se corrige en el siguiente sondeo.
    }
  }

  // Al pulsar una notificación: la marca leída y lleva a las alertas.
  // `not_url` es '/alertas/<cod>', pero la pantalla de detalle no existe,
  // por eso vamos a la lista (no al login, que es donde caería esa ruta).
  const abrir = async (n) => {
    await leer(n)
    if (!n.not_url) return
    onCerrar()
    navigate('/alertas')
  }

  const leerTodas = async () => {
    try {
      await fetch('/api/v2/notificaciones/leer-todas', {
        method: 'PATCH',
        headers: { Authorization: `Bearer ${accessToken}` },
      })
      setItems((lista) => lista.map((x) => ({ ...x, not_leida: true })))
      onLeidas?.()
    } catch {
      setErrorLista('No se pudieron marcar como leídas.')
    }
  }

  const activar = async () => {
    const sub = await suscribir(accessToken)
    if (sub) onCerrar()
  }

  const desactivar = async () => {
    await desuscribir(accessToken)
  }

  return (
    <div className="modal-notif-fondo" onClick={onCerrar}>
      <div className="modal-notif-caja" onClick={(e) => e.stopPropagation()}>
        <h2 className="modal-notif-titulo">
          🔔 Notificaciones {sinLeer > 0 && <span className="modal-notif-sinleer">{sinLeer} sin leer</span>}
        </h2>

        {/* ===== 1. HISTORIAL ===== */}
        {cargandoLista && <p className="modal-notif-mensaje">Cargando…</p>}
        {errorLista && <p className="modal-notif-mensaje error">{errorLista}</p>}

        {!cargandoLista && !errorLista && (
          <div className="modal-notif-items">
            {items.map((n) => (
              <button
                key={n.not_cod}
                type="button"
                className={n.not_leida ? 'modal-notif-item' : 'modal-notif-item no-leida'}
                onClick={() => abrir(n)}
              >
                <span className={`modal-notif-sev sev-${n.not_sev}`}>{SEV[n.not_sev] || n.not_sev}</span>
                <span className="modal-notif-item-cuerpo">
                  <span className="modal-notif-item-titulo">{n.not_titulo}</span>
                  {n.not_detalle && <span className="modal-notif-item-detalle">{n.not_detalle}</span>}
                  <span className="modal-notif-item-meta">{fecha(n.fec_creacion)}</span>
                </span>
              </button>
            ))}
            {!items.length && (
              <p className="modal-notif-vacio">No tienes notificaciones por ahora.</p>
            )}
          </div>
        )}

        {sinLeer > 0 && (
          <div className="modal-notif-acciones">
            <button type="button" className="modal-notif-btn secundario" onClick={leerTodas}>
              Marcar todas como leídas
            </button>
          </div>
        )}

        {/* ===== 2. NOTIFICACIONES DE ESCRITORIO (Web Push) ===== */}
        <h3 className="modal-notif-subtitulo">Notificaciones de escritorio</h3>

        {!soportado && (
          <p className="modal-notif-mensaje error">
            Este navegador no soporta notificaciones push. Prueba con Chrome, Edge o Firefox actualizado.
          </p>
        )}

        {soportado && !suscrito && (
          <p className="modal-notif-mensaje">
            Actívalas para recibir un aviso al instante (también con la pestaña cerrada) cuando
            se abra una alerta crítica <strong>C</strong> o alta <strong>A</strong>.
          </p>
        )}

        {soportado && suscrito && (
          <p className="modal-notif-mensaje exito">
            ✅ Ya estás suscrito. Recibirás las alertas en este dispositivo.
          </p>
        )}

        {error && <p className="modal-notif-mensaje error">{error}</p>}

        {permiso === 'denied' && (
          <p className="modal-notif-mensaje error">
            Has denegado las notificaciones antes. Para activarlas, ve a la configuración del navegador → Privacidad → Notificaciones → Permitir para este sitio.
          </p>
        )}

        <div className="modal-notif-acciones">
          {!suscrito && soportado && (
            <>
              <button type="button" className="modal-notif-btn secundario" onClick={onCerrar}>
                Cerrar
              </button>
              <button
                type="button"
                className="modal-notif-btn primario"
                onClick={activar}
                disabled={cargando || permiso === 'denied'}
              >
                {cargando ? 'Activando…' : 'Activar notificaciones'}
              </button>
            </>
          )}
          {suscrito && (
            <>
              <button type="button" className="modal-notif-btn secundario" onClick={onCerrar}>
                Cerrar
              </button>
              <button
                type="button"
                className="modal-notif-btn peligro"
                onClick={desactivar}
                disabled={cargando}
              >
                {cargando ? 'Desactivando…' : 'Desactivar'}
              </button>
            </>
          )}
          {!soportado && (
            <button type="button" className="modal-notif-btn secundario" onClick={onCerrar}>
              Cerrar
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
