// Pagina de inicio de sesion.
//
// En la v2 el login es por USUARIO (columna usu_log del esquema), no por
// correo. Envia POST /api/v2/auth/login con { usuario, clave }, muestra los
// errores que devuelve el backend (401 usuario/clave incorrectos, 403 usuario
// inactivo) y redirige a /inicio solo si la autenticacion fue exitosa.
//
// Nota: los enlaces de recuperacion y redes sociales siguen como
// placeholders; el "recordar contraseña" no aplica porque el token se
// guarda en memoria y se pierde al recargar.
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import logo from '../assets/brands/logo_steelNorth.png'
import facebookIcon from '../assets/icons/facebook_icon.png'
import instagramIcon from '../assets/icons/instagram_icon.png'
import whatsappIcon from '../assets/icons/whatsapp_icon.png'
import { useAuth } from '../context/AuthContext.jsx'
import '../css/Login.css'

function Login() {
  const [usuario, setUsuario] = useState('')
  const [clave, setClave] = useState('')
  const [error, setError] = useState('')
  const { login, loading } = useAuth()
  const navigate = useNavigate()

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')

    const us = usuario.trim()

    // Validaciones minimas del lado del cliente para no llamar al backend
    // con datos claramente incompletos.
    if (!us) {
      setError('Ingrese su usuario.')
      return
    }
    if (!clave) {
      setError('Ingrese su contrasena.')
      return
    }

    try {
      await login({ usuario: us, clave })
      navigate('/inicio')
    } catch (err) {
      setError(err.message || 'No se pudo iniciar sesion.')
    }
  }

  return (
    <main className="login">
      <div className="login-card">
        <img className="login-logo" src={logo} alt="Steel North" />

        <form className="login-form" onSubmit={handleSubmit}>
          <div className="login-field">
            <label htmlFor="usuario">Usuario</label>
            <input
              id="usuario"
              type="text"
              placeholder="admin"
              autoComplete="username"
              value={usuario}
              onChange={(e) => setUsuario(e.target.value)}
              required
            />
          </div>

          <div className="login-field">
            <label htmlFor="clave">Contraseña</label>
            <input
              id="clave"
              type="password"
              placeholder="••••••••"
              autoComplete="current-password"
              value={clave}
              onChange={(e) => setClave(e.target.value)}
              required
            />
          </div>

          {error && <p className="login-error">{error}</p>}

          <button type="submit" className="login-button" disabled={loading}>
            {loading ? 'VALIDANDO…' : 'INICIAR SESIÓN'}
          </button>
        </form>

        <div className="login-links">
          <a href="#recuperar">¿Olvidaste tu contraseña?</a>
        </div>

        <div className="login-social">
          <a href="#facebook" aria-label="Facebook">
            <img src={facebookIcon} alt="" />
          </a>
          <a href="#instagram" aria-label="Instagram">
            <img src={instagramIcon} alt="" />
          </a>
          <a href="#whatsapp" aria-label="WhatsApp">
            <img src={whatsappIcon} alt="" />
          </a>
        </div>
      </div>
    </main>
  )
}

export default Login
