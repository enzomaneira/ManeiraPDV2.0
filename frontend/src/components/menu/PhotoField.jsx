import { useEffect, useRef, useState } from 'react';
import { Image, Upload, Loader2, CheckCircle, AlertCircle, Link as LinkIcon } from 'lucide-react';
import { imageService } from '../../services/api';
import { inputClass, getErrorMessage } from './menuUtils';

const MIN_WIDTH = 600;
const MIN_HEIGHT = 450;

// Campo de foto do produto: envia uma foto do computador (o PDV ajusta e manda
// ao Cloudflare R2) ou aceita um link, conferindo se a imagem abre e se tem o
// tamanho mínimo que a Keeta pede.
export default function PhotoField({ value, onChange, productName }) {
  const [uploadEnabled, setUploadEnabled] = useState(null); // null = verificando
  const [uploading, setUploading] = useState(false);
  const [uploadInfo, setUploadInfo] = useState(null);
  const [uploadError, setUploadError] = useState(null);
  const [check, setCheck] = useState({ state: 'empty' }); // empty | loading | ok | small | broken
  const fileInput = useRef(null);
  const url = (value || '').trim();

  useEffect(() => {
    imageService.status()
      .then(({ data }) => setUploadEnabled(Boolean(data.uploadEnabled)))
      .catch(() => setUploadEnabled(false));
  }, []);

  useEffect(() => {
    if (!url) { setCheck({ state: 'empty' }); return; }
    setCheck({ state: 'loading' });
  }, [url]);

  const handleLoaded = (event) => {
    const { naturalWidth: width, naturalHeight: height } = event.currentTarget;
    setCheck({ state: width >= MIN_WIDTH && height >= MIN_HEIGHT ? 'ok' : 'small', width, height });
  };

  const handleFile = async (event) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    setUploading(true);
    setUploadError(null);
    setUploadInfo(null);
    try {
      const { data } = await imageService.upload(file, productName);
      onChange(data.url);
      setUploadInfo(data);
    } catch (error) {
      setUploadError(getErrorMessage(error, 'Não foi possível enviar a foto.'));
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-start gap-3">
        <div className="flex-1 min-w-[240px] space-y-2">
          <button type="button" onClick={() => fileInput.current?.click()} disabled={!uploadEnabled || uploading}
            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl border-2 border-dashed border-indigo-300 text-indigo-700 font-bold text-sm hover:bg-indigo-50 disabled:border-slate-200 disabled:text-slate-400 disabled:hover:bg-transparent">
            {uploading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
            {uploading ? 'Ajustando e enviando…' : 'Enviar foto do computador'}
          </button>
          <input ref={fileInput} type="file" accept="image/jpeg,image/png,image/webp" className="hidden" onChange={handleFile} aria-label="Arquivo da foto" />
          {uploadEnabled === false && (
            <p className="text-xs text-slate-400">Envio de fotos ainda não configurado (Cloudflare R2). Por enquanto, cole o link abaixo.</p>
          )}
          <div className="relative">
            <LinkIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input type="url" className={inputClass + ' pl-9 font-mono'} value={value} onChange={e => { setUploadInfo(null); onChange(e.target.value); }}
              placeholder="ou cole o link da foto (https://…)" aria-label="Link da foto" />
          </div>
        </div>
        <div className="w-28 h-[84px] rounded-xl bg-slate-100 border border-slate-200 flex items-center justify-center overflow-hidden shrink-0">
          {url && check.state !== 'broken'
            ? <img key={url} src={url} alt="Prévia da foto" className="w-full h-full object-cover" onLoad={handleLoaded} onError={() => setCheck({ state: 'broken' })} />
            : <Image className="w-6 h-6 text-slate-300" />}
        </div>
      </div>

      {uploadError && <p className="flex items-start gap-1.5 text-xs font-bold text-red-600"><AlertCircle className="w-4 h-4 shrink-0" />{uploadError}</p>}
      {uploadInfo && (
        <p className="flex items-start gap-1.5 text-xs text-green-700">
          <CheckCircle className="w-4 h-4 shrink-0" />
          <span>
            Foto enviada: {uploadInfo.originalWidth}×{uploadInfo.originalHeight} → <b>{uploadInfo.width}×{uploadInfo.height}</b>, {uploadInfo.sizeKb} KB.
            {uploadInfo.changes?.length > 0 && <> Ajustes: {uploadInfo.changes.join(', ')}.</>} Clique em salvar para usar no produto.
          </span>
        </p>
      )}
      {!uploadInfo && check.state === 'ok' && <p className="flex items-center gap-1.5 text-xs text-green-700"><CheckCircle className="w-4 h-4" />Foto válida para a Keeta ({check.width}×{check.height} px).</p>}
      {!uploadInfo && check.state === 'small' && (
        <p className="flex items-start gap-1.5 text-xs font-bold text-amber-700"><AlertCircle className="w-4 h-4 shrink-0" />
          Foto pequena demais: {check.width}×{check.height} px. A Keeta pede no mínimo {MIN_WIDTH}×{MIN_HEIGHT}. {uploadEnabled ? 'Envie uma foto maior pelo botão acima.' : 'Use uma foto maior.'}
        </p>
      )}
      {check.state === 'broken' && (
        <p className="flex items-start gap-1.5 text-xs font-bold text-red-600"><AlertCircle className="w-4 h-4 shrink-0" />
          Não foi possível abrir esta imagem. Confira se o link abre a foto diretamente no navegador.
        </p>
      )}
      <p className="text-[11px] text-slate-400">O PDV ajusta a foto enviada para 4:3 (até 1200×900 px, JPG). Mínimo aceito: {MIN_WIDTH}×{MIN_HEIGHT} px.</p>
    </div>
  );
}
