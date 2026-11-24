// Login com Google (Google Identity Services). O Client ID vem do backend
// (GET /auth/google/config), então trocar o Client ID não exige novo build.
import { authService } from '../services/api';

const SCRIPT_URL = 'https://accounts.google.com/gsi/client';
let scriptPromise = null;
let clientIdPromise = null;

export function loadGoogleScript() {
  if (window.google?.accounts?.id) return Promise.resolve(window.google);
  if (!scriptPromise) {
    scriptPromise = new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = SCRIPT_URL;
      script.async = true;
      script.defer = true;
      script.onload = () => resolve(window.google);
      script.onerror = () => { scriptPromise = null; reject(new Error('Não foi possível carregar o login do Google.')); };
      document.head.appendChild(script);
    });
  }
  return scriptPromise;
}

// null quando o login com Google não está configurado no servidor
export function getGoogleClientId() {
  if (!clientIdPromise) {
    clientIdPromise = authService.googleConfig()
      .then(({ data }) => data?.clientId || null)
      .catch(() => { clientIdPromise = null; return null; });
  }
  return clientIdPromise;
}
