import { useEffect, useRef, useState } from 'react';
import { loadGoogleScript, getGoogleClientId } from '../utils/googleIdentity';

// Botão oficial "Entrar com Google". Não aparece se o servidor não tiver o
// Client ID configurado. onCredential recebe o ID token do Google.
export default function GoogleButton({ onCredential, text = 'signin_with', width = 320, onUnavailable }) {
  const container = useRef(null);
  const callback = useRef(onCredential);
  const [available, setAvailable] = useState(true);
  callback.current = onCredential;

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const clientId = await getGoogleClientId();
      if (!clientId) { if (!cancelled) { setAvailable(false); onUnavailable?.(); } return; }
      try {
        const google = await loadGoogleScript();
        if (cancelled || !container.current) return;
        google.accounts.id.initialize({
          client_id: clientId,
          callback: (response) => callback.current?.(response.credential),
          ux_mode: 'popup',
          auto_select: false,
        });
        container.current.innerHTML = '';
        google.accounts.id.renderButton(container.current, {
          type: 'standard', theme: 'outline', size: 'large', shape: 'pill', text, width, locale: 'pt-BR', logo_alignment: 'center',
        });
      } catch {
        if (!cancelled) { setAvailable(false); onUnavailable?.(); }
      }
    })();
    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text, width]);

  if (!available) return null;
  return <div ref={container} className="flex justify-center min-h-[44px]" />;
}
