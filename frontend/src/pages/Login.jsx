// Pagina de inicio de sesion.
//
// Antes: el boton solo navegaba a /inicio sin validar nada.
// Ahora: envia las credenciales al backend (POST /auth/login),
// maneja los errores de validacion (400/401/403) y redirige a /inicio
// solo si la autenticacion fue exitosa.
//
// Nota: los enlaces "Recordar / Crear cuenta / Recuperar" se mantienen
// como placeholders (mock) por ahora.
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import logo from '../assets/brands/logo_steelNorth.png'
import facebookIcon from '../assets/icons/facebook_icon.png'
import instagramIcon from '../assets/icons/instagram_icon.png'
import whatsappIcon from '../assets/icons/whatsapp_icon.png'
import { useAuth } from '../context/AuthContext.jsx'
import '../css/Login.css'

function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [remember, setRemember] = useState(false)
  const [error, setError] = useState('')
  const { login, loading } = useAuth()
  const navigate = useNavigate()

  // Envia la peticion de login. Muestra el error en pantalla si la
  // autenticacion falla y NO redirige.
  async function handleSubmit(e) {
    e.preventDefault()
    setError('')

    // Validacion basica del lado del cliente.
    if (!email || !password) {
      setError('Ingrese su correo y contrasena.')
      return
    }

    try {
      await login({ email, password })
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
            <label htmlFor="email">Correo electrónico</label>
            <input
              id="email"
              type="email"
              placeholder="correo@ejemplo.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>

          <div className="login-field">
            <label htmlFor="password">Contraseña</label>
            <input
              id="password"
              type="password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>

          <label className="login-remember">
            <input
              type="checkbox"
              checked={remember}
              onChange={(e) => setRemember(e.target.checked)}
            />
            Recordar contraseña
          </label>

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