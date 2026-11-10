'use strict';
/* Faceless Cloud Studio · painel do robô de vídeo */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (v = '') => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const clone = o => (o === undefined ? undefined : JSON.parse(JSON.stringify(o)));
const deepGet = (o, p) => p.split('.').reduce((a, k) => (a == null ? undefined : a[k]), o);
function deepSet(o, p, v) {
  const ks = p.split('.'); let cur = o;
  ks.slice(0, -1).forEach(k => { if (typeof cur[k] !== 'object' || cur[k] === null) cur[k] = {}; cur = cur[k]; });
  cur[ks[ks.length - 1]] = v;
}
function deepMerge(a, b) {
  const out = clone(a) || {};
  Object.entries(b || {}).forEach(([k, v]) => {
    out[k] = (v && typeof v === 'object' && !Array.isArray(v) && out[k] && typeof out[k] === 'object') ? deepMerge(out[k], v) : clone(v);
  });
  return out;
}
const fmtTime = s => { s = Math.max(0, Math.floor(Number(s) || 0)); const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), x = s % 60; return h ? `${h}:${String(m).padStart(2, '0')}:${String(x).padStart(2, '0')}` : `${m}:${String(x).padStart(2, '0')}`; };
const fmtAudioTime = s => { const n = Number(s); return Number.isFinite(n) && n > 0 ? fmtTime(Math.max(1, Math.round(n))) : 'Duração não detectada'; };
const clock = iso => { try { return new Date(iso).toLocaleTimeString('pt-BR', { hour12: false }); } catch { return ''; } };

/* ---------- ícones */
const ICONS = {
  file: 'M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z M14 3v5h5',
  image: 'M4 5h16v14H4z M4 16l5-5 4 4 3-3 4 4 M9 9.5h.01',
  film: 'M4 4h16v16H4z M8 4v16 M16 4v16 M4 9h4 M4 15h4 M16 9h4 M16 15h4',
  palette: 'M12 3a9 9 0 1 0 0 18c1.2 0 1.8-.8 1.8-1.7 0-1-.8-1.4-.8-2.3 0-.9.7-1.5 1.7-1.5H17a4 4 0 0 0 4-4c0-4.4-4-8.5-9-8.5z M7.5 11h.01 M10 7.5h.01 M14.5 7.5h.01',
  music: 'M9 18V5l10-2v13 M9 18a3 3 0 1 1-3-3 3 3 0 0 1 3 3z M19 16a3 3 0 1 1-3-3 3 3 0 0 1 3 3z',
  sliders: 'M4 6h10 M18 6h2 M4 12h4 M12 12h8 M4 18h12 M14 4v4 M8 10v4 M16 16v4',
  check: 'M5 12.5l4.5 4.5L19 7.5', x: 'M6 6l12 12 M18 6L6 18', minus: 'M6 12h12',
  play: 'M8 5v14l11-7z', pause: 'M8 5v14 M16 5v14',
  upload: 'M12 16V4 M7 9l5-5 5 5 M4 20h16', download: 'M12 4v12 M7 11l5 5 5-5 M4 20h16',
  bot: 'M12 3v3 M7 8h10a3 3 0 0 1 3 3v6a3 3 0 0 1-3 3H7a3 3 0 0 1-3-3v-6a3 3 0 0 1 3-3z M9 13h.01 M15 13h.01 M9.5 16.5h5',
  spark: 'M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z M19 16l.7 2 2 .7-2 .7-.7 2-.7-2-2-.7 2-.7z',
  search: 'M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14z M20 20l-4-4',
  refresh: 'M4 12a8 8 0 0 1 14-5.3L20 9 M20 4v5h-5 M20 12a8 8 0 0 1-14 5.3L4 15 M4 20v-5h5',
  trash: 'M5 7h14 M10 4h4 M7 7l1 13h8l1-13 M10 11v5 M14 11v5',
  mic: 'M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3z M6 11a6 6 0 0 0 12 0 M12 17v4',
  box: 'M12 3l8 4.5v9L12 21l-8-4.5v-9z M4 7.5l8 4.5 8-4.5 M12 12v9',
  alert: 'M12 4l9 16H3z M12 10v4 M12 17h.01',
  'arrow-right': 'M5 12h14 M13 6l6 6-6 6', 'arrow-left': 'M19 12H5 M11 6l-6 6 6 6',
  link: 'M14 4h6v6 M20 4l-9 9 M18 14v5H5V6h5',
  list: 'M8 6h13 M8 12h13 M8 18h13 M3 6h.01 M3 12h.01 M3 18h.01',
  send: 'M22 2L11 13 M22 2l-7 20-4-9-9-4z',
  terminal: 'M4 5h16v14H4z M7 10l3 2-3 2 M12 15h5',
  scissors: 'M6 6a2 2 0 1 0 0 .01 M6 18a2 2 0 1 0 0 .01 M8 7.5L20 18 M8 16.5L20 6',
  copy: 'M9 9h11v11H9z M5 15V4h11',
  chrome: 'M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z',
};
const ic = n => `<svg class="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="${ICONS[n] || ''}"/></svg>`;
const hydrateIcons = (root = document) => $$('[data-ic]', root).forEach(el => { el.outerHTML = ic(el.dataset.ic); });

/* ---------- vozes salvas recomendadas */
const SAVED_VOICES = [
  { id: 'bf322df2096a46f18c579d0baa36f41d', title: 'Adrian', desc: 'Voz masculina estável, firme e confiável. Ideal para narrações cinematográficas e documentários.', lang: 'en', flag: '🇺🇸', tags: ['Firme', 'Confiável', 'Documentário'] },
  { id: '536d3a5e000945adb7038665781a4aca', title: 'Ethan', desc: 'Tom curioso e didático. Excelente para vídeos explicativos, curiosidades e canais explainer.', lang: 'en', flag: '🇺🇸', tags: ['Curioso', 'Didático', 'Explainer'] },
  { id: 'f8dfe9c83081432386f143e2fe9767ef', title: 'Book Record Regular', desc: 'Voz masculina madura, profunda, rasgada e rouca com autoridade para contação dramática de histórias.', lang: 'en', flag: '🇺🇸', tags: ['Grave', 'Rouca', 'Storytelling'] },
  { id: 'bf4a01bacf1b43b188c2c13ebdc77166', title: 'Marcus - Calm Male', desc: 'Narrador masculino calmo e claro para YouTube Faceless, documentários e podcasts.', lang: 'en', flag: '🇺🇸', tags: ['Calmo', 'YouTube', 'Faceless'] },
  { id: 'a754ca8729d642d9a918a42b5b6a77d1', title: 'Dave - Australian Male', desc: 'Voz masculina profunda com sotaque australiano natural para narração moderna e social media.', lang: 'en', flag: '🇦🇺', tags: ['Profunda', 'Australiano', 'Social Media'] },
  { id: '53ac6dc4ad314fed88aa28732ad9c87d', title: 'Gabriel VO - Spanish', desc: 'Voz castelhana profunda e ressonante com presença calorosa. Perfeita para documentários e thrillers.', lang: 'es', flag: '🇪🇸', tags: ['Castelhano', 'Profundo', 'Documentário'] },
  { id: 'd219d7c37aeb4fba87b4567ef982ce86', title: 'Rui Burigo', desc: 'Voz masculina suave e tranquila em português. Transmite paz, bem-estar, autenticidade e conexão.', lang: 'pt', flag: '🇧🇷', tags: ['Suave', 'Tranquila', 'Autêntica'] },
  { id: '6fdff31635694522b2bb6592c49f02e8', title: 'Melky Fernandes', desc: 'Voz calma e pensativa em português. Ideal para reflexão e observação do cotidiano com serenidade.', lang: 'pt', flag: '🇧🇷', tags: ['Calma', 'Reflexiva', 'Serena'] },
  { id: '195885c4f0994bebb1160a6a500fa63d', title: 'Narrativa Serena', desc: 'Voz masculina suave e introspectiva em português. Excelente para conteúdos de reflexão e paz.', lang: 'pt', flag: '🇧🇷', tags: ['Serena', 'Introspectiva', 'Paz'] },
  { id: 'ecf9605f63d04284bbb36a9bb2d53966', title: 'João M (Narrativa Calma)', desc: 'Voz masculina calma e reflexiva em português. Dicção pausada e clara para momentos de introspecção.', lang: 'pt', flag: '🇧🇷', tags: ['Calma', 'Pausada', 'Introspecção'] },
];

/* ---------- estado */
const S = {
  catalog: null, health: null, healthStatus: 'checking', healthError: '', catalogStatus: 'loading', music: [], files: { narration: null, srt: null, script: null }, title: '',
  cfg: null, projects: [], projectId: null, project: null, logSeq: 0, scenesRev: -1, poll: null, tick: 0,
  skills: { selected: null },
  skillsVideoSelected: null,
  genOpen: {}, ytOpen: {}, previewText: 'A cidade que o mercado esqueceu há trinta anos',
  voice: { script: '', model: 's2.1-pro-free', voiceId: '', previewText: 'Olá! Esta é uma prévia da voz escolhida para narrar seu próximo vídeo.', job: null, busy: false, voices: [], langFilter: 'all' },
  keys: [], flowGallery: [], flowKind: 'image', flowQueue: [], flowProjects: [],
  groq: { file: null, scriptFile: null, job: null, jobs: [], busy: false, ready: false, guidance: null, poll: null, optionsReady: false },
  flowBlocks: { blocos: [], busy: false, ready: false, projectId: null, ratio: '16:9' },
  filesGroq: { job: null, busy: false, poll: null }, projectGroq: { job: null, busy: false, poll: null },
};
const TABS = [
  { id: 'files', label: 'Arquivos', ic: 'file' }, { id: 'media', label: 'Mídia', ic: 'image' },
  { id: 'style', label: 'Estilo', ic: 'palette' }, { id: 'audio', label: 'Áudio', ic: 'music' }, { id: 'out', label: 'Saída', ic: 'sliders' },
];
let CREATE = null;  // contexto do formulário de criação
let EDIT = null;    // contexto do editor de um projeto

function toast(msg) {
  const el = $('#toast'); el.textContent = msg; el.classList.add('show');
  clearTimeout(toast.t); toast.t = setTimeout(() => el.classList.remove('show'), 3600);
}
async function api(url, opts = {}) {
  const res = await fetch(url, opts);
  const ct = res.headers.get('content-type') || '';
  const body = ct.includes('json') ? await res.json() : await res.text();
  const onLogin = String(url).startsWith('/api/login');
  if (res.status === 401 && !onLogin) {
    $('#loginOverlay').hidden = false;
    throw new Error('Acesso protegido. Faça login para continuar.');
  }
  if (!res.ok) throw new Error((body && (body.detail || body.message)) || `Erro ${res.status}`);
  return body;
}
const jpost = (url, data, method = 'POST') => api(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data ?? {}) });
const jpostForm = (url, formData, method = 'POST') => api(url, { method, body: formData });

/* ---------- catálogo e padrões */
const tplById = id => S.catalog.templates.find(t => t.id === id) || S.catalog.templates[0];
const effStyle = cfg => deepMerge(tplById(cfg.template).style, cfg.style || {});
function defaultCfg() {
  const src = S.catalog.sources;
  const sources = src.filter(s => s.id !== 'youtube_frame' && (!s.needs_key || s.ready)).map(s => s.id);
  const t = S.catalog.templates[0];
  return {
    ratio: t.ratio, quality: '720p', sources, media_pref: 'mixed', video_percent: 50, max_video_seconds: 10,
    openrouter_model: 'google/gemini-2.5-flash', openrouter_vision_model: 'google/gemini-2.5-flash', semantic_scene_grouping: true, stock_only: true, per_source: 3, max_search_requests: 12, pacing: t.pacing, search_lang: 'auto', query_extra: '',
    template: t.id, style: {}, autopilot: false, auto_capcut: false,
    audio: { music_id: null, music_volume: t.audio.music_volume, narration_volume: 1, ducking: true, duck_level: 'medium', fade_in: 2, fade_out: 3, loop: true, normalize: false },
  };
}
const getVal = (ctx, p) => (p.startsWith('style.') ? deepGet(effStyle(ctx.cfg), p.slice(6)) : deepGet(ctx.cfg, p));
function setVal(ctx, p, v) {
  if (p.startsWith('style.')) deepSet(ctx.cfg.style, p.slice(6), v); else deepSet(ctx.cfg, p, v);
  $$(`[data-out="${p}"]`, ctx.container).forEach(o => { o.textContent = FMT[o.dataset.fmt || 'int'](v); });
  $$(`[data-color-path="${p}"]`, ctx.container).forEach(s => s.classList.toggle('on', String(s.dataset.val).toLowerCase() === String(v).toLowerCase()));
  if (p.startsWith('style.') || p === 'ratio') schedulePreview(ctx);
  if (ctx === CREATE) updateSummary();
}
const FMT = {
  pct: v => `${Math.round(v * 100)}%`, percent: v => `${Math.round(Number(v))}%`, size: v => (v * 100).toFixed(1), x2: v => Number(v).toFixed(2),
  int: v => String(Math.round(Number(v))), sec: v => `${Number(v)} s`, plain: v => String(v),
};

/* ---------- componentes de formulário */
function seg(ctx, path, options, type = 'str') {
  const cur = String(getVal(ctx, path));
  return `<div class="seg">${options.map(([v, l]) => `<button type="button" class="${String(v) === cur ? 'on' : ''}" data-set="${path}" data-val="${v}" data-type="${type}">${l}</button>`).join('')}</div>`;
}
function slider(ctx, path, label, min, max, step, fmt, hint = '') {
  const v = getVal(ctx, path) ?? min;
  return `<div class="slider"><div class="slider-top"><span class="lbl">${label}</span><output data-out="${path}" data-fmt="${fmt}">${FMT[fmt](v)}</output></div><input type="range" data-bind="${path}" min="${min}" max="${max}" step="${step}" value="${v}">${hint ? `<small class="hint">${hint}</small>` : ''}</div>`;
}
function toggle(ctx, path, title, sub = '') {
  const on = !!getVal(ctx, path);
  return `<label class="switch ${on ? 'on' : ''}"><input type="checkbox" data-bind="${path}" ${on ? 'checked' : ''}><span class="sw"></span><div><b>${title}</b>${sub ? `<small>${sub}</small>` : ''}</div></label>`;
}
function colorField(ctx, path, label, presets) {
  const cur = String(getVal(ctx, path) || '#FFFFFF');
  return `<div class="field"><span>${label}</span><div class="swatches">${presets.map(c => `<button type="button" class="sw-c ${c.toLowerCase() === cur.toLowerCase() ? 'on' : ''}" style="background:${c}" data-color-path="${path}" data-val="${c}" title="${c}"></button>`).join('')}<input type="color" data-bind="${path}" value="${cur.toLowerCase()}"></div></div>`;
}
const PALETTE = ['#FFFFFF', '#FFD60A', '#F6EAD0', '#4CF2C8', '#35E0FF', '#FF4D5E', '#F5B83D', '#FF8FD8'];

function savedVoicesHtml(v) {
  const filter = v.langFilter || 'all';
  const list = filter === 'all' ? SAVED_VOICES : SAVED_VOICES.filter(x => x.lang === filter);
  return list.map(x => {
    const isSelected = (v.voiceId || '').trim() === x.id;
    return `
    <div class="voice-card ${isSelected ? 'on' : ''}" data-voice-card="${x.id}">
      <div class="voice-card-head">
        <span style="font-size:18px">${x.flag}</span>
        <h5 style="margin:0 6px">${esc(x.title)}</h5>
        ${isSelected ? '<span class="pill ok" style="padding:2px 7px;font-size:10px">Em uso</span>' : ''}
      </div>
      <p>${esc(x.desc)}</p>
      <div class="tags">${x.tags.map(t => `<span class="tag">${esc(t)}</span>`).join('')}</div>
      <div class="voice-card-foot">
        <button type="button" class="btn ghost small" data-act-vprev="${x.id}">${ic('play')} Prévia</button>
        <button type="button" class="btn small ${isSelected ? 'primary' : 'ghost'}" data-act-vpick="${x.id}">${isSelected ? '✓ Selecionada' : 'Escolher'}</button>
      </div>
    </div>`;
  }).join('');
}

/* ---------- painéis */
const PANES = {
  files(ctx) {
    const f = S.files, v = S.voice;
    const card = (key, cls, icon, title, sub, req, accept) => `<label class="drop ${cls} ${f[key] ? 'filled' : ''}" data-file-card="${key}"><span class="req ${req ? '' : 'opt'}">${req ? 'OBRIGATÓRIO' : 'OPCIONAL'}</span><div class="ico">${ic(icon)}</div><strong>${title}</strong><small>${sub}</small><span class="picked">${f[key] ? '✓ ' + esc(f[key].name) : 'Clique ou arraste o arquivo'}</span><input type="file" data-file="${key}" accept="${accept}"></label>`;
    return `
    <div class="card">
      <div class="card-title"><div><h3>Qual é o vídeo?</h3><p>Dê um nome e envie a narração com as legendas sincronizadas.</p></div></div>
      <label class="field" style="margin-bottom:16px"><span>Nome do projeto</span><input type="text" id="titleInput" maxlength="100" placeholder="Ex.: A história da Zara" value="${esc(S.title)}"></label>
      <div class="grid3">
        ${card('narration', '', 'mic', 'Narração', 'MP3, WAV, M4A, AAC ou OGG', true, '.mp3,.wav,.m4a,.aac,.ogg,audio/*')}
        ${card('srt', 's', 'file', 'Legendas (.SRT)', 'Com os tempos da narração', true, '.srt')}
        ${card('script', 't', 'file', 'Roteiro original', 'TXT ou Markdown, para guardar com o projeto', false, '.txt,.md,text/plain')}
      </div>
    </div>
    ${filesGroqCard()}
    <details class="fold" id="voiceFold" ${v.job || v.script ? 'open' : ''}>
      <summary>${ic('mic')} Ainda não tem narração? Gere com Fish Audio <small>Cole o roteiro, escolha a voz e o MP3 sai pronto</small></summary>
      <div class="fold-body">
        <div class="voice-layout">
          <div class="stack">
            <label class="field"><span>Roteiro para narrar</span><textarea id="voiceScript" rows="8" placeholder="Cole aqui o roteiro completo…">${esc(v.script)}</textarea><div id="voiceStats" style="color:var(--muted);font-size:11px;margin-top:4px"></div><small>Roteiros longos são divididos em partes automaticamente. Tags como [whisper] ou [excited] funcionam no texto.</small></label>
            <div class="grid2">
              <label class="field"><span>Modelo</span><select id="fishModel"><option value="s2.1-pro-free">S2.1 Pro Free · avaliação</option><option value="s2.1-pro">S2.1 Pro · produção</option><option value="s2-pro">S2 Pro</option></select></label>
              <label class="field"><span>ID da voz (reference_id)</span><input type="text" id="fishVoiceId" placeholder="Cole o ID da voz" autocomplete="off" value="${esc(v.voiceId)}"></label>
            </div>
            <div class="row"><label class="field" style="flex:1;min-width:220px"><span>Suas vozes na conta</span><select id="fishVoiceSelect"><option value="">Selecione uma voz (opcional)</option>${v.voices.map(x => `<option value="${esc(x.id)}">${esc(x.title)} · ${esc(x.id.slice(0, 8))}</option>`).join('')}</select></label><button type="button" class="btn ghost small" id="loadFishVoices" style="align-self:end">${ic('refresh')} Carregar minhas vozes</button></div>
          </div>
          <aside class="voice-side">
            <div class="eyebrow">TESTE DE VOZ</div>
            <label class="field"><span>Frase de prévia</span><textarea id="voicePreviewText" rows="3">${esc(v.previewText)}</textarea></label>
            <button type="button" class="btn ghost" id="previewFishVoice">${ic('play')} Ouvir prévia</button>
            <audio id="fishPreviewAudio" controls hidden></audio>
            <div id="voiceStepControls" style="display:flex;gap:6px;margin-top:8px;flex-wrap:wrap" hidden>
              <button type="button" class="btn ghost small" id="pauseNarration">${ic('pause')} Pausar</button>
              <button type="button" class="btn ghost small" id="resumeNarration">${ic('play')} Retomar</button>
              <button type="button" class="btn ghost small" id="redoNarration">${ic('refresh')} Refazer</button>
            </div>
            <button type="button" class="btn primary" id="generateNarration">${ic('spark')} Gerar narração MP3</button>
            <div id="ttsProgress" hidden><div class="spread tiny" style="margin-bottom:6px"><span id="ttsMessage">Preparando…</span><span id="ttsPercent">0%</span></div><div class="track"><div id="ttsFill"></div></div></div>
            <div id="voiceBlocksBox" style="margin-top:10px;padding:10px;border:1px solid var(--line2);border-radius:10px;background:#0a1020;display:none;">
              <div class="spread tiny" style="margin-bottom:6px"><b id="voiceBlocksTitle">Gerando blocos…</b></div>
              <div id="voiceBlocksList" style="font-size:11px;color:var(--muted);max-height:200px;overflow-y:auto;"></div>
            </div>
            <audio id="genAudio" controls hidden></audio>
            <div class="row" id="genLinks" hidden><a class="text-btn" id="dlAudio" href="#">↓ MP3</a><a class="text-btn" id="dlSrt" href="#">↓ SRT estimado</a></div>
            <button type="button" class="btn" id="useNarration" disabled>${ic('check')} Usar no projeto</button>
            <p class="hint" id="fishStatus"></p>
          </aside>
        </div>

        <div class="saved-voices-box" style="margin-top:16px;padding-top:16px;border-top:1px solid var(--line)">
          <div class="spread" style="margin-bottom:10px;flex-wrap:wrap">
            <div>
              <div class="eyebrow">10 VOZES SALVAS & CONFIGURADAS</div>
              <h4 style="margin:2px 0 0;font:700 14.5px var(--head)">Selecione o narrador com 1 clique</h4>
            </div>
            <div class="seg" id="voiceFilterSeg">
              <button type="button" class="${(v.langFilter || 'all') === 'all' ? 'on' : ''}" data-vlang="all">Todas (10)</button>
              <button type="button" class="${v.langFilter === 'pt' ? 'on' : ''}" data-vlang="pt">🇧🇷 Português (4)</button>
              <button type="button" class="${v.langFilter === 'en' ? 'on' : ''}" data-vlang="en">🇺🇸 Inglês (5)</button>
              <button type="button" class="${v.langFilter === 'es' ? 'on' : ''}" data-vlang="es">🇪🇸 Espanhol (1)</button>
            </div>
          </div>
          <div class="saved-voices-grid" id="savedVoicesGrid">
            ${savedVoicesHtml(v)}
          </div>
        </div>

        <div class="note" style="margin-top:14px"><b>Sobre as legendas geradas:</b> o SRT sai com tempos estimados pela duração de cada trecho, não palavra por palavra. Revise ou troque o SRT se precisar de sincronia exata.</div>
      </div>
    </details>`;
  },

  media(ctx) {
    const c = S.catalog, cfg = ctx.cfg, editing = !!ctx.projectId;
    const group = (kind, title, icon) => {
      const list = c.sources.filter(s => s.kind === kind && s.id !== 'youtube_frame');
      return `<div class="src-group"><div class="src-head">${ic(icon)}<h4>${title}</h4></div><div class="src-grid">${list.map(s => {
        const on = cfg.sources.includes(s.id);
        const pill = s.id === 'youtube_frame'
          ? '<span class="pill key">opcional · confirme direitos</span>'
          : s.provider === 'Storyblocks' && !s.ready
            ? '<span class="pill key">falta API Key + Secret Key</span>'
            : !s.needs_key ? '<span class="pill free">sem chave</span>' : s.ready ? '<span class="pill ok">● chave ativa</span>' : `<span class="pill key">falta ${esc(s.env)}</span>`;
        return `<label class="src ${on ? 'on' : ''} ${s.ready ? '' : 'dis'}" data-src="${s.id}"><input type="checkbox" data-source="${s.id}" ${on ? 'checked' : ''}><span class="tick">${ic('check')}</span><b>${esc(s.provider)}</b><small>${esc(s.blurb)}</small>${pill}</label>`;
      }).join('')}</div></div>`;
    };
    const pacingDesc = { fast: 'Cenas de ~7 s. Muita troca de imagem, bom para Shorts.', balanced: 'Cenas de ~13 s. Equilíbrio para a maioria dos vídeos.', slow: 'Cenas de ~25 s. Calmo, para documentário longo.' };
    return `
    <div class="card">
      <div class="card-title"><div><h3>De onde vêm as imagens e vídeos?</h3><p>Marque os bancos que o robô deve pesquisar. As fontes sem chave funcionam de imediato.</p></div>
        <div class="quick"><button type="button" class="btn ghost small" data-quick="video">Só vídeos</button><button type="button" class="btn ghost small" data-quick="image">Só fotos</button><button type="button" class="btn ghost small" data-quick="ready">Todas disponíveis</button><button type="button" class="btn ghost small" data-quick="none">Limpar</button></div></div>
      ${group('video', 'Vídeos', 'film')}${group('image', 'Fotos e imagens', 'image')}
      <div class="grid2" style="margin-top:14px">
        <div>${toggle(ctx, 'stock_only', 'Desativar geração de mídia por IA', 'Mantém imagens e vídeos reais. YouTube continua como fonte opcional; a importação exige autorização e recorte sincronizado com o SRT.')}</div>
        <div class="note info">Cada bloco do SRT é uma unidade visual independente. A mídia escolhida começa no timestamp do bloco e acompanha a sequência da narração.</div>
      </div>
      <div class="card" style="margin-top:14px">
        <div class="card-title"><div><h3>Bancos alternativos</h3><p>Pesquise em bibliotecas menos repetidas sem raspar sites nem contornar seus limites.</p></div></div>
        <label class="field"><span>O que você está procurando?</span><input id="externalStockQuery" type="text" maxlength="120" placeholder="Ex.: vintage factory footage, old cars, city at night"></label>
        <div class="quick" style="margin-top:10px;flex-wrap:wrap">
          ${(c.external_sources || []).map(s => `<button type="button" class="btn ghost small" data-stock-search="${esc(s.id)}">${esc(s.name)} ↗</button>`).join('')}
        </div>
        <p class="hint" style="margin-top:10px">Esses botões abrem uma pesquisa externa limitada ao domínio de cada banco. A maioria não oferece API pública; por isso, o app não baixa nem copia arquivos automaticamente dessas páginas. Confira a licença antes de usar.</p>
      </div>
      <p class="hint" style="margin-top:14px">YouTube também funciona como banco de candidatos. O OpenRouter localiza o momento que combina com a fala do SRT, recorta até ${cfg.max_video_seconds || 10} s e salva o vídeo e um quadro do mesmo trecho. A importação exige confirmação de licença/autorização; o app não verifica direitos automaticamente.</p>
      <p class="hint" style="margin-top:8px"><b>Busca inteligente:</b> o robô traduz o conceito da cena, gera variações de termos e ordena os resultados por relevância, qualidade e popularidade. As consultas ficam em cache por 24 h para economizar chamadas.</p>
    </div>
    <div class="card">
      <div class="card-title"><div><h3>Como o robô escolhe</h3></div></div>
      <div class="grid2">
        <div class="field"><span>Preferência de tipo</span>${seg(ctx, 'media_pref', [['mixed', 'Misturar'], ['video', 'Preferir vídeo'], ['image', 'Preferir foto']])}<small>A preferência atua como desempate; a porcentagem abaixo define a distribuição automática.</small></div>
        ${slider(ctx, 'video_percent', 'Percentual de cenas em vídeo', 0, 100, 5, 'percent', 'O robô prioriza vídeos nas cenas com maior nota de movimento. O restante recebe imagens.')}
        ${slider(ctx, 'max_video_seconds', 'Duração máxima de cada clipe', 1, 10, 1, 'sec', 'O limite nunca ultrapassa 10 segundos. Clipes maiores são cortados pelo FFmpeg.')}
        ${slider(ctx, 'per_source', 'Opções por fonte e por cena', 1, 8, 1, 'int', 'Quantidade máxima de resultados que cada fonte pode retornar para uma cena.')}
        ${slider(ctx, 'max_search_requests', 'Máximo de consultas aos bancos por cena', 1, 24, 1, 'int', 'Limite total de chamadas fonte + consulta. Ex.: 12 permite até 12 pesquisas somando YouTube e bancos selecionados.')}
        <label class="field"><span>Idioma da busca</span><select data-bind="search_lang"><option value="auto" ${cfg.search_lang === 'auto' ? 'selected' : ''}>Automático (detecta pelo texto)</option><option value="pt" ${cfg.search_lang === 'pt' ? 'selected' : ''}>Português</option><option value="en" ${cfg.search_lang === 'en' ? 'selected' : ''}>Inglês</option></select><small>Os bancos retornam mais resultados em inglês.</small></label>
        <label class="field"><span>Palavras extras em toda busca</span><input type="text" data-bind="query_extra" maxlength="60" placeholder="ex.: cinematic, vintage, 4k" value="${esc(cfg.query_extra)}"><small>Entram no final de cada pesquisa para dar um tom ao vídeo.</small></label>
      </div>
      <div class="field" style="margin-top:16px">
        <span>Modelo OpenRouter para interpretar o roteiro</span>
        <div class="row"><input id="openrouterModelInput" list="openrouterModelList" type="text" data-bind="openrouter_model" maxlength="120" value="${esc(cfg.openrouter_model || 'google/gemini-2.5-flash')}" placeholder="Ex.: google/gemini-2.5-flash" style="flex:1"><button type="button" class="btn ghost small" id="loadOpenRouterModelsBtn">Carregar modelos</button></div>
        <datalist id="openrouterModelList"></datalist>
        <small>A chave OPENROUTER_API_KEY é cadastrada em Chaves de API. O modelo interpreta a fala e cria buscas específicas; se falhar, o app registra um aviso e usa fallback.</small>
        <label class="field" style="margin-top:12px"><span>Modelo OpenRouter para conferir imagens (visão)</span><input type="text" data-bind="openrouter_vision_model" maxlength="120" value="${esc(cfg.openrouter_vision_model || 'google/gemini-2.5-flash')}" placeholder="google/gemini-2.5-flash"><small>Escolha um modelo multimodal que aceite imagens para comparar as miniaturas com a narração.</small></label>
      </div>
      ${editing ? '<div class="note info" style="margin-top:14px">As fontes valem para <b>Buscar tudo de novo</b>. O ritmo das cenas só pode ser escolhido ao criar o projeto.</div>' : `
      <div class="field" style="margin-top:18px"><span>Ritmo das cenas</span><div class="choices">${Object.entries(c.pacing).map(([k, l]) => `<button type="button" class="choice ${cfg.pacing === k ? 'on' : ''}" data-set="pacing" data-val="${k}"><b>${l}</b><small>${pacingDesc[k] || ''}</small></button>`).join('')}</div></div>`}
    </div>`;

  },

  style(ctx) {
    const cfg = ctx.cfg, st = effStyle(cfg), sub = st.subtitles;
    const fonts = S.catalog.fonts;
    const motions = S.catalog.motions || {};
    const transitions = S.catalog.transitions || {};
    const effects = S.catalog.effects || {};
    const cta = st.cta || {};
    const ctaLang = cta.language && cta.language !== 'auto' ? cta.language : 'pt';
    const ctaText = (S.catalog.cta_texts || {})[ctaLang] || { main: 'SE INSCREVA NO CANAL', sub: 'e ative o sininho' };
    const classic = ['cut', 'fade', 'flash'].filter(k => transitions[k]);
    const modern = Object.keys(transitions).filter(k => !classic.includes(k));
    const tplSource = t => (t.source && t.source !== 'projeto' ? `<span class="tag tag-src">${t.source === 'github' ? 'GitHub' : esc(t.source)}</span>` : '');
    return `
    <div class="style-layout">
      <div>
        <div class="card-title" style="margin-bottom:12px"><div><h3>Escolha um estilo de vídeo</h3><p>Cada cartão é uma prévia real: o mesmo filtro, cor e legenda que o FFmpeg aplica no render.</p></div></div>
        <div class="tpl-grid">${S.catalog.templates.map(t => `
          <button type="button" class="tpl ${cfg.template === t.id ? 'on' : ''}" data-tpl="${t.id}">
            <div class="tpl-img"><div class="sk"></div><img loading="lazy" alt="" data-tpl-img="${t.id}"><span class="tpl-check">${ic('check')}</span></div>
            <div class="tpl-body"><b>${esc(t.name)}</b><small>${esc(t.tagline)}</small><div class="tags">${t.tags.map(x => `<span class="tag">${esc(x)}</span>`).join('')}${tplSource(t)}</div></div>
          </button>`).join('')}</div>
      </div>
      <div class="preview-box">
        <div class="card">
          <div class="card-title"><div><h3>Prévia com os seus ajustes</h3><p>${ctx.projectId ? 'Usa uma cena do seu projeto.' : 'Usa uma imagem de exemplo.'}</p></div></div>
          <div class="preview-frame" id="livePreview"><img alt="Prévia do estilo"><div class="spin"></div></div>
          <label class="field" style="margin-top:12px"><span>Texto da legenda de exemplo</span><input type="text" id="previewText" maxlength="120" value="${esc(S.previewText)}"></label>
        </div>
        <div>
          <details class="acc" open><summary>${ic('file')} Legenda</summary><div>
            ${toggle(ctx, 'style.subtitles.enabled', 'Mostrar legendas no vídeo', 'Desligue se vai legendar no CapCut')}
            <div class="field"><span>Modo</span>${seg(ctx, 'style.subtitles.mode', [['block', 'Frase inteira'], ['word', 'Palavra a palavra']])}</div>
            <div class="field"><span>Fonte</span><div class="fonts">${fonts.map(f => `<button type="button" class="font-chip ${sub.font === f.family ? 'on' : ''}" style="font-family:'${f.css}',sans-serif;${f.bold ? 'font-weight:700' : ''}" data-set="style.subtitles.font" data-val="${esc(f.family)}">Aa Legenda<small>${esc(f.label)}</small></button>`).join('')}</div></div>
            <div class="field"><span>Posição</span>${seg(ctx, 'style.subtitles.position', [['bottom', 'Embaixo'], ['lower_third', 'Terço inferior'], ['middle', 'Centro'], ['top', 'Topo']])}</div>
            <div class="field"><span>Animação</span>${seg(ctx, 'style.subtitles.animation', [['none', 'Nenhuma'], ['fade', 'Suave'], ['pop', 'Pop']])}</div>
            ${slider(ctx, 'style.subtitles.size', 'Tamanho', 0.025, 0.11, 0.001, 'size')}
            ${slider(ctx, 'style.subtitles.words', 'Palavras por tela (modo palavra a palavra)', 1, 5, 1, 'int')}
            ${colorField(ctx, 'style.subtitles.color', 'Cor do texto', PALETTE)}
            ${colorField(ctx, 'style.subtitles.highlight', 'Cor da palavra ativa', PALETTE)}
            ${colorField(ctx, 'style.subtitles.outline_color', 'Cor do contorno', ['#000000', '#2B1A0B', '#0B1B2B', '#3A0A12', '#FFFFFF'])}
            <div class="opt-row">${toggle(ctx, 'style.subtitles.uppercase', 'MAIÚSCULAS')}${toggle(ctx, 'style.subtitles.box', 'Caixa escura')}</div>
          </div></details>
          <details class="acc"><summary>${ic('film')} Imagem e movimento</summary><div>
            <label class="field"><span>Movimento nas fotos</span><select data-bind="style.motion">${Object.entries(motions).map(([v, o]) => `<option value="${v}" ${st.motion === v ? 'selected' : ''}>${esc(o.label)}</option>`).join('')}</select><small>${esc((motions[st.motion] || {}).hint || 'Movimento de câmera aplicado nas fotos do vídeo.')}</small></label>
            ${slider(ctx, 'style.motion_strength', 'Intensidade do movimento', 0.02, 0.3, 0.01, 'x2')}
            ${toggle(ctx, 'style.motion_video', 'Movimento também nos vídeos', 'Aplica o zoom/pan nos clipes de vídeo (só nas bordas, sem cortar o centro)')}
            <label class="field"><span>Transição entre cenas</span><select data-bind="style.transition"><optgroup label="Clássicas (por cena)">${classic.map(k => `<option value="${k}" ${st.transition === k ? 'selected' : ''}>${esc(transitions[k].label)}</option>`).join('')}</optgroup><optgroup label="Efeitos de transição (xfade)">${modern.map(k => `<option value="${k}" ${st.transition === k ? 'selected' : ''}>${esc(transitions[k].label)}</option>`).join('')}</optgroup></select><small>As transições modernas juntam as cenas com o filtro xfade do FFmpeg. As clássicas escurecem ou dão flash dentro da própria cena.</small></label>
            ${slider(ctx, 'style.transition_dur', 'Duração da transição', 0.05, 1.5, 0.05, 'x2', 'Transições muito longas encurtam cenas rápidas. 0,26 a 0,50 s funciona na maioria.')}
          </div></details>
          <details class="acc"><summary>${ic('sliders')} Efeitos de imagem</summary><div>
            ${Object.keys(effects).filter(k => k !== 'mirror').map(k => slider(ctx, `style.effects.${k}`, effects[k].label, 0, 1, 0.01, 'x2', esc(effects[k].hint || ''))).join('')}
            <div class="note info">Os efeitos são cumulativos. Comece com 0,10 a 0,25 para manter o vídeo elegante e legível.</div>
            ${toggle(ctx, 'style.effects.mirror', 'Espelhar a imagem', 'Inverte o vídeo horizontalmente (cuidado com textos e logotipos)')}
          </div></details>
          <details class="acc"><summary>${ic('palette')} Cor e acabamento</summary><div>
            ${slider(ctx, 'style.grade.saturation', 'Saturação', 0, 2, 0.05, 'x2')}
            ${slider(ctx, 'style.grade.contrast', 'Contraste', 0.5, 1.8, 0.02, 'x2')}
            ${slider(ctx, 'style.grade.brightness', 'Brilho', -0.3, 0.3, 0.01, 'x2')}
            ${slider(ctx, 'style.vignette', 'Vinheta', 0, 1, 0.05, 'x2')}
            ${slider(ctx, 'style.grain', 'Granulação de filme', 0, 30, 1, 'int')}
            <div class="opt-row">${toggle(ctx, 'style.grade.mono', 'Preto e branco')}${toggle(ctx, 'style.grade.sepia', 'Sépia')}</div>
            ${toggle(ctx, 'style.letterbox', 'Faixas de cinema', 'Barras pretas em cima e embaixo (só no 16:9)')}
          </div></details>
          <details class="acc"><summary>${ic('spark')} Destaques na tela</summary><div>
            ${toggle(ctx, 'style.overlays.verse_cards', 'Cartões de versículo', 'Quando a fala cita uma passagem (ex.: 1 Reis 11:4), aparece um cartão dourado com a referência')}
            ${toggle(ctx, 'style.overlays.callouts', 'Etiquetas de papel com apontamento', 'Uma palavra-chave de cada cena vira etiqueta com linha tracejada até a imagem')}
            ${toggle(ctx, 'style.overlays.topic_bar', 'Barra de tópico no canto', 'Resumo da cena no canto inferior esquerdo')}
          </div></details>
          <details class="acc"><summary>${ic('spark')} Sticker de inscrição</summary><div>
            ${toggle(ctx, 'style.cta.enabled', 'Mostrar sticker de inscrição', 'Um cartão com a chamada do canal no idioma do vídeo')}
            <div class="field"><span>Quando aparece</span>${seg(ctx, 'style.cta.position', [['start', 'Início'], ['middle', 'Meio'], ['end', 'Fim']])}</div>
            <div class="field"><span>Onde fica</span>${seg(ctx, 'style.cta.anchor', [['top', 'Topo'], ['bottom', 'Embaixo']])}</div>
            <div class="grid2">
              <label class="field"><span>Idioma da chamada</span><select data-bind="style.cta.language">${[['auto', 'Automático (pelo texto)'], ['pt', 'Português'], ['en', 'Inglês'], ['es', 'Espanhol']].map(([v, l]) => `<option value="${v}" ${(cta.language || 'auto') === v ? 'selected' : ''}>${l}</option>`).join('')}</select></label>
              <label class="field"><span>Estilo do sticker</span><select data-bind="style.cta.style">${Object.entries(S.catalog.cta_styles || {}).map(([v, o]) => `<option value="${v}" ${(cta.style || 'red') === v ? 'selected' : ''}>${esc(o.label)}</option>`).join('')}</select></label>
            </div>
            ${slider(ctx, 'style.cta.seconds', 'Tempo na tela', 1.5, 12, 0.5, 'sec')}
            <label class="field"><span>Texto personalizado (opcional)</span><input type="text" data-bind="style.cta.text" maxlength="80" value="${esc(cta.text || '')}" placeholder="${esc(`${ctaText.main} | ${ctaText.sub}`)}"><small>Use <b>principal | apoio</b> para trocar as duas linhas. Vazio = texto localizado automático (${esc(ctaText.main)}).</small></label>
            <div class="note info">O sticker é queimado no MP4 e também vira texto no projeto do CapCut. No modo automático, o idioma é detectado pelas falas; sem falas suficientes, usa português.</div>
          </div></details>
          <button type="button" class="btn ghost small" data-act="reset-style" style="margin-top:12px">${ic('refresh')} Voltar ao padrão do template</button>
        </div>
      </div>
    </div>`;
  },

  audio(ctx) {
    const a = ctx.cfg.audio;
    const rows = S.music.map(m => `<div class="track-row ${a.music_id === m.id ? 'on' : ''}" data-music="${m.id}"><span class="radio"></span><button type="button" class="mini" data-play="${m.id}" title="Ouvir">${ic('play')}</button><div class="meta"><b>${esc(m.name)}</b><small>${fmtTime(m.duration)} · ${m.size_mb} MB</small></div><button type="button" class="mini" data-del-music="${m.id}" title="Apagar da biblioteca">${ic('trash')}</button></div>`).join('');
    return `
    <div class="grid2" style="align-items:start">
      <div class="card">
        <div class="card-title"><div><h3>Música de fundo</h3><p>Suba suas trilhas uma vez e use em qualquer projeto.</p></div></div>
        <div class="music-list">
          <div class="track-row ${a.music_id ? '' : 'on'}" data-music=""><span class="radio"></span><div class="meta"><b>Sem música</b><small>Só a narração</small></div></div>
          ${rows}
        </div>
        <label class="dropzone" style="display:block;margin-top:12px" id="musicDrop">${ic('upload')}<b>Enviar música</b><small>Arraste ou clique · MP3, WAV, M4A, AAC ou OGG</small><input type="file" id="musicFile" accept=".mp3,.wav,.m4a,.aac,.ogg,audio/*" multiple></label>
        <p class="hint" style="margin-top:10px">Use músicas que você tenha direito de usar no YouTube.</p>
      </div>
      <div class="card">
        <div class="card-title"><div><h3>Mixagem</h3><p>Ajuste o volume e ouça um trecho de 20 s antes de montar.</p></div></div>
        <div class="mixer">
          ${slider(ctx, 'audio.music_volume', 'Volume da música', 0, 1, 0.01, 'pct', 'Entre 8% e 18% costuma deixar a voz clara.')}
          ${slider(ctx, 'audio.narration_volume', 'Volume da narração', 0, 2, 0.05, 'pct')}
          ${toggle(ctx, 'audio.ducking', 'Abaixar a música quando a voz fala', 'Compressão sidechain: a música "abre" nos silêncios')}
          <div class="field"><span>Força do efeito</span>${seg(ctx, 'audio.duck_level', [['low', 'Leve'], ['medium', 'Médio'], ['high', 'Forte']])}</div>
          <div class="opt-row">
            <label class="field"><span>Entrada gradual (s)</span><input type="number" min="0" max="15" step="0.5" data-bind="audio.fade_in" value="${a.fade_in}"></label>
            <label class="field"><span>Saída gradual (s)</span><input type="number" min="0" max="15" step="0.5" data-bind="audio.fade_out" value="${a.fade_out}"></label>
          </div>
          ${toggle(ctx, 'audio.loop', 'Repetir a música até o fim do vídeo')}
          ${toggle(ctx, 'audio.normalize', 'Normalizar o volume final', 'Ajusta para cerca de -14 LUFS, padrão do YouTube')}
          <div><button type="button" class="btn" data-act="mix-preview">${ic('play')} Ouvir prévia do mix</button><audio id="mixAudio" controls hidden style="width:100%;margin-top:10px"></audio></div>
        </div>
      </div>
    </div>`;
  },

  out(ctx) {
    const cfg = ctx.cfg;
    const shape = (w, h) => `<span class="shape" style="width:${w}px;height:${h}px"></span>`;
    return `
    <div class="grid2" style="align-items:start">
      <div class="card">
        <div class="card-title"><div><h3>Formato do vídeo</h3></div></div>
        <div class="choices">
          <button type="button" class="choice ${cfg.ratio === '16:9' ? 'on' : ''}" data-set="ratio" data-val="16:9">${shape(46, 26)}<b>16:9</b><small>YouTube e TV</small></button>
          <button type="button" class="choice ${cfg.ratio === '9:16' ? 'on' : ''}" data-set="ratio" data-val="9:16">${shape(26, 46)}<b>9:16</b><small>Shorts, Reels e TikTok</small></button>
          <button type="button" class="choice ${cfg.ratio === '1:1' ? 'on' : ''}" data-set="ratio" data-val="1:1">${shape(36, 36)}<b>1:1</b><small>Feed quadrado</small></button>
        </div>
        <div class="field" style="margin-top:16px"><span>Qualidade</span>${seg(ctx, 'quality', [['720p', '720p · rápido'], ['1080p', '1080p · mais pesado']])}<small>Servidores com pouca CPU demoram bem mais em 1080p. Valide o fluxo em 720p.</small></div>
      </div>
      <div class="card">
        <div class="card-title"><div><h3>Como o robô trabalha</h3></div></div>
        <div class="stack">
          ${toggle(ctx, 'autopilot', 'Piloto automático', 'Busca a mídia, escolhe as melhores cenas e já monta o vídeo, sem esperar a sua revisão')}
          ${toggle(ctx, 'auto_capcut', 'Gerar também o projeto do CapCut', 'No fim, empacota as cenas, a narração, a música e as legendas para abrir no CapCut')}
          <div class="note info">Sem o piloto automático, o robô para depois da busca para você revisar cada cena. Tudo pode ser trocado antes de montar.</div>
        </div>
      </div>
    </div>`;
  },
};

/* ---------- Groq (Whisper) · helpers de interface */
function groqStatusLabel(job) {
  if (!job) return 'pronto para usar';
  if (job.status === 'complete') return 'concluído';
  if (job.status === 'failed') return 'falhou';
  if (job.status === 'running') return job.message || 'transcrevendo';
  return 'na fila';
}
function groqProgressHtml(job, idPrefix = 'groq') {
  const pct = Math.max(0, Math.min(100, Math.round(job?.progress || 0)));
  return `<div id="${idPrefix}Progress" ${job ? '' : 'hidden'}>
    <div class="spread tiny" style="margin-bottom:6px"><span id="${idPrefix}ProgressMsg">${esc(job?.message || 'Preparando…')}</span><span id="${idPrefix}ProgressPct">${pct}%</span></div>
    <div class="track"><div id="${idPrefix}ProgressFill" style="width:${pct}%"></div></div>
    <small class="hint" id="${idPrefix}ProgressStage">${esc(job?.stage || '')}</small>
  </div>`;
}
function filesGroqCard() {
  const G = S.filesGroq, job = G.job;
  const ready = !!S.catalog?.groq?.ready;
  const done = job && job.status === 'complete';
  const failed = job && job.status === 'failed';
  const pill = !ready ? '<span class="pill key">falta GROQ_API_KEY</span>' : done ? '<span class="pill ok">● SRT sincronizado</span>' : failed ? '<span class="pill key">falhou</span>' : '<span class="pill free">● pronto</span>';
  const label = G.busy ? `<span class="spin"></span> Transcrevendo…` : done ? `${ic('refresh')} Transcrever de novo` : `${ic('mic')} Gerar SRT exato com Groq`;
  return `<div class="card groq-card" id="fileGroqCard">
    <div class="card-title"><div><h3>${ic('mic')} Legenda exata com Groq (Whisper)</h3><p>Transcreve a narração enviada acima, palavra por palavra, e preenche o campo de legendas (.SRT) automaticamente.</p></div>${pill}</div>
    <div class="note info"><b>Quando usar:</b> quando o SRT veio estimado (Fish Audio, por exemplo), quando há pausas e silêncios que quebram a sincronia, ou quando você quer legenda palavra a palavra. Pode ser usado sempre; a mesma narração é cacheada e não gasta cota duas vezes.</div>
    ${groqProgressHtml(job, 'fileGroq')}
    <div class="row" style="margin-top:12px;align-items:center">
      <button type="button" class="btn ${done ? 'ghost' : 'primary'}" data-act="groq-srt" ${(!ready || G.busy || !S.files.narration) ? 'disabled' : ''}>${label}</button>
      <span class="hint" id="fileGroqMsg">${failed ? esc(job.error || job.message || 'Falhou.') : !S.files.narration ? 'Envie a narração primeiro.' : done ? `SRT com ${job.cue_count || 0} blocos e ${job.word_count || 0} palavras.` : 'O roteiro original, se enviado, mantém o texto exato.'}</span>
    </div>
  </div>`;
}

/* ---------- abas e ligação dos campos */
function renderTabs(ctx) {
  const tabs = ctx === CREATE ? TABS : TABS.filter(t => t.id !== 'files');
  ctx.tabsEl.innerHTML = tabs.map((t, i) => {
    const ok = ctx === CREATE && ((t.id === 'files' && S.files.narration && S.files.srt) || (t.id === 'media' && ctx.cfg.sources.length));
    return `<button type="button" class="tab ${ctx.tab === t.id ? 'on' : ''} ${ok ? 'ok' : ''}" data-tab="${t.id}"><span class="n">${ok && ctx.tab !== t.id ? '✓' : i + 1}</span>${ic(t.ic)}${t.label}</button>`;
  }).join('');
}
function renderPane(ctx, keepScroll = false) {
  const y = window.scrollY, top = ctx.container.scrollTop;
  ctx.container.innerHTML = PANES[ctx.tab](ctx);
  renderTabs(ctx);
  afterPane(ctx);
  if (keepScroll) { window.scrollTo(0, y); ctx.container.scrollTop = top; }
}
function goTab(ctx, id) {
  ctx.tab = id; renderPane(ctx);
  if (ctx === CREATE) { updateCreateBar(); window.scrollTo({ top: 0, behavior: 'smooth' }); }
}
function afterPane(ctx) {
  const c = ctx.container;
  if (ctx.tab === 'files') { renderVoice(); }
  if (ctx.tab === 'style') {
    $$('[data-tpl-img]', c).forEach(img => {
      img.onload = () => img.previousElementSibling?.remove();
      img.src = previewUrl(ctx, { template: img.dataset.tplImg, overrides: {}, ratio: '16:9', text: 'O mercado esqueceu essa cidade' });
    });
    refreshPreview(ctx);
  }
}
function bindContext(ctx) {
  const c = ctx.container;
  c.addEventListener('input', e => {
    const el = e.target;
    if (el.dataset.bind) {
      let v = el.type === 'checkbox' ? el.checked : (el.type === 'range' || el.type === 'number') ? Number(el.value) : el.value;
      if (el.type === 'number' && Number.isNaN(v)) v = 0;
      setVal(ctx, el.dataset.bind, v);
    } else if (el.id === 'previewText') { S.previewText = el.value; schedulePreview(ctx); }
    else if (el.id === 'titleInput') { S.title = el.value; }
  });
  c.addEventListener('change', e => {
    const el = e.target;
    if (el.type === 'checkbox' && el.closest('.switch')) el.closest('.switch').classList.toggle('on', el.checked);
    if (el.dataset.source) {
      const id = el.dataset.source, meta = S.catalog.sources.find(s => s.id === id), box = el.closest('.src');
      if (el.checked && meta && !meta.ready) { el.checked = false; toast(`Configure ${meta.env} no arquivo .env (aba Chaves de API) para usar ${meta.provider}.`); return; }
      const set = new Set(ctx.cfg.sources); el.checked ? set.add(id) : set.delete(id);
      ctx.cfg.sources = [...set]; box.classList.toggle('on', el.checked);
      renderTabs(ctx); if (ctx === CREATE) updateSummary();
    } else if (el.dataset.file) { setFile(el.dataset.file, el.files[0]); }
    else if (el.id === 'musicFile') { uploadMusic([...el.files]); el.value = ''; }
  });
  c.addEventListener('click', e => {
    const t = e.target;
    const setBtn = t.closest('[data-set]');
    if (setBtn && c.contains(setBtn)) {
      const path = setBtn.dataset.set; let v = setBtn.dataset.val;
      if (setBtn.dataset.type === 'num') v = Number(v);
      $$(`[data-set="${path}"]`, c).forEach(b => b.classList.toggle('on', b === setBtn));
      setVal(ctx, path, v);
      if (path === 'ratio' && ctx === CREATE) return;
      return;
    }
    const sw = t.closest('[data-color-path]');
    if (sw) { const p = sw.dataset.colorPath; setVal(ctx, p, sw.dataset.val); const inp = $(`input[type=color][data-bind="${p}"]`, c); if (inp) inp.value = sw.dataset.val.toLowerCase(); return; }
    const tpl = t.closest('[data-tpl]'); if (tpl) return applyTemplate(ctx, tpl.dataset.tpl);
    const play = t.closest('[data-play]'); if (play) { e.stopPropagation(); return playMusic(play.dataset.play, play); }
    const del = t.closest('[data-del-music]'); if (del) { e.stopPropagation(); return deleteMusic(del.dataset.delMusic); }
    const mu = t.closest('[data-music]');
    if (mu) { ctx.cfg.audio.music_id = mu.dataset.music || null; $$('[data-music]', c).forEach(r => r.classList.toggle('on', r === mu)); return; }
    const stockSearch = t.closest('[data-stock-search]');
    if (stockSearch) {
      const query = c.querySelector('#externalStockQuery')?.value?.trim();
      if (!query) { toast('Digite o que deseja encontrar.'); return; }
      const source = (S.catalog.external_sources || []).find(s => s.id === stockSearch.dataset.stockSearch);
      if (source) window.open(source.search_prefix + encodeURIComponent(query), '_blank', 'noopener,noreferrer');
      return;
    }
    const q = t.closest('[data-quick]');
    if (q) {
      const all = S.catalog.sources, k = q.dataset.quick;
      ctx.cfg.sources = all.filter(s => s.ready && (k === 'ready' || s.kind === k)).map(s => s.id);
      if (k === 'none') ctx.cfg.sources = [];
      if (k !== 'none' && !ctx.cfg.sources.length) toast('Nenhuma fonte desse tipo está pronta. Configure uma chave no arquivo .env (aba Chaves de API).');
      renderPane(ctx, true); if (ctx === CREATE) updateSummary(); return;
    }
    const act = t.closest('[data-act]');
    if (act) {
      if (act.dataset.act === 'reset-style') { ctx.cfg.style = {}; renderPane(ctx, true); toast('Ajustes do template restaurados.'); }
      if (act.dataset.act === 'mix-preview') mixPreview(ctx, act);
      if (act.dataset.act === 'groq-srt') groqFromNarration(act);
      return;
    }
    const vc = t.closest('#voiceFold'); if (vc) voiceClick(t);
  });
  c.addEventListener('dragover', e => { const d = e.target.closest('.drop,.dropzone'); if (d) { e.preventDefault(); d.classList.add('over'); } });
  c.addEventListener('dragleave', e => e.target.closest('.drop,.dropzone')?.classList.remove('over'));
  c.addEventListener('drop', e => e.target.closest('.drop,.dropzone')?.classList.remove('over'));
  ctx.tabsEl.addEventListener('click', e => { const b = e.target.closest('[data-tab]'); if (b) goTab(ctx, b.dataset.tab); });
}

function applyTemplate(ctx, id) {
  const t = tplById(id), creating = ctx === CREATE;
  ctx.cfg.template = id; ctx.cfg.style = {};
  const bits = [t.name];
  if (creating) {
    ctx.cfg.ratio = t.ratio; ctx.cfg.pacing = t.pacing;
    ctx.cfg.audio.music_volume = t.audio.music_volume; ctx.cfg.audio.ducking = t.audio.ducking;
    bits.push(`formato ${t.ratio}`, `ritmo ${S.catalog.pacing[t.pacing].toLowerCase()}`);
  }
  renderPane(ctx, true); if (creating) updateSummary();
  toast(`Estilo aplicado: ${bits.join(' · ')}`);
}

/* ---------- prévia do estilo */
function previewUrl(ctx, { template, overrides, ratio, text }) {
  const p = new URLSearchParams({ template, ratio, text: text || S.previewText, overrides: JSON.stringify(overrides || {}) });
  if (ctx.projectId) p.set('project_id', ctx.projectId);
  return `/api/styles/preview?${p}`;
}
function schedulePreview(ctx) { clearTimeout(ctx.pt); ctx.pt = setTimeout(() => refreshPreview(ctx), 380); }
function refreshPreview(ctx) {
  const frame = $('#livePreview', ctx.container); if (!frame) return;
  const img = $('img', frame); frame.classList.add('busy');
  const next = new Image();
  next.onload = () => { img.src = next.src; frame.classList.remove('busy'); };
  next.onerror = () => { frame.classList.remove('busy'); };
  next.src = previewUrl(ctx, { template: ctx.cfg.template, overrides: ctx.cfg.style, ratio: ctx.cfg.ratio, text: S.previewText });
}

/* ---------- arquivos */
function setFile(key, file) {
  S.files[key] = file || null;
  const card = $(`[data-file-card="${key}"]`);
  if (card) { card.classList.toggle('filled', !!file); $('.picked', card).textContent = file ? '✓ ' + file.name : 'Clique ou arraste o arquivo'; }
  if (key === 'narration' && file && !S.title.trim()) { S.title = file.name.replace(/\.[^.]+$/, '').slice(0, 80); const t = $('#titleInput'); if (t) t.value = S.title; }
  const gcard = document.getElementById('fileGroqCard'); if (gcard) gcard.outerHTML = filesGroqCard();
  renderTabs(CREATE); updateCreateBar();
}

/* ---------- música */
const player = new Audio(); let playingId = null, playingBtn = null;
player.addEventListener('ended', () => { if (playingBtn) playingBtn.innerHTML = ic('play'); playingId = null; });
function playMusic(id, btn) {
  if (playingId === id && !player.paused) { player.pause(); btn.innerHTML = ic('play'); return; }
  if (playingBtn) playingBtn.innerHTML = ic('play');
  player.src = `/api/music/${id}/file`; player.play().catch(() => toast('Não consegui tocar esta música.'));
  playingId = id; playingBtn = btn; btn.innerHTML = ic('pause');
}
async function loadMusic() { try { S.music = await api('/api/music'); } catch { S.music = []; } }
async function uploadMusic(files) {
  for (const f of files) {
    const fd = new FormData(); fd.append('file', f);
    try { toast(`Enviando ${f.name}…`); const m = await api('/api/music', { method: 'POST', body: fd }); S.music.unshift(m); const ctx = activeCtx(); if (ctx && !ctx.cfg.audio.music_id) ctx.cfg.audio.music_id = m.id; toast(`Música adicionada: ${m.name}`); }
    catch (err) { toast(err.message); }
  }
  const ctx = activeCtx(); if (ctx && ctx.tab === 'audio') renderPane(ctx, true);
}
async function deleteMusic(id) {
  if (!confirm('Apagar esta música da biblioteca?')) return;
  try { await api(`/api/music/${id}`, { method: 'DELETE' }); S.music = S.music.filter(m => m.id !== id); [CREATE, EDIT].forEach(c => { if (c && c.cfg.audio.music_id === id) c.cfg.audio.music_id = null; }); const ctx = activeCtx(); if (ctx) renderPane(ctx, true); }
  catch (err) { toast(err.message); }
}
async function mixPreview(ctx, btn) {
  if (!ctx.cfg.audio.music_id) return toast('Escolha uma música para ouvir o mix.');
  const fd = new FormData(); fd.append('settings', JSON.stringify({ audio: ctx.cfg.audio }));
  if (ctx.projectId) fd.append('project_id', ctx.projectId);
  else if (S.files.narration) fd.append('narration', S.files.narration);
  else return toast('Envie a narração na aba Arquivos para testar o mix.');
  const old = btn.innerHTML; btn.disabled = true; btn.innerHTML = `<span class="spin"></span> Mixando…`;
  try {
    const res = await fetch('/api/mix-preview', { method: 'POST', body: fd });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `Erro ${res.status}`);
    const url = URL.createObjectURL(await res.blob()); const a = $('#mixAudio', ctx.container);
    if (a.dataset.u) URL.revokeObjectURL(a.dataset.u); a.dataset.u = url; a.src = url; a.hidden = false; a.play().catch(() => {});
  } catch (err) { toast(err.message); } finally { btn.disabled = false; btn.innerHTML = old; }
}
const activeCtx = () => (!$('#editor').hidden ? EDIT : (!$('#viewCreate').hidden ? CREATE : null));

/* ---------- narração Fish Audio */
function renderVoice() {
  const v = S.voice, $e = id => document.getElementById(id); if (!$e('voiceScript')) return;
  $e('fishModel').value = v.model;
  const sel = $e('fishVoiceSelect'); if (v.voiceId) sel.value = v.voiceId;
  $e('fishStatus').textContent = S.health?.fish_audio ? 'Fish Audio conectado. As chaves ficam só no servidor.' : 'Configure FISH_API_KEY no arquivo .env (aba Chaves de API) para ativar a geração.';
  const j = v.job;
  $e('ttsProgress').hidden = !j;
  if (j) {
    $e('ttsFill').style.width = `${j.progress || 0}%`;
    $e('ttsPercent').textContent = `${j.progress || 0}%`;
    $e('ttsMessage').textContent = j.message || 'Gerando…';
  }
  const done = !!j && j.status === 'complete';
  const failed = !!j && j.status === 'failed';
  const generating = !!j && (j.status === 'queued' || j.status === 'generating');
  const paused = !!j && j.paused;
  const stepControls = $e('voiceStepControls');
  if (stepControls) {
    stepControls.hidden = !(generating || failed);
    $e('pauseNarration').hidden = paused || failed || !generating;
    $e('resumeNarration').hidden = !paused;
    $e('redoNarration').hidden = !(failed || paused);
  }

  // Exibe os blocos reais processados pelo motor, sem disparar um job separado para cada parágrafo.
  const blocks = j && Array.isArray(j.blocks) ? j.blocks : [];
  const blocksBox = $e('voiceBlocksBox');
  const blocksTitle = $e('voiceBlocksTitle');
  const blocksList = $e('voiceBlocksList');
  if (blocksBox && blocksTitle && blocksList) {
    blocksBox.style.display = j ? 'block' : 'none';
    if (blocks.length) {
      const finished = blocks.filter(b => b.status === 'complete' || b.status === 'cached').length;
      blocksTitle.textContent = `${finished} de ${blocks.length} blocos prontos`;
      blocksList.innerHTML = blocks.map((b, i) => {
        const status = b.status === 'complete' || b.status === 'cached'
          ? `✓ Pronto (${fmtTime(b.duration || 0)})`
          : b.status === 'failed' ? `✗ ${esc(String(b.error || 'Falhou'))}`
          : 'Na fila / gerando…';
        const preview = esc(String(b.text || '').slice(0, 120));
        return `<div style="padding:6px 0;border-bottom:1px solid var(--line)"><div style="font-size:10px;color:var(--muted)">Bloco ${i + 1} · ${status}</div><div style="font-size:11px;color:#eaf2ff;white-space:normal">${preview}</div></div>`;
      }).join('');
    } else {
      blocksTitle.textContent = j ? (j.message || 'Preparando blocos…') : 'Aguardando geração…';
      blocksList.textContent = '';
    }
  }

  const au = $e('genAudio');
  const audioUrl = done ? (j.audio_url || '') : '';
  au.hidden = !done;
  if (audioUrl && au.getAttribute('src') !== audioUrl) {
    au.src = audioUrl;
    au.load();
  } else if (!audioUrl && au.hasAttribute('src')) {
    au.pause();
    au.removeAttribute('src');
    au.load();
  }
  $e('genLinks').hidden = !done;
  if (done) {
    $e('dlAudio').href = j.audio_download_url || j.audio_url;
    $e('dlSrt').href = j.srt_url;
  }
  $e('useNarration').disabled = !done;
  $e('generateNarration').disabled = v.busy || generating || paused;
  $e('generateNarration').innerHTML = v.busy || generating || paused
    ? `<span class="spin"></span> ${paused ? 'Pausado' : 'Gerando…'}`
    : `${ic('spark')} ${failed ? 'Tentar de novo' : 'Gerar narração MP3'}`;
  if (failed) $e('fishStatus').textContent = j.error || j.message || 'A geração falhou.';
  if (done) $e('fishStatus').textContent = `Áudio pronto · ${fmtAudioTime(j.duration)} · MP3 completo disponível para reprodução e download.`;
  if (paused) $e('fishStatus').textContent = 'Narração pausada. Clique em Retomar para continuar.';
}
document.addEventListener('input', e => {
  const id = e.target.id, v = S.voice;
  if (id === 'voiceScript') { v.script = e.target.value; updateVoiceStats(); }
  else if (id === 'fishModel') v.model = e.target.value;
  else if (id === 'fishVoiceId') v.voiceId = e.target.value.trim(); else if (id === 'voicePreviewText') v.previewText = e.target.value;
  else if (id === 'fishVoiceSelect') { v.voiceId = e.target.value; const i = document.getElementById('fishVoiceId'); if (i) i.value = v.voiceId; }
});

function updateVoiceStats() {
  const text = (S.voice && S.voice.script) || '';
  const words = text.trim() ? text.trim().split(/\s+/).length : 0;
  const estChunks = Math.max(1, Math.ceil(text.length / 7000));
  const el = document.getElementById('voiceStats');
  if (el) el.textContent = `${words} palavra${words !== 1 ? 's' : ''} · ${text.length} caractere${text.length !== 1 ? 's' : ''} · cerca de ${estChunks} trecho${estChunks !== 1 ? 's' : ''}`;
}
async function voiceClick(t) {
  const btn = t.closest('button'); if (!btn) return; const v = S.voice;
  if (btn.dataset.vlang) {
    v.langFilter = btn.dataset.vlang;
    $$('#voiceFilterSeg button').forEach(b => b.classList.toggle('on', b.dataset.vlang === v.langFilter));
    const grid = document.getElementById('savedVoicesGrid');
    if (grid) grid.innerHTML = savedVoicesHtml(v);
    return;
  }
  if (btn.dataset.actVpick) {
    const vid = btn.dataset.actVpick;
    v.voiceId = vid;
    const inp = document.getElementById('fishVoiceId');
    if (inp) inp.value = vid;
    const sel = document.getElementById('fishVoiceSelect');
    if (sel) sel.value = vid;
    const grid = document.getElementById('savedVoicesGrid');
    if (grid) grid.innerHTML = savedVoicesHtml(v);
    const chosen = SAVED_VOICES.find(x => x.id === vid);
    toast(`Voz selecionada: ${chosen ? chosen.title : vid}`);
    return;
  }
  if (btn.dataset.actVprev) {
    const vid = btn.dataset.actVprev;
    btn.disabled = true; const old = btn.innerHTML; btn.innerHTML = '<span class="spin"></span>';
    try {
      const res = await fetch('/api/fish/preview', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: v.previewText || 'Esta é uma prévia do narrador.', reference_id: vid, model: v.model })
      });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `Erro ${res.status}`);
      const a = document.getElementById('fishPreviewAudio');
      a.src = URL.createObjectURL(await res.blob()); a.hidden = false; a.play().catch(() => {});
    } catch (err) { toast(err.message); } finally { btn.disabled = false; btn.innerHTML = old; }
    return;
  }
  if (btn.id === 'loadFishVoices') {
    btn.disabled = true;
    try { v.voices = (await api('/api/fish/voices')).voices || []; renderPane(CREATE, true); toast(`${v.voices.length} vozes encontradas.`); } catch (err) { toast(err.message); btn.disabled = false; }
  } else if (btn.id === 'previewFishVoice') {
    if (!v.previewText.trim()) return toast('Digite uma frase para testar a voz.');
    btn.disabled = true; const old = btn.innerHTML; btn.innerHTML = '<span class="spin"></span> Gerando…';
    try {
      const res = await fetch('/api/fish/preview', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: v.previewText, reference_id: v.voiceId || null, model: v.model }) });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `Erro ${res.status}`);
      const a = document.getElementById('fishPreviewAudio'); a.src = URL.createObjectURL(await res.blob()); a.hidden = false; a.play().catch(() => {});
    } catch (err) { toast(err.message); } finally { btn.disabled = false; btn.innerHTML = old; }
  } else if (btn.id === 'pauseNarration') {
    btn.disabled = true;
    try { await api(`/api/narrations/${v.job.id}/pause`, { method: 'POST' }); v.job.paused = true; renderVoice(); toast('Narração pausada.'); }
    catch (err) { toast(err.message); } finally { btn.disabled = false; }
  } else if (btn.id === 'resumeNarration') {
    btn.disabled = true;
    try { await api(`/api/narrations/${v.job.id}/resume`, { method: 'POST' }); v.job.paused = false; renderVoice(); pollNarration(v.job.id); toast('Retomando narração…'); }
    catch (err) { toast(err.message); } finally { btn.disabled = false; }
  } else if (btn.id === 'redoNarration') {
    if (!confirm('Refazer a narração do zero? Os trechos já gerados serão descartados.')) return;
    btn.disabled = true;
    try { await api(`/api/narrations/${v.job.id}/redo`, { method: 'POST' }); v.job = { status: 'queued', progress: 0, message: 'Recomeçando…', paused: false }; v.busy = true; renderVoice(); pollNarration(v.job.id); }
    catch (err) { toast(err.message); v.busy = false; renderVoice(); } finally { btn.disabled = false; }
  } else if (btn.id === 'generateNarration') {
    const script = v.script.trim();
    if (!script) return toast('Cole o roteiro para narrar.');
    v.busy = true;
    v.job = { status: 'queued', progress: 0, message: 'Enviando o roteiro completo para o motor de narração…' };
    renderVoice();
    try {
      // Um único job recebe o roteiro inteiro; o motor divide, gera, une e valida o MP3.
      const job = await jpost('/api/narrations', {
        text: script,
        reference_id: v.voiceId || null,
        model: v.model
      });
      if (!job || !job.id) throw new Error('O servidor não retornou o identificador da narração.');
      v.job = { ...job, status: job.status || 'queued', message: job.message || 'Narração adicionada à fila.' };
      renderVoice();
      pollNarration(job.id);
    } catch (err) {
      v.busy = false;
      v.job = { status: 'failed', progress: 0, message: err.message, error: err.message };
      renderVoice();
      toast(err.message);
    }
  } else if (btn.id === 'useNarration') useNarration(btn);
}
async function pollNarration(id) {
  const v = S.voice;
  try {
    const j = await api(`/api/narrations/${id}`); v.job = j; renderVoice();
    if (j.status === 'complete') { v.busy = false; renderVoice(); toast('Narração pronta. Clique em "Usar no projeto".'); return; }
    if (j.status === 'failed') { v.busy = false; renderVoice(); return; }
    setTimeout(() => pollNarration(id), 2200);
  } catch (err) { v.busy = false; v.job = { status: 'failed', error: err.message }; renderVoice(); }
}

async function useNarration(btn) {
  const j = S.voice.job; if (!j || j.status !== 'complete') return;
  btn.disabled = true;
  try {
    const [a, s] = await Promise.all([fetch(j.audio_url), fetch(j.srt_url)]);
    if (!a.ok || !s.ok) throw new Error('Não consegui carregar o MP3 ou o SRT gerado.');
    setFile('narration', new File([await a.blob()], 'narracao_fish_audio.mp3', { type: 'audio/mpeg' }));
    setFile('srt', new File([await s.blob()], 'narracao_estimada.srt', { type: 'application/x-subrip' }));
    if (S.voice.script.trim()) setFile('script', new File([S.voice.script], 'roteiro.txt', { type: 'text/plain' }));
    toast('Narração e SRT adicionados ao projeto.'); $('[data-file-card="narration"]')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  } catch (err) { toast(err.message); } finally { btn.disabled = false; }
}

/* ---------- Groq · transcrição da narração no formulário */
function setText(id, value) { const el = document.getElementById(id); if (el) el.textContent = value; }
function setWidth(id, value) { const el = document.getElementById(id); if (el) el.style.width = value; }
function updateGroqProgressDom(prefix, job) {
  if (!job) return;
  const pct = Math.max(0, Math.min(100, Math.round(job.progress || 0)));
  setText(`${prefix}ProgressMsg`, job.message || 'Processando…');
  setText(`${prefix}ProgressPct`, `${pct}%`);
  setText(`${prefix}ProgressStage`, job.stage || '');
  setWidth(`${prefix}ProgressFill`, `${pct}%`);
}
async function fileScriptText() {
  let text = '';
  if (S.files.script) { try { text = await S.files.script.text(); } catch { text = ''; } }
  if (!text && S.voice.script.trim() && S.voice.job && S.voice.job.status === 'complete') text = S.voice.script;
  return text.trim();
}
async function groqFromNarration(btn) {
  const G = S.filesGroq;
  if (!S.files.narration) return toast('Envie a narração antes de gerar o SRT com Groq.');
  if (!S.catalog?.groq?.ready) return toast('Configure GROQ_API_KEY na tela de Chaves de API.');
  if (G.busy) return;
  G.busy = true; clearTimeout(G.poll);
  G.job = { status: 'queued', progress: 4, message: 'Enviando a narração para o Groq…', stage: 'upload' };
  const card = document.getElementById('fileGroqCard'); if (card) card.outerHTML = filesGroqCard();
  try {
    const script = await fileScriptText();
    const fd = new FormData();
    fd.append('audio', S.files.narration);
    fd.append('model', S.groq.model || 'whisper-large-v3-turbo');
    fd.append('language', S.groq.language || 'auto');
    fd.append('mode', S.groq.mode || 'auto');
    if (script) fd.append('script_text', script.slice(0, 200000));
    const res = await api('/api/transcribe', { method: 'POST', body: fd });
    G.job = { id: res.id, status: 'queued', progress: 6, message: 'Na fila do Groq…', stage: 'queue' };
    const c2 = document.getElementById('fileGroqCard'); if (c2) c2.outerHTML = filesGroqCard();
    pollFilesGroq(res.id);
  } catch (err) {
    G.busy = false;
    G.job = { status: 'failed', progress: 0, error: err.message, message: err.message };
    const c3 = document.getElementById('fileGroqCard'); if (c3) c3.outerHTML = filesGroqCard();
    toast(err.message);
  }
}
async function pollFilesGroq(id) {
  const G = S.filesGroq;
  try {
    const j = await api(`/api/transcribe/${id}`);
    G.job = j; updateGroqProgressDom('fileGroq', j);
    if (j.status === 'queued' || j.status === 'running') { G.poll = setTimeout(() => pollFilesGroq(id), 1800); return; }
    G.busy = false;
    const card = document.getElementById('fileGroqCard'); if (card) card.outerHTML = filesGroqCard();
    if (j.status === 'complete') {
      await applyGroqSrtToFiles(j);
      toast(`SRT sincronizado pelo Groq: ${j.cue_count || 0} blocos.`);
    } else {
      toast(j.error || j.message || 'A transcrição falhou.');
    }
  } catch (err) {
    G.busy = false;
    G.job = { status: 'failed', progress: 0, error: err.message, message: err.message };
    const card = document.getElementById('fileGroqCard'); if (card) card.outerHTML = filesGroqCard();
    toast(err.message);
  }
}
async function applyGroqSrtToFiles(job) {
  const res = await fetch(job.srt_url);
  if (!res.ok) throw new Error('Não consegui baixar o SRT gerado.');
  const base = (S.files.narration?.name || 'narracao').replace(/\.[^.]+$/, '');
  setFile('srt', new File([await res.blob()], `${base}_groq.srt`, { type: 'application/x-subrip' }));
}

/* ---------- Groq · tela completa */
function renderGroqOptions() {
  const c = S.catalog?.groq; if (!c) return;
  const modelSel = document.getElementById('groqModel'), langSel = document.getElementById('groqLanguage'), modeSel = document.getElementById('groqMode');
  if (!modelSel || modelSel.dataset.ready) return;
  modelSel.innerHTML = (c.models || []).map(m => `<option value="${esc(m.id)}" ${m.id === (S.groq.model || 'whisper-large-v3-turbo') ? 'selected' : ''}>${esc(m.label)}</option>`).join('');
  langSel.innerHTML = (c.languages || []).map(l => `<option value="${esc(l.id)}" ${l.id === 'auto' ? 'selected' : ''}>${esc(l.label)}</option>`).join('');
  modeSel.innerHTML = [['auto', 'Automático (recomendado)'], ['words', 'Palavra por palavra (transcrição)'], ['script', 'Manter o roteiro original (alinha os tempos)']].map(([v, l]) => `<option value="${v}" ${v === 'auto' ? 'selected' : ''}>${l}</option>`).join('');
  modelSel.dataset.ready = langSel.dataset.ready = modeSel.dataset.ready = '1';
  const chip = document.getElementById('groqLimitChip'); if (chip) chip.textContent = `até ${c.max_upload_mb} MB · ${c.max_active} por vez`;
  const g = c.guidance || {};
  const guide = document.getElementById('groqGuidance');
  if (guide) guide.innerHTML = `<div class="note info"><b>Pode usar em todos os projetos.</b> ${esc(g.always_note || 'O áudio é comprimido e dividido automaticamente; a mesma narração é cacheada.')}</div><ul class="groq-when">${(g.when || []).map(x => `<li>${esc(x)}</li>`).join('')}</ul>`;
  const facts = document.getElementById('groqFacts');
  if (facts && g.limits) facts.innerHTML = `<span class="chip">API ${g.limits.api_mb} MB</span><span class="chip">envio ${g.limits.upload_mb} MB</span><span class="chip">${g.limits.max_active} simultâneas</span><span class="chip">modelo ${esc(g.recommended_model || 'whisper-large-v3-turbo')}</span>`;
  modeSel.addEventListener('change', () => {
    const hint = document.getElementById('groqModeHint');
    if (hint) hint.textContent = modeSel.value === 'script' ? 'Mantém as palavras do roteiro; o Groq só encontra os tempos de cada bloco.' : modeSel.value === 'words' ? 'Usa a transcrição falada palavra por palavra, sem o roteiro.' : 'Automático escolhe o melhor modo conforme o roteiro e o áudio.';
  });
}
function renderGroqJobs() {
  const host = document.getElementById('groqJobsList'); if (!host) return;
  const jobs = S.groq.jobs || [];
  const count = document.getElementById('groqJobsCount'); if (count) count.textContent = `${jobs.length} tarefa${jobs.length === 1 ? '' : 's'}`;
  if (!jobs.length) { host.innerHTML = '<div class="empty"><b>Nenhuma transcrição ainda</b>Envie uma narração acima para gerar o primeiro SRT.</div>'; return; }
  host.innerHTML = jobs.map(j => {
    const done = j.status === 'complete';
    const cls = done ? 'ok' : j.status === 'failed' ? 'key' : 'free';
    const actions = done ? `<a class="btn ghost small" href="${esc(j.srt_url)}" download>${ic('download')} SRT</a><a class="btn ghost small" href="${esc(j.txt_url)}" download>TXT</a><a class="btn ghost small" href="${esc(j.json_url)}" download>JSON</a>${j.script_srt_url ? `<a class="btn ghost small" href="${esc(j.script_srt_url)}" download>SRT do roteiro</a>` : ''}<button type="button" class="btn primary small" data-groq-use="${esc(j.id)}">${ic('check')} Usar num novo vídeo</button>` : '';
    return `<article class="groq-job ${done ? 'done' : ''}">
      <div class="spread"><div class="groq-job-title"><b>${esc(j.name || 'Narração')}</b><small>${esc(j.model || '')} · ${esc(j.language || 'auto')} · ${new Date(j.created_at).toLocaleString('pt-BR')}</small></div><span class="pill ${cls}">● ${esc(done ? 'concluído' : j.status === 'failed' ? 'falhou' : j.status === 'running' ? 'transcrevendo' : 'na fila')}</span></div>
      <div class="groq-job-meta"><span class="chip">${j.word_count || 0} palavras</span><span class="chip">${j.cue_count || 0} blocos</span>${j.duration ? `<span class="chip">${fmtTime(j.duration)}</span>` : ''}${j.project_id ? '<span class="chip">projeto</span>' : ''}${j.cached ? '<span class="chip">cache</span>' : ''}${j.srt_mode ? `<span class="chip">${j.srt_mode === 'roteiro' ? 'roteiro alinhado' : 'transcrição'}</span>` : ''}</div>
      <div class="row">${actions}${j.status === 'failed' ? `<span class="hint">${esc(j.error || j.message || 'Falhou.')}</span>` : ''}</div>
    </article>`;
  }).join('');
}
function renderGroqProgress() {
  const j = S.groq.job, box = document.getElementById('groqProgress');
  if (box) box.hidden = !j;
  if (j) updateGroqProgressDom('groq', j);
  const btn = document.getElementById('groqSubmit');
  if (btn) {
    btn.disabled = !!S.groq.busy;
    btn.innerHTML = S.groq.busy ? '<span class="spin"></span> Transcrevendo…' : `${ic('spark')} Transcrever com Groq`;
  }
}
function renderGroqResult() {
  const j = S.groq.job, card = document.getElementById('groqResultCard'), box = document.getElementById('groqResultActions');
  if (!card || !box) return;
  const done = j && j.status === 'complete';
  card.hidden = !done;
  if (!done) return;
  const meta = document.getElementById('groqResultMeta');
  if (meta) meta.textContent = `${j.model} · ${j.language} · ${j.word_count || 0} palavras · ${j.cue_count || 0} blocos${j.srt_mode === 'roteiro' ? ' · roteiro alinhado' : j.srt_mode ? ' · transcrição' : ''}${j.cached ? ' · do cache' : ''}`;
  box.innerHTML = `<a class="btn primary" href="${esc(j.srt_url)}" download>${ic('download')} Baixar SRT</a><a class="btn ghost" href="${esc(j.txt_url)}" download>TXT</a><a class="btn ghost" href="${esc(j.json_url)}" download>JSON</a>${j.script_srt_url ? `<a class="btn ghost" href="${esc(j.script_srt_url)}" download>SRT do roteiro</a>` : ''}<button type="button" class="btn" data-groq-use="${esc(j.id)}">${ic('check')} Usar num novo vídeo</button>`;
  const preview = document.getElementById('groqPreview');
  if (preview) preview.textContent = String(j.text || '').slice(0, 1400) || '(sem prévia de texto)';
}
async function loadGroqView() {
  renderGroqOptions();
  const pill = document.getElementById('groqStatusPill');
  try {
    const res = await api('/api/transcribe');
    S.groq.ready = !!res.ready; S.groq.guidance = res.guidance; S.groq.jobs = res.jobs || [];
    if (pill) { pill.className = S.groq.ready ? 'pill ok' : 'pill key'; pill.textContent = S.groq.ready ? '● Groq conectado' : 'falta GROQ_API_KEY'; }
    renderGroqJobs();
    const active = S.groq.jobs.find(j => j.status === 'queued' || j.status === 'running');
    if (active) { S.groq.job = active; S.groq.busy = true; renderGroqProgress(); renderGroqResult(); clearTimeout(S.groq.poll); pollGroq(active.id); return; }
    if (!S.groq.job && S.groq.jobs[0]) { S.groq.job = S.groq.jobs[0]; }
    S.groq.busy = false; renderGroqProgress(); renderGroqResult();
  } catch (err) { toast(err.message); }
}
async function groqSubmit() {
  const g = S.groq;
  if (!g.file) return toast('Escolha o arquivo de áudio da narração.');
  if (!S.catalog?.groq?.ready) return toast('Configure GROQ_API_KEY na tela de Chaves de API.');
  g.busy = true; clearTimeout(g.poll);
  g.job = { status: 'queued', progress: 4, message: 'Enviando o áudio para o Groq…', stage: 'upload' };
  renderGroqProgress(); renderGroqResult();
  try {
    const fd = new FormData();
    fd.append('audio', g.file);
    fd.append('model', document.getElementById('groqModel')?.value || 'whisper-large-v3-turbo');
    fd.append('language', document.getElementById('groqLanguage')?.value || 'auto');
    fd.append('mode', document.getElementById('groqMode')?.value || 'auto');
    const text = (document.getElementById('groqScriptText')?.value || '').trim();
    if (text) fd.append('script_text', text.slice(0, 200000));
    if (g.scriptFile) fd.append('script', g.scriptFile);
    const res = await api('/api/transcribe', { method: 'POST', body: fd });
    g.job = { id: res.id, status: 'queued', progress: 6, message: 'Na fila do Groq…', stage: 'queue' };
    renderGroqProgress(); renderGroqResult(); pollGroq(res.id);
  } catch (err) {
    g.busy = false; g.job = { status: 'failed', progress: 0, error: err.message, message: err.message };
    renderGroqProgress(); toast(err.message);
  }
}
async function pollGroq(id) {
  const g = S.groq; clearTimeout(g.poll);
  try {
    const j = await api(`/api/transcribe/${id}`);
    g.job = j; renderGroqProgress(); renderGroqResult();
    if (j.status === 'queued' || j.status === 'running') { g.poll = setTimeout(() => pollGroq(id), 1900); return; }
    g.busy = false; renderGroqProgress();
    if (j.status === 'complete') {
      toast(`Transcrição concluída: ${j.word_count || 0} palavras.`);
      const list = await api('/api/transcribe'); g.jobs = list.jobs || []; renderGroqJobs();
    } else { toast(j.error || j.message || 'A transcrição falhou.'); }
  } catch (err) {
    g.busy = false; g.job = { status: 'failed', progress: 0, error: err.message, message: err.message };
    renderGroqProgress(); toast(err.message);
  }
}
async function groqUseNewVideo(jobId) {
  const j = (S.groq.jobs || []).find(x => x.id === jobId) || (S.groq.job?.id === jobId ? S.groq.job : null);
  if (!j || j.status !== 'complete') return toast('A transcrição ainda não está pronta.');
  try {
    const res = await fetch(j.srt_url); if (!res.ok) throw new Error('Não consegui baixar o SRT.');
    const base = (S.groq.file?.name || j.name || 'narracao').replace(/\.[^.]+$/, '');
    S.files.srt = new File([await res.blob()], `${base}_groq.srt`, { type: 'application/x-subrip' });
    if (S.groq.file) S.files.narration = S.groq.file;
    const text = (document.getElementById('groqScriptText')?.value || '').trim();
    if (S.groq.scriptFile) S.files.script = S.groq.scriptFile;
    else if (text) S.files.script = new File([text], 'roteiro.txt', { type: 'text/plain' });
    if (!S.title.trim() && S.files.narration) { S.title = S.files.narration.name.replace(/\.[^.]+$/, '').slice(0, 80); }
    showView('create'); goTab(CREATE, 'files');
    if (S.groq.file) toast('SRT do Groq e narração adicionados ao novo vídeo.');
    else toast('SRT do Groq adicionado. Envie a narração na aba Arquivos.');
  } catch (err) { toast(err.message); }
}

/* ---------- barra inferior do formulário */
function updateSummary() {
  const c = CREATE.cfg, t = tplById(c.template);
  const chips = [`${ic('palette')} ${esc(t.name)}`, `${esc(c.ratio)} · ${esc(c.quality)}`, `${c.sources.length} fonte${c.sources.length === 1 ? '' : 's'}`, c.audio.music_id ? `${ic('music')} ${Math.round(c.audio.music_volume * 100)}%` : 'sem música'];
  if (c.autopilot) chips.push(`${ic('bot')} piloto automático`);
  if (c.auto_capcut) chips.push('CapCut');
  $('#createSummary').innerHTML = chips.map(x => `<span class="chip">${x}</span>`).join('');
}
function updateCreateBar() {
  const i = TABS.findIndex(t => t.id === CREATE.tab), last = i === TABS.length - 1;
  $('#prevTab').disabled = i === 0; $('#nextTab').hidden = last; $('#submitProject').hidden = !last;
  $('#submitProject').disabled = !(S.files.narration && S.files.srt);
  $('#submitProject').title = $('#submitProject').disabled ? 'Envie a narração e o SRT na aba Arquivos' : '';
}
async function submitProject() {
  const err = $('#formError'); err.hidden = true;
  const bad = m => { err.textContent = m; err.hidden = false; };
  if (!S.files.narration || !S.files.srt) return bad('Envie a narração e o arquivo SRT na aba Arquivos.');
  if (!CREATE.cfg.sources.length) return bad('Marque pelo menos uma fonte de mídia na aba Mídia.');
  const title = (S.title || S.files.narration.name.replace(/\.[^.]+$/, '')).trim() || 'Novo vídeo';
  const fd = new FormData();
  fd.append('title', title); fd.append('settings', JSON.stringify(CREATE.cfg));
  fd.append('narration', S.files.narration); fd.append('subtitles', S.files.srt); if (S.files.script) fd.append('script', S.files.script);
  const btn = $('#submitProject'); btn.disabled = true; btn.innerHTML = '<span class="spin"></span> Enviando arquivos…';
  try {
    const p = await api('/api/projects', { method: 'POST', body: fd });
    toast('Projeto criado. O robô começou.');
    S.files = { narration: null, srt: null, script: null }; S.title = ''; S.voice.job = null;
    await loadProjects(); await openProject(p.id);
  } catch (e) { bad(e.message); }
  finally { btn.innerHTML = `${ic('bot')} Criar e iniciar o robô`; updateCreateBar(); }
}

/* ---------- projetos */
const STATUS = { queued: 'NA FILA', searching: 'BUSCANDO MÍDIA', ready: 'PRONTO PARA REVISAR', queued_render: 'NA FILA', rendering: 'MONTANDO', complete: 'CONCLUÍDO', failed: 'FALHOU' };
const isWorking = s => ['queued', 'searching', 'queued_render', 'rendering'].includes(s);
const badgeCls = s => (isWorking(s) ? 'work' : s === 'ready' ? 'ready' : s === 'complete' ? 'complete' : s === 'failed' ? 'failed' : '');
async function loadProjects() {
  try { S.projects = await api('/api/projects'); } catch { return; }
  $('#projectCount').textContent = S.projects.length; renderProjects();
}
function renderProjects() {
  const host = $('#projectList');
  if (!S.projects.length) { host.innerHTML = `<div class="empty" style="grid-column:1/-1"><b>Nenhum projeto ainda</b>Crie o primeiro em "Novo vídeo".</div>`; return; }
  host.innerHTML = S.projects.map(p => `<article class="pcard" data-open="${p.id}"><div class="spread"><span class="badge ${badgeCls(p.status)}">${STATUS[p.status] || 'PROCESSANDO'}</span><button class="icon-btn" data-del="${p.id}" title="Apagar">${ic('trash')}</button></div><h3>${esc(p.title)}</h3><div class="meta"><span class="chip">${esc(p.ratio || '16:9')}</span>${p.template ? `<span class="chip">${esc((S.catalog.templates.find(t => t.id === p.template) || {}).name || p.template)}</span>` : ''}<span class="chip">${p.scenes || 0} cenas</span>${p.duration ? `<span class="chip">${fmtTime(p.duration)}</span>` : ''}</div><div class="track"><div style="width:${Math.min(100, p.progress || 0)}%"></div></div><div class="foot"><small>${new Date(p.created_at).toLocaleString('pt-BR')}</small><small>${esc(((p.status === 'complete' ? 'Vídeo pronto para assistir e baixar' : p.status === 'failed' ? (p.error || p.message || 'Falhou.') : (p.message || '')) || '').slice(0, 44))}</small></div></article>`).join('');
}
$('#projectList').addEventListener('click', async e => {
  const del = e.target.closest('[data-del]');
  if (del) { e.stopPropagation(); if (!confirm('Apagar este projeto e todos os arquivos dele?')) return; try { await api(`/api/projects/${del.dataset.del}`, { method: 'DELETE' }); toast('Projeto apagado.'); loadProjects(); } catch (err) { toast(err.message); } return; }
  const open = e.target.closest('[data-open]'); if (open) openProject(open.dataset.open);
});

const VIEW_ID = { create: 'viewCreate', projects: 'viewProjects', project: 'viewProject', groq: 'viewGroq', keys: 'viewKeys', 'skills-video': 'viewSkillsVideo', 'media-library': 'viewMediaLibrary' };
function showView(name) {
  Object.keys(VIEW_ID).forEach(v => {
    const el = $('#' + VIEW_ID[v]);
    if (el) el.hidden = v !== name;
  });
  $$('.nav-item').forEach(b => b.classList.toggle('on', b.dataset.view === (name === 'project' ? 'projects' : name)));
  window.scrollTo(0, 0);
  if (name !== 'project') { stopPoll(); S.projectId = null; history.replaceState(null, '', location.pathname); }
  if (name === 'keys') loadKeysView();
  if (name === 'groq') loadGroqView();
  if (name === 'skills-video') loadSkillsVideoView();
  if (name === 'media-library') checkStoryblocksConnection();
}

/* ---------- Biblioteca de Mídia Storyblocks */
async function checkStoryblocksConnection() {
  const status = $('#storyblocksConnectionStatus');
  if (!status) return;
  status.textContent = 'Verificando...';
  status.className = 'chip';
  try {
    const res = await jpost('/api/keys/test', { key_id: 'storyblocks' });
    status.textContent = res.message || (res.ok ? 'Storyblocks conectado' : 'Falha na conexão');
    status.className = res.ok ? 'chip ok' : 'chip warn';
  } catch (err) {
    status.textContent = err.message;
    status.className = 'chip warn';
  }
}
function renderStoryblocksResults(items) {
  const host = $('#storyblocksResults');
  if (!host) return;
  if (!items.length) {
    host.innerHTML = '<div class="empty" style="grid-column:1/-1">Nenhum resultado encontrado. Tente outras palavras-chave.</div>';
    return;
  }
  host.innerHTML = items.map(item => {
    const isVideo = item.media_type === 'video';
    const preview = item.thumbnail || item.download_url || '';
    const media = isVideo
      ? (preview ? `<video src="${esc(item.download_url || preview)}" poster="${esc(preview)}" controls muted preload="none" playsinline></video>` : '<div class="empty">Prévia indisponível</div>')
      : `<img src="${esc(preview)}" alt="${esc(item.title || 'Imagem Storyblocks')}" loading="lazy">`;
    return `
      <article class="media-result-card">
        <div class="media-result-preview">${media}<span class="media-type-tag">${isVideo ? 'VÍDEO' : 'IMAGEM'}</span></div>
        <div class="media-result-body">
          <strong title="${esc(item.title || '')}">${esc(item.title || 'Mídia Storyblocks')}</strong>
          <div class="media-result-meta">${item.duration ? fmtTime(item.duration) + ' · ' : ''}${item.width && item.height ? esc(item.width + ' × ' + item.height) : 'Prévia disponível'}</div>
          <div class="media-result-actions"><a class="btn small primary" href="${esc(item.source_url || 'https://www.storyblocks.com')}" target="_blank" rel="noopener noreferrer">Ver licença e download</a></div>
        </div>
      </article>`;
  }).join('');
}
async function searchStoryblocks(event) {
  event?.preventDefault();
  const query = ($('#storyblocksQuery')?.value || '').trim();
  if (query.length < 2) return toast('Digite pelo menos dois caracteres.');
  const host = $('#storyblocksResults'), btn = $('#storyblocksSearchBtn'), meta = $('#storyblocksResultMeta');
  if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spin"></span> Pesquisando...'; }
  if (host) host.innerHTML = '<div class="empty" style="grid-column:1/-1"><span class="spin"></span><br>Buscando no Storyblocks...</div>';
  if (meta) meta.textContent = 'Pesquisando: ' + query;
  try {
    const result = await jpost('/api/storyblocks/search', {
      query,
      media_type: $('#storyblocksType')?.value || 'video',
      orientation: $('#storyblocksOrientation')?.value || 'landscape',
      per: Number($('#storyblocksPer')?.value || 12),
      project_id: S.projectId || 'faceless-media-library',
    });
    renderStoryblocksResults(result.results || []);
    if (meta) meta.textContent = (result.total || 0) + ' resultado(s) para “' + result.query + '”.';
  } catch (err) {
    if (host) host.innerHTML = '<div class="form-error" style="grid-column:1/-1">' + esc(err.message) + '</div>';
    if (meta) meta.textContent = 'A pesquisa não foi concluída.';
  } finally {
    if (btn) { btn.disabled = false; btn.innerHTML = ic('search') + ' Pesquisar'; }
  }
}
$('#storyblocksSearchForm')?.addEventListener('submit', searchStoryblocks);
$('#storyblocksCheckBtn')?.addEventListener('click', checkStoryblocksConnection);

/* ---------- Modelos OpenRouter */
async function loadOpenRouterModels() {
  const btn = $('#loadOpenRouterModelsBtn');
  const list = $('#openrouterModelList');
  if (btn) { btn.disabled = true; btn.textContent = 'Carregando…'; }
  try {
    const data = await api('/api/openrouter/models');
    if (!list) return;
    list.innerHTML = (data.models || []).map(model => `<option value="${esc(model.id)}">`).join('');
    toast((data.models || []).length + ' modelos OpenRouter carregados.');
  } catch (err) {
    toast('Não foi possível carregar modelos: ' + err.message);
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Carregar modelos'; }
  }
}
document.addEventListener('click', event => {
  if (event.target.closest('#loadOpenRouterModelsBtn')) loadOpenRouterModels();
});

/* ---------- View Skills de Vídeo (Estilos de Edição) */

async function loadSkillsVideoView() {
  const list = $('#skillsVideoList');
  const count = $('#skillsVideoCount');
  try {
    const [res, projetos] = await Promise.all([
      api('/api/skills-video'),
      api('/api/projects').catch(() => []),
    ]);
    const items = res.skills || [];
    const selProj = $('#skillsVideoProjectSelect');
    if (selProj) {
      const atual = selProj.value;
      selProj.innerHTML = '<option value="">Salvar como estilo padrão do estúdio</option>' +
        (projetos || []).map(p => `<option value="${esc(p.id)}" ${p.id === atual ? 'selected' : ''}>${esc(p.title || 'Sem título')} (${p.scenes || 0} cenas · ${esc(String(p.id).slice(0, 6))})</option>`).join('');
    }
    if (count) count.textContent = items.length + ' estilo' + (items.length === 1 ? '' : 's');
    if (!items.length) {
      list.innerHTML = '<div class="empty">Nenhum estilo encontrado.</div>';
      return;
    }
    list.innerHTML = items.map(s => {
      const estilo = s.estilo || {};
      const cor = estilo.cor_primaria || '#6366F1';
      const motionLabel = (S.catalog?.motions || {})[estilo.motion]?.label || estilo.motion || 'Parado';
      const transLabel = (S.catalog?.transitions || {})[estilo.transition]?.label || estilo.transition || 'Corte seco';
      const selecionado = S.skillsVideoSelected === s.id;
      return `
        <article class="skill-video-card ${selecionado ? 'selected' : ''}" data-skill-id="${esc(s.id)}" role="button" tabindex="0">
          <div class="skill-card-left">
            <div class="skill-card-title" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(s.name)}<span class="style-badge">${esc(s.categoria || '')}</span></div>
            <div class="skill-card-cat">${esc(motionLabel)} · ${esc(transLabel)}</div>
            <div class="skill-card-desc">${esc(s.descricao || '')}</div>
          </div>
          <div class="skill-card-actions">
            <span class="chip" title="Cor primária: ${esc(estilo.cor_primaria || '#6366F1')}" style="background:${cor}"></span>
            <span class="chip" style="background:var(--panel3);color:var(--dim)">${selecionado ? 'Selecionado' : 'Escolher'}</span>
          </div>
        </article>
      `;
    }).join('');
    S.skillsVideoItems = items;
    const motionBtn = $('#motionRenderBtn');
    if (motionBtn) motionBtn.disabled = !S.skillsVideoSelected;
    renderSkillVideoPreview();
  } catch (err) {
    list.innerHTML = '<div class="empty">Erro ao carregar estilos: ' + esc(err.message) + '</div>';
  }
}

/* ---------- Prévia do estilo de vídeo selecionado */
function selectedSkillStyle() {
  return (S.skillsVideoItems || []).find(s => s.id === S.skillsVideoSelected) || null;
}

function skillsVideoProjectId() {
  return $('#skillsVideoProjectSelect')?.value || null;
}

function skillPreviewUrl(estilo) {
  const p = new URLSearchParams({ ratio: '16:9', text: 'O mercado esqueceu essa cidade', overrides: JSON.stringify(estilo || {}) });
  const projectId = skillsVideoProjectId();
  if (projectId) p.set('project_id', projectId);
  return '/api/styles/preview?' + p;
}

function renderSkillVideoPreview() {
  const skill = selectedSkillStyle();
  if (!skill) return;
  const estilo = skill.estilo || {};
  const motionLabel = (S.catalog?.motions || {})[estilo.motion]?.label || estilo.motion || 'Parado';
  const transLabel = (S.catalog?.transitions || {})[estilo.transition]?.label || estilo.transition || 'Corte seco';
  const label = $('#skillsVideoSelectedLabel');
  if (label) label.textContent = `${skill.name} · ${skill.categoria || 'estilo'}`;
  const colorChip = $('#skillsVideoColorChip');
  if (colorChip) colorChip.style.background = estilo.cor_primaria || '#6366F1';
  const motionChip = $('#skillsVideoMotionChip');
  if (motionChip) motionChip.textContent = 'Movimento: ' + ((S.catalog?.motions || {})[estilo.motion]?.label || estilo.motion || 'Parado');
  const transChip = $('#skillsVideoTransitionChip');
  if (transChip) transChip.textContent = 'Transição: ' + ((S.catalog?.transitions || {})[estilo.transition]?.label || estilo.transition || 'Corte seco');
  const frame = $('#skillsVideoPreviewBox');
  if (!frame) return;
  frame.className = 'skills-preview-frame';
  frame.innerHTML = `<img alt="Prévia do estilo ${esc(skill.name)}" style="width:100%;height:100%;object-fit:cover">`;
  const img = $('img', frame);
  if (img) img.src = skillPreviewUrl(estilo);
  const chipContainer = $('#skillsVideoPreviewBox')?.parentElement?.querySelector('.skills-preview-chip');
  if (chipContainer) chipContainer.remove();
  const chips = document.createElement('div');
  chips.className = 'skills-preview-chip';
  chips.innerHTML = `
    <span class="chip" style="background:${estilo.cor_primaria || '#6366F1'}" title="Cor primária"></span>
    <span class="chip" style="background:var(--panel3);color:var(--dim)">${motionLabel}</span>
    <span class="chip" style="background:var(--panel3);color:var(--dim)">${transLabel}</span>
  `;
  frame.parentElement.appendChild(chips);
  const motionBtn = $('#motionRenderBtn');
  if (motionBtn) motionBtn.disabled = false;
}

async function renderMotionScene() {
  const skill = selectedSkillStyle();
  if (!skill) return;
  const estilo = skill.estilo || {};
  const btn = $('#motionRenderBtn');
  const resultBox = $('#motionRenderResult');
  const textInp = $('#motionSceneText');
  const durInp = $('#motionSceneDuration');
  const text = textInp?.value || skill.name;
  const duration = parseFloat(durInp?.value || '5') || 5;
  btn.disabled = true;
  btn.innerHTML = '<span class="spin"></span> Renderizando…';
  resultBox.innerHTML = '';
  try {
    const res = await jpost('/api/motion/render', {
      text,
      duration,
      width: 1280,
      height: 720,
      cor_primaria: estilo.cor_primaria || '#2F6FED',
      estilo: estilo.id || 'documentario',
    });
    if (res.ok) {
      resultBox.innerHTML = `<div style="color:var(--green);font-size:12px">✓ Cena renderizada!</div><video src="${res.url}" controls width="100%" style="margin-top:8px;border-radius:8px;background:#0a1020"></video>`;
      toast('Cena Remotion renderizada com sucesso!');
    } else {
      throw new Error(res.detail || 'Erro ao renderizar');
    }
  } catch (err) {
    resultBox.innerHTML = `<div style="color:var(--red);font-size:12px">✗ ${err.message}</div>`;
    toast(err.message);
  } finally {
    btn.disabled = false;
    btn.innerHTML = ic('spark') + ' Renderizar Cena Remotion';
  }
}

async function applySkillStyle(skillId) {
  const btn = $('#skillsVideoApplyBtn');
  if (!btn) return;
  const restore = () => { btn.disabled = false; btn.innerHTML = ic('check') + ' Aplicar Estilo Selecionado'; };
  btn.disabled = true;
  btn.innerHTML = '<span class="spin"></span> Aplicando…';
  try {
    const res = await jpost('/api/skills-video/apply', { skill_id: skillId, project_id: skillsVideoProjectId() });
    if (res.ok) {
      S.skillsVideoSelected = skillId;
      loadSkillsVideoView();
      const destino = res.applied_to === 'project'
        ? `ao projeto selecionado (${res.skill_name || skillId})`
        : `como estilo padrão do estúdio (${res.skill_name || skillId})`;
      $('#skillsVideoResult').innerHTML = '<div style="color:var(--green);font-size:12px">✓ Estilo aplicado ' + esc(destino) + '. Abra um projeto e confira na aba Estilo.</div>';
      restore();
      const previewBtn = $('#skillsVideoPreviewBtn');
      if (previewBtn) previewBtn.disabled = false;
      toast(res.applied_to === 'project' ? 'Estilo aplicado ao projeto!' : 'Estilo salvo como padrão do estúdio!');
    } else {
      throw new Error(res.detail || 'Erro ao aplicar estilo');
    }
  } catch (err) {
    toast(err.message);
    restore();
  }
}

/* ---------- Listeners View Skills de Vídeo */
$('#viewSkillsVideo')?.addEventListener('click', async e => {
  const card = e.target.closest('[data-skill-id]');
  if (card) {
    e.stopPropagation();
    S.skillsVideoSelected = card.dataset.skillId;
    loadSkillsVideoView();
    renderSkillVideoPreview();
    return;
  }
  if (e.target.closest('#skillsVideoRefreshBtn')) return loadSkillsVideoView();
  if (e.target.closest('#skillsVideoApplyBtn')) {
    if (!S.skillsVideoSelected) return toast('Selecione um estilo primeiro.');
    await applySkillStyle(S.skillsVideoSelected);
    return;
  }
  if (e.target.closest('#motionRenderBtn')) {
    if (!S.skillsVideoSelected) return toast('Selecione um estilo primeiro.');
    await renderMotionScene();
    return;
  }
});
$('#viewSkillsVideo')?.addEventListener('change', e => {
  if (e.target.id === 'skillsVideoProjectSelect' && S.skillsVideoSelected) renderSkillVideoPreview();
});

/* ---------- tela de chaves e testes ---------- */
async function loadSystemDiagnostics() {
  const btn = $('#runSystemDoctorBtn');
  const status = $('#doctorStatus');
  const summary = $('#doctorSummary');
  const results = $('#doctorResults');
  if (!results) return;
  if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spin"></span> Verificando…'; }
  if (status) { status.className = 'chip'; status.textContent = 'Em execução'; }
  if (summary) summary.textContent = 'Verificando dependências locais. Nenhuma chave será exibida ou enviada.';
  results.innerHTML = '<div class="empty">Executando verificações…</div>';
  try {
    const res = await api('/api/doctor');
    const labels = { ok: 'OK', warning: 'ATENÇÃO', error: 'ERRO' };
    const icons = { ok: '✓', warning: '!', error: '×' };
    if (status) {
      status.className = res.ok ? 'chip ok' : 'chip warn';
      status.textContent = res.ok ? 'Essencial pronto' : 'Precisa de atenção';
    }
    if (summary) {
      const c = res.counts || {};
      summary.textContent = `${res.summary || 'Diagnóstico concluído'} · ${c.ok || 0} OK · ${c.warning || 0} avisos · ${c.error || 0} erros`;
    }
    results.innerHTML = (res.checks || []).map(item => {
      const state = ['ok', 'warning', 'error'].includes(item.status) ? item.status : 'warning';
      const label = labels[state];
      const icon = icons[state];
      return `<article class="doctor-check status-${state}">
        <div class="doctor-check-head"><b>${esc(item.label || item.id || 'Verificação')}</b><span class="doctor-state">${icon} ${label}</span></div>
        <p>${esc(item.detail || '')}</p>
      </article>`;
    }).join('') || '<div class="empty">Nenhuma verificação foi retornada.</div>';
  } catch (err) {
    if (status) { status.className = 'chip warn'; status.textContent = 'Falha'; }
    if (summary) summary.textContent = 'Não foi possível executar o diagnóstico.';
    results.innerHTML = `<div class="form-error">${esc(err.message)}</div>`;
  } finally {
    if (btn) { btn.disabled = false; btn.innerHTML = `${ic('refresh')} Executar diagnóstico`; }
  }
}

async function loadKeysView() {
  const grid = $('#keysCardsGrid');
  if (!grid) return;
  grid.innerHTML = '<div class="empty" style="grid-column:1/-1"><span class="spin" style="margin-bottom:8px"></span><br>Carregando chaves de API...</div>';
  try {
    const res = await api('/api/keys');
    S.keys = res.keys || [];
    renderKeysGrid();
  } catch (err) {
    grid.innerHTML = `<div class="form-error" style="grid-column:1/-1">Falha ao carregar chaves: ${esc(err.message)}</div>`;
  }
  try {
    await loadFlowAgentConfig();
  } catch { /* sem servidor flow agent configurado */ }
}

async function runSystemDoctor() {
  const button = $('#runSystemDoctorBtn');
  const status = $('#doctorStatus');
  const summary = $('#doctorSummary');
  const host = $('#doctorResults');
  if (!button || !host) return;
  button.disabled = true;
  button.innerHTML = '<span class="spin"></span> Verificando...';
  if (status) { status.textContent = 'Executando'; status.className = 'chip'; }
  if (host) host.innerHTML = '<div class="empty">Verificando componentes locais...</div>';
  try {
    const result = await api('/api/doctor');
    const counts = result.counts || {};
    if (status) {
      status.textContent = result.ok ? 'Essencial pronto' : 'Atenção necessária';
      status.className = result.ok ? 'chip ok' : 'chip warn';
    }
    if (summary) summary.textContent = result.summary || 'Verificação concluída.';
    const labels = { ok: 'OK', warning: 'AVISO', error: 'ERRO' };
    host.innerHTML = (result.checks || []).map(item => `
      <div class="doctor-check status-${esc(item.status)}">
        <div class="doctor-check-head"><b>${esc(item.label)}</b><span class="doctor-state">${labels[item.status] || 'INFO'}</span></div>
        <p>${esc(item.detail)}</p>
      </div>`).join('') || '<div class="empty">Nenhuma verificação foi retornada.</div>';
  } catch (err) {
    if (status) { status.textContent = 'Falha'; status.className = 'chip warn'; }
    if (summary) summary.textContent = err.message || 'Não foi possível executar o diagnóstico.';
    host.innerHTML = '<div class="form-error">Não foi possível consultar o diagnóstico.</div>';
  } finally {
    button.disabled = false;
    button.innerHTML = ic('refresh') + ' Executar diagnóstico';
  }
}
document.addEventListener('click', event => {
  if (event.target.closest('#runSystemDoctorBtn')) runSystemDoctor();
});

function renderKeysGrid() {
  const grid = $('#keysCardsGrid');
  if (!grid || !S.keys) return;
  grid.innerHTML = S.keys.map(k => {
    const statusPill = k.configured
      ? '<span class="pill ok">● Chave Ativa</span>'
      : k.placeholder
      ? '<span class="pill key">⚠️ Exemplo de texto</span>'
      : '<span class="pill off">○ Não configurada</span>';

    return `
    <article class="pcard key-card" data-key-id="${esc(k.id)}" data-key-env="${esc(k.env)}">
      <div class="spread">
        <div>
          <span class="chip" style="font-size:10px">${esc(k.category)}</span>
          <h3 style="margin-top:6px">${esc(k.name)}</h3>
        </div>
        ${statusPill}
      </div>
      <p class="hint">${esc(k.blurb)}</p>
      ${k.link ? `<a href="${esc(k.link)}" target="_blank" rel="noopener" class="text-btn" style="display:inline-flex;align-items:center;gap:4px">Obter chave oficial ${ic('link')}</a>` : ''}

      <div class="field" style="margin-top:4px">
        <span>Variável de ambiente: <code>${esc(k.env)}</code></span>
        <div style="position:relative">
          <input type="password" class="key-input" data-env="${esc(k.env)}" placeholder="${k.has_value ? 'Chave salva (digite para alterar)' : 'Cole sua chave aqui'}" autocomplete="off">
          <button type="button" class="mini toggle-key-vis" title="Ver / Ocultar" style="position:absolute;right:6px;top:50%;transform:translateY(-50%)">${ic('sliders')}</button>
        </div>
        ${k.masked ? `<small class="hint">Atual: <code>${esc(k.masked)}</code></small>` : ''}
      </div>

      <div class="row" style="margin-top:6px">
        ${k.kind === 'secret' ? '' : `<button type="button" class="btn ghost small test-key-btn" data-key-id="${esc(k.id)}">
          ${ic('spark')} Testar chave
        </button>`}
        <button type="button" class="btn small save-single-key-btn" data-key-id="${esc(k.id)}" data-key-env="${esc(k.env)}">
          ${ic('check')} Salvar
        </button>
      </div>
      <div class="key-test-result" id="testResult_${esc(k.id)}" hidden></div>
    </article>
    `;
  }).join('');
}

async function testSingleKey(keyId, btn) {
  const card = $(`[data-key-id="${keyId}"]`);
  const input = card ? $(`[data-env]`, card) : null;
  const resultBox = $(`#testResult_${keyId}`);
  const val = (input && input.value.trim()) ? input.value.trim() : null;

  if (resultBox) {
    resultBox.hidden = false;
    resultBox.className = 'key-test-result busy';
    resultBox.innerHTML = '<span class="spin"></span> Testando conexão com o provedor...';
  }
  if (btn) btn.disabled = true;

  try {
    const res = await jpost('/api/keys/test', { key_id: keyId, key_value: val });
    if (resultBox) {
      resultBox.className = `key-test-result ${res.ok ? 'ok' : 'err'}`;
      resultBox.innerHTML = (res.ok ? '✓ ' : '✗ ') + esc(res.message);
    }
  } catch (err) {
    if (resultBox) {
      resultBox.className = 'key-test-result err';
      resultBox.innerHTML = '✗ ' + esc(err.message);
    }
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function saveKeyDict(keysToSave) {
  if (!Object.keys(keysToSave).length) {
    return toast('Nenhuma chave alterada para salvar.');
  }
  try {
    toast('Salvando no .env...');
    const res = await jpost('/api/keys', { keys: keysToSave });
    S.keys = res.keys || [];
    renderKeysGrid();
    await refreshHealth();
    toast('Chaves salvas com sucesso!');
  } catch (err) {
    toast(err.message);
  }
}

/* ---------- tela flow & mcp ---------- */
async function loadFlowView() {
  try {
    const [galleryRes, queueRes, projectsRes] = await Promise.all([
      api('/api/flow/gallery'),
      api('/api/flow/queue'),
      api('/api/projects'),
    ]);
    S.flowGallery = galleryRes.items || [];
    S.flowQueue = queueRes.items || [];
    S.flowProjects = projectsRes || [];
    const cfg = galleryRes.mcp_config || {};
    const box = $('#mcpConfigJson');
    if (box) box.value = JSON.stringify(cfg, null, 2);

    const pill = $('#flowApiPill');
    renderFlowPills();
    renderFlowGallery();
    renderFlowQueue();
    loadMcpChatProjects();
  } catch (err) {
    toast(err.message);
  }
}

/* Atualiza os selos do Flow conforme o motor realmente disponível. */
function renderFlowPills() {
  const health = S.health || {};
  const ready = !!health.flow_ai;
  const agentOn = !!(S.flowAgentCfg && S.flowAgentCfg.ativo);
  const tip = ready ? '' : (health.flow_error || '');
  const pill = $('#flowApiPill');
  if (pill) {
    pill.className = ready ? 'pill ok' : 'pill key';
    pill.textContent = ready
      ? (agentOn ? '● Flow Agent conectado' : '● Gemini API conectada')
      : (agentOn ? '● Flow Agent indisponível' : 'Gemini sem chave');
    pill.title = tip;
  }
  const batchPill = $('#flowBatchApiPill');
  if (batchPill) {
    batchPill.className = ready ? 'pill ok' : 'pill key';
    batchPill.textContent = ready
      ? (agentOn ? '● Flow Agent conectado' : '● Nano Banana conectado')
      : (agentOn ? '● Flow Agent indisponível' : 'Nano Banana sem chave');
    batchPill.title = tip;
  }
}

function renderFlowQueue() {
  const grid = $('#flowQueueGrid');
  const countEl = $('#flowQueueCount');
  const progressBox = $('#flowQueueProgress');
  const msgEl = $('#flowQueueMsg');
  const pctEl = $('#flowQueuePct');
  const fillEl = $('#flowQueueFill');
  if (!grid) return;
  if (countEl) countEl.textContent = `${S.flowQueue.length} item${S.flowQueue.length === 1 ? '' : 's'}`;
  const processing = S.flowQueue.filter(i => i.status === 'processando').length;
  const concluidos = S.flowQueue.filter(i => i.status === 'concluido').length;
  const erros = S.flowQueue.filter(i => i.status === 'erro').length;
  const total = S.flowQueue.length;
  if (progressBox) {
    progressBox.hidden = total === 0;
    if (total > 0) {
      const pct = total ? Math.round(((concluidos + erros) / total) * 100) : 0;
      pctEl.textContent = `${pct}%`;
      fillEl.style.width = `${pct}%`;
      msgEl.textContent = `${concluidos} concluído${concluidos !== 1 ? 's' : ''}, ${erros} com erro, ${processing} processando…`;
    } else {
      msgEl.textContent = 'Ocioso';
      pctEl.textContent = '0%';
      fillEl.style.width = '0%';
    }
  }
  if (!S.flowQueue.length) {
    grid.innerHTML = '<div class="empty" style="grid-column:1/-1">Nenhum item na fila ainda.</div>';
    return;
  }
  const projectsOptions = (S.flowProjects || []).map(p => `<option value="${esc(p.id)}">${esc(p.title || 'Sem título')} (${p.scenes || 0} cenas)</option>`).join('') || '<option value="">Nenhum projeto disponível</option>';
  grid.innerHTML = S.flowQueue.map(item => {
    const isVid = item.kind === 'video';
    const statusClass = item.status === 'concluido' ? 'ok' : item.status === 'erro' ? 'off' : 'key';
    const statusText = item.status === 'concluido' ? 'Concluído' : item.status === 'erro' ? 'Erro' : 'Processando…';
    const preview = item.url
      ? (isVid ? `<video src="${esc(item.url)}" controls preload="metadata" style="width:100%;height:90px;object-fit:cover;border-radius:8px;background:#000"></video>` : `<img src="${esc(item.url)}" alt="" style="width:100%;height:90px;object-fit:cover;border-radius:8px">`)
      : `<div style="width:100%;height:90px;background:rgba(10,18,34,.3);border-radius:8px;display:flex;align-items:center;justify-content:center;color:var(--muted);font-size:11px">Aguardando…</div>`;
    const toProjectHtml = item.status === 'concluido' && item.url
      ? `
      <div style="margin-top:8px;padding:8px;border:1px solid var(--line2);border-radius:8px;background:rgba(10,18,34,.3)">
        <div class="spread tiny" style="margin-bottom:4px"><b>Enviar para o projeto:</b></div>
        <div class="grid2" style="gap:6px">
          <div class="field"><span>Projeto</span><select class="to-project-select" data-item-id="${esc(item.id)}">${projectsOptions}</select></div>
          <div class="field"><span>Cena</span><select class="to-project-scene" data-item-id="${esc(item.id)}"><option value="">Selecione a cena</option></select></div>
        </div>
        <button class="btn primary small to-project-btn" data-item-id="${esc(item.id)}">${ic('send')} Adicionar à cena</button>
      </div>
      ` : '';
    return `
    <article class="pcard" style="position:relative">
      ${preview}
      <div class="spread" style="margin-top:8px">
        <span class="badge ${isVid ? 'work' : 'ready'}">${isVid ? 'VÍDEO' : 'IMAGEM'}</span>
        <span class="badge pill ${statusClass}" style="font-size:11px">${statusText}</span>
      </div>
      ${item.prompt ? `<p class="hint" style="display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;margin-top:6px;font-size:12px">${esc(item.prompt)}</p>` : ''}
      ${item.erro ? `<p class="hint" style="color:var(--red);font-size:11px;margin-top:6px">Erro: ${esc(item.erro)}</p>` : ''}
      <div class="foot" style="margin-top:8px">
        <small>${esc(item.created_at || '')}</small>
        ${item.status === 'concluido' && item.url ? `<a class="btn primary small" href="${esc(item.url)}" download="${esc(item.filename)}">${ic('download')} Baixar ${isVid ? 'MP4' : 'PNG'}</a>` : ''}
        ${item.status === 'erro' ? `<button class="btn ghost small retry-queue" data-id="${item.id}">${ic('refresh')} Tentar novamente</button>` : ''}
        ${item.status === 'processando' ? `<button class="btn ghost small" disabled>${ic('refresh')} Atualizar</button>` : ''}
      </div>
      ${toProjectHtml}
    </article>
    `;
  }).join('');
}

function renderFlowGallery() {
  const grid = $('#flowGalleryGrid');
  const countEl = $('#flowGalleryCount');
  if (countEl) countEl.textContent = `${S.flowGallery.length} arquivo${S.flowGallery.length === 1 ? '' : 's'}`;
  if (!grid) return;
  if (!S.flowGallery.length) {
    grid.innerHTML = '<div class="empty" style="grid-column:1/-1"><b>Nenhuma mídia na galeria</b>Gere imagens ou vídeos acima para vê-los e baixá-los aqui.</div>';
    return;
  }
  grid.innerHTML = S.flowGallery.map(item => {
    const isVid = item.kind === 'video';
    const previewEl = isVid
      ? `<video src="${esc(item.url)}" controls preload="metadata" style="width:100%;aspect-ratio:16/9;background:#000;border-radius:10px"></video>`
      : `<img src="${esc(item.url)}" alt="" loading="lazy" style="width:100%;aspect-ratio:16/9;object-fit:cover;border-radius:10px">`;
    return `
    <article class="pcard">
      ${previewEl}
      <div class="spread">
        <span class="badge ${isVid ? 'work' : 'ready'}">${isVid ? 'VÍDEO VEO' : 'IMAGEM NANO BANANA'}</span>
        <span class="tiny">${esc(item.size_mb)} MB</span>
      </div>
      ${item.prompt ? `<p class="hint" style="display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden"><b>Prompt:</b> ${esc(item.prompt)}</p>` : ''}
      <div class="foot">
        <small>${esc(item.created_at)}</small>
        <a class="btn primary small" href="${esc(item.url)}" download="${esc(item.filename)}">
          ${ic('download')} Baixar ${isVid ? 'MP4' : 'PNG'}
        </a>
      </div>
    </article>
    `;
  }).join('');
}

/* ---------- painel do robô */
async function openProject(id) {
  S.projectId = id; S.logSeq = 0; S.scenesRev = -1; S.genOpen = {}; $('#logBox').innerHTML = '';
  clearTimeout(S.projectGroq.poll); S.projectGroq = { job: null, busy: false, poll: null };
  // Limpa blocos do flow ao mudar de projeto (será recarregado ao abrir a view)
  S.flowBlocks = { blocos: [], busy: false, ready: false, projectId: null, ratio: '16:9' };
  try {
    const p = await api(`/api/projects/${id}`);
    S.project = p; showView('project'); history.replaceState(null, '', `#p=${id}`);
    $('#projTitle').textContent = p.title;
    renderAll(p); (p.log || []).forEach(addLog); S.logSeq = p.log_seq || 0;
    startPoll();
  } catch (err) { toast(err.message); }
}
function renderAll(p) {
  const st = p.settings || {};
  const tpl = S.catalog.templates.find(t => t.id === st.template);
  $('#projMeta').textContent = `${st.ratio || '16:9'} · ${st.quality || '720p'} · ${tpl ? tpl.name.toUpperCase() : ''}${st.autopilot ? ' · PILOTO AUTOMÁTICO' : ''}`;
  renderStatus(p); renderScenes(p); renderAction(p); renderGroqProject(p);
}
function stateOfRobot(p) {
  const cap = p.capcut || {};
  if (isWorking(p.status) || cap.status === 'building') return 'work';
  return { ready: 'wait', complete: 'done', failed: 'fail' }[p.status] || 'idle';
}
function renderStatus(p) {
  const rs = stateOfRobot(p); $('#robot').dataset.state = rs;
  const stages = p.stages || {}, cur = stages[p.current_stage];
  let now = 'Aguardando', sub = '';
  if (rs === 'work') { now = cur ? cur.label : 'Trabalhando'; sub = cur ? cur.detail : (p.message || ''); }
  else if (rs === 'wait') { now = 'Esperando você'; sub = 'Revise as cenas e clique em Montar vídeo.'; }
  else if (rs === 'done') { now = 'Vídeo pronto'; sub = 'Baixe o MP4 ou exporte para o CapCut.'; }
  else if (rs === 'fail') { now = 'Parei por um erro'; sub = p.error || p.message || ''; }
  $('#robotNow').textContent = now; $('#robotSub').textContent = sub;
  const pct = Math.round(p.progress || 0); $('#overallPct').textContent = `${pct}%`; $('#overallBar').style.width = `${pct}%`;
  const badge = $('#projStatus'); badge.textContent = STATUS[p.status] || 'PROCESSANDO'; badge.className = `badge ${badgeCls(p.status)}`;
  $('#cancelJob').hidden = !(isWorking(p.status) || (p.capcut || {}).status === 'building');
  const keys = S.catalog.stages.map(s => s.key), st = (S.project?.settings) || {};
  $('#stageList').innerHTML = keys.map((k, i) => {
    const s = stages[k] || { status: 'pending', label: S.catalog.stages[i].label, detail: '', progress: 0 };
    let icon = i + 1, status = s.status;
    if (status === 'running') icon = '<span class="spin"></span>'; else if (status === 'done') icon = ic('check'); else if (status === 'waiting') icon = ic('pause'); else if (status === 'failed') icon = ic('x'); else if (status === 'skipped') icon = ic('minus');
    let detail = s.detail || '';
    if (k === 'capcut' && status === 'pending' && !st.auto_capcut) detail = 'Opcional · gere quando quiser';
    let time = '';
    if (s.started) { const end = s.ended ? new Date(s.ended) : new Date(); const sec = Math.max(0, (end - new Date(s.started)) / 1000); if (status !== 'pending' && sec >= 1) time = sec >= 60 ? `${Math.floor(sec / 60)}m${String(Math.floor(sec % 60)).padStart(2, '0')}s` : `${Math.floor(sec)}s`; }
    return `<li class="stage ${status}"><div class="st-ic">${icon}</div><div class="st-body"><b>${esc(s.label)}</b>${detail ? `<small>${esc(detail)}</small>` : ''}${status === 'running' && s.progress > 0 ? `<div class="mini-track"><div style="width:${s.progress}%"></div></div>` : ''}</div><span class="st-time">${time}</span></li>`;
  }).join('');
}
function addLog(e) {
  const box = $('#logBox'), near = box.scrollHeight - box.scrollTop - box.clientHeight < 60;
  const row = document.createElement('div'); row.className = `log-line ${e.level || ''}`;
  row.innerHTML = `<time>${clock(e.t)}</time><em>${esc((S.catalog.stages.find(s => s.key === e.stage) || {}).label || e.stage || '')}</em><span>${esc(e.msg)}</span>`;
  box.appendChild(row); while (box.children.length > 400) box.firstChild.remove();
  if (near) box.scrollTop = box.scrollHeight;
}
$('#clearLog').onclick = () => { $('#logBox').innerHTML = ''; };

function capBox(p) {
  const cap = p.capcut || { status: 'none' };
  const steps = `<ol class="cap-steps"><li>Baixe e extraia o zip.</li><li>Feche o CapCut por completo.</li><li>Dê dois cliques em <b>INSTALAR_NO_CAPCUT.bat</b> (precisa do Python).</li><li>Abra o CapCut: o projeto aparece no topo.</li></ol>`;
  let body;
  if (cap.status === 'building') body = `<p><span class="spin" style="display:inline-block;vertical-align:-3px;margin-right:8px"></span>Montando o pacote… acompanhe na etapa "Projeto do CapCut".</p>`;
  else if (cap.status === 'ready') body = `<p>Pacote pronto${cap.size_mb ? ` · ${cap.size_mb} MB` : ''}. Traz as cenas, a narração, a música com o volume escolhido e as legendas como texto.</p><a class="btn primary" href="/api/projects/${p.id}/capcut/download">${ic('download')} Baixar projeto do CapCut</a>${steps}<p class="warn-text">Cor do template, vinheta, transições e redução automática da música ficam só no MP4. Feito para o CapCut desktop 8.x.</p><button class="btn ghost small" data-cap="go">${ic('refresh')} Gerar de novo</button>`;
  else if (cap.status === 'failed') body = `<p class="warn-text">${esc(cap.error || 'Não consegui montar o pacote.')}</p><button class="btn" data-cap="go">${ic('refresh')} Tentar de novo</button>`;
  else body = `<p>Gera uma pasta de rascunho com as cenas na timeline, a narração, a música e as legendas, para você refinar no CapCut.</p><button class="btn" data-cap="go">${ic('box')} Gerar projeto do CapCut</button>`;
  return `<div class="cap-box"><h4>${ic('scissors')} Importar no CapCut</h4>${body}</div>`;
}
function credits(p) {
  const lines = [];
  (p.scenes || []).forEach((s, i) => { const o = (s.options || [])[s.selected || 0]; if (o && o.provider !== 'Meu arquivo') lines.push(`Cena ${i + 1}: ${o.provider} · ${o.photographer || ''}${o.license ? ' · ' + o.license : ''}${o.source_url ? ' · ' + o.source_url : ''}`); });
  return lines.join('\n');
}
function renderAction(p) {
  const act = $('#actionCard'), res = $('#resultCard'), st = p.status;
  act.hidden = true; res.hidden = true;
  const changed = p.settings_changed_after_render;
  const hasMedia = (p.scenes || []).some(s => (s.options || []).length);
  if (st === 'complete') {
    res.hidden = false;
    const cr = credits(p);
    res.innerHTML = `<div class="result-grid"><div><video controls preload="metadata" src="/api/projects/${p.id}/video?v=${encodeURIComponent(p.updated_at || '')}"></video><div class="row" style="margin-top:14px"><a class="btn primary" href="/api/projects/${p.id}/download">${ic('download')} Baixar MP4</a><button class="btn ghost" data-act="rerender">${ic('refresh')} Montar de novo</button>${changed ? '<span class="warn-text">Você mudou algo depois desta montagem.</span>' : ''}</div></div><div class="cap">${capBox(p)}</div></div>${cr ? `<details class="fold" style="margin-top:16px"><summary>${ic('file')} Créditos e licenças das mídias usadas <small>Confira antes de publicar</small></summary><div class="fold-body"><pre style="white-space:pre-wrap;font:12px/1.6 var(--mono);color:#aebbd4;margin:0 0 12px">${esc(cr)}</pre><button class="btn ghost small" data-act="copy-credits">${ic('copy')} Copiar créditos</button></div></details>` : ''}`;
    return;
  }
  if (st === 'ready') {
    act.hidden = false;
    act.innerHTML = `<div class="grow"><h3>As cenas estão prontas para revisar</h3><p>O robô já pré-escolheu a melhor mídia de cada cena. Troque o que quiser abaixo e depois monte o vídeo.</p></div><button class="btn primary" data-act="render" ${hasMedia ? '' : 'disabled'}>${ic('bot')} Montar vídeo</button>${(p.capcut || {}).status === 'ready' ? `<a class="btn" href="/api/projects/${p.id}/capcut/download">${ic('download')} Baixar CapCut (desktop)</a>` : `<button class="btn" data-cap="go" ${hasMedia ? '' : 'disabled'}>${ic('box')} Só o projeto do CapCut</button>`}${hasMedia ? `<button class="btn ghost" data-act="capcut-draft">${ic('file')} Draft CapCut (.js)</button>` : ''}`;
    return;
  }
  if (st === 'failed') {
    act.hidden = false;
    act.innerHTML = `<div class="grow"><h3>O robô parou</h3><p class="warn-text">${esc(p.error || p.message || 'Erro desconhecido.')}</p></div><button class="btn primary" data-act="${hasMedia ? 'render' : 'research'}">${ic('refresh')} ${hasMedia ? 'Tentar montar de novo' : 'Tentar a busca de novo'}</button>`;
  }
}
function renderGroqProject(p) {
  const host = $('#groqProjectCard'); if (!host || !p) return;
  host.hidden = false;
  const ready = !!S.catalog?.groq?.ready;
  const G = S.projectGroq, job = G.job;
  const done = job && job.status === 'complete';
  const failed = job && job.status === 'failed';
  const busy = G.busy;
  const g = p.groq || {};
  const when = g.updated_at ? new Date(g.updated_at).toLocaleString('pt-BR') : '';
  const pill = !ready ? '<span class="pill key">falta GROQ_API_KEY</span>' : busy ? '<span class="pill free">● transcrevendo</span>' : g.job_id ? '<span class="pill ok">● SRT do Groq aplicado</span>' : '<span class="pill off">legenda estimada</span>';
  const button = busy ? `<span class="spin"></span> Transcrevendo…` : g.job_id ? `${ic('refresh')} Sincronizar de novo` : `${ic('mic')} Sincronizar legendas com Groq`;
  host.innerHTML = `<div class="card-title"><div><h3>${ic('mic')} Legendas sincronizadas (Groq Whisper)</h3><p>Reconhece a narração real do projeto palavra por palavra e substitui o SRT. As cenas e o áudio não são alterados.</p></div>${pill}</div>
    ${g.job_id ? `<div class="groq-project-meta"><span class="chip">${g.word_count || 0} palavras</span><span class="chip">${g.script_ratio ? `roteiro ${Math.round(g.script_ratio * 100)}%` : 'transcrição'}</span><span class="chip">${esc(g.model || 'whisper')}</span>${when ? `<span class="chip">${esc(when)}</span>` : ''}</div>` : '<div class="note info"><b>Vale a pena usar quando:</b> o SRT veio estimado, há silêncios longos, ou você quer legenda palavra a palavra no MP4 e no CapCut.</div>'}
    ${groqProgressHtml(job, 'projGroq')}
    <div class="row" style="margin-top:12px">
      <button type="button" class="btn ${g.job_id ? 'ghost' : 'primary'}" data-act="groq" ${(!ready || busy || isWorking(p.status)) ? 'disabled' : ''}>${button}</button>
      <span class="hint">${failed ? esc(job.error || job.message || 'Falhou.') : !ready ? 'Configure GROQ_API_KEY na tela de Chaves de API.' : isWorking(p.status) ? 'Espere o robô terminar a etapa atual.' : 'Usa o áudio já salvo no projeto. O resultado fica em cache por narração.'}</span>
    </div>`;
}
async function projectGroq() {
  const id = S.projectId; if (!id) return;
  if (!S.catalog?.groq?.ready) return toast('Configure GROQ_API_KEY na tela de Chaves de API.');
  if (S.projectGroq.busy) return;
  S.projectGroq.busy = true; clearTimeout(S.projectGroq.poll);
  S.projectGroq.job = { status: 'queued', progress: 4, message: 'Enviando o áudio do projeto…', stage: 'upload' };
  renderGroqProject(S.project);
  try {
    const fd = new FormData();
    fd.append('model', S.catalog.groq.models?.[0]?.id || 'whisper-large-v3-turbo');
    fd.append('language', 'auto');
    fd.append('mode', 'auto');
    fd.append('use_script', 'true');
    const res = await api(`/api/projects/${id}/transcribe`, { method: 'POST', body: fd });
    S.projectGroq.job = { id: res.id, status: 'queued', progress: 6, message: 'Na fila do Groq…', stage: 'queue' };
    renderGroqProject(S.project); pollProjectGroq(res.id);
  } catch (err) {
    S.projectGroq.busy = false;
    S.projectGroq.job = { status: 'failed', progress: 0, error: err.message, message: err.message };
    renderGroqProject(S.project); toast(err.message);
  }
}
async function pollProjectGroq(id) {
  const G = S.projectGroq; clearTimeout(G.poll);
  try {
    const j = await api(`/api/transcribe/${id}`);
    G.job = j; updateGroqProgressDom('projGroq', j);
    if (j.status === 'queued' || j.status === 'running') { G.poll = setTimeout(() => pollProjectGroq(id), 1900); return; }
    G.busy = false;
    if (j.status === 'complete') {
      toast(`Legendas do projeto sincronizadas: ${j.cue_count || 0} blocos.`);
      await refetch(); loadProjects();
    } else {
      toast(j.error || j.message || 'A transcrição falhou.');
      renderGroqProject(S.project);
    }
  } catch (err) {
    G.busy = false;
    G.job = { status: 'failed', progress: 0, error: err.message, message: err.message };
    renderGroqProject(S.project); toast(err.message);
  }
}

$('#viewProject').addEventListener('click', async e => {
  const b = e.target.closest('[data-act],[data-cap]'); if (!b || !S.projectId) return; const id = S.projectId;
  try {
    if (b.dataset.cap === 'go') { await api(`/api/projects/${id}/capcut`, { method: 'POST' }); toast('Montando o projeto do CapCut…'); startPoll(); }
    else if (b.dataset.act === 'render' || b.dataset.act === 'rerender') { await api(`/api/projects/${id}/render`, { method: 'POST' }); toast('O robô começou a montar.'); startPoll(); }
    else if (b.dataset.act === 'research') { await api(`/api/projects/${id}/research`, { method: 'POST' }); toast('Buscando de novo…'); startPoll(); }
    else if (b.dataset.act === 'groq') { await projectGroq(); }
    else if (b.dataset.act === 'capcut-draft') {
      const btn = b; btn.disabled = true; const old = btn.innerHTML; btn.innerHTML = '<span class="spin"></span> Gerando draft…';
      try {
        const res = await api(`/api/projects/${id}/capcut-draft`, { method: 'POST' });
        toast(`Draft do CapCut gerado: ${res.draft_name}.`);
        // download automático
        const a = document.createElement('a');
        a.href = `/api/projects/${id}/capcut-draft/download`;
        a.download = `capcut_draft_${res.draft_name}.js`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
      } catch (err) { toast(err.message); } finally { btn.disabled = false; btn.innerHTML = old; }
    }
    else if (b.dataset.act === 'copy-credits') { await navigator.clipboard.writeText(credits(S.project)); toast('Créditos copiados.'); }
  } catch (err) { toast(err.message); }
});
$('#cancelJob').onclick = async () => { try { await api(`/api/projects/${S.projectId}/cancel`, { method: 'POST' }); toast('Cancelando…'); } catch (e) { toast(e.message); } };
$('#autoPickBtn').onclick = async () => { try { await api(`/api/projects/${S.projectId}/auto-pick`, { method: 'POST' }); await refetch(); toast('Escolha automática aplicada.'); } catch (e) { toast(e.message); } };
$('#researchAllBtn').onclick = async () => { if (!confirm('Buscar a mídia de todas as cenas de novo? Suas escolhas atuais serão trocadas (arquivos enviados por você ficam).')) return; try { await api(`/api/projects/${S.projectId}/research`, { method: 'POST' }); startPoll(); } catch (e) { toast(e.message); } };
  document.getElementById('researchEmptyBtn')?.addEventListener('click', async () => {
    if (!S.projectId) return;
    if (!confirm('Buscar mídia apenas nas cenas que ainda não têm resultado? As cenas que já têm mídia serão mantidas.')) return;
    try {
      const r = await api(`/api/projects/${S.projectId}/research-empty`, {method:'POST'});
      toast(`Buscando ${r.empty_count} cenas sem mídia...`);
      startPoll();
    } catch(e) {
      toast(e.message || 'Erro ao iniciar busca');
    }
  });


$('#viewProject').addEventListener('click', e => {
  if (e.target.closest('#projMcpSendBtn')) projMcpSend();
  if (e.target.closest('#projMcpSuggestAllBtn')) projMcpSuggestAll();
});
$('#viewProject').addEventListener('keydown', e => {
  if (e.key === 'Enter' && e.target.closest('#projMcpInput')) { e.preventDefault(); projMcpSend(); }
});

/* ---------- cenas */
function sceneHtml(s, i, p) {
  const opts = s.options || [], sel = Math.min(s.selected || 0, Math.max(0, opts.length - 1)), o = opts[sel];
  const stockOnly = p.settings?.stock_only !== false;
  const gen = s.gen || {}, flowOk = !stockOnly && S.catalog.flow.ready;
  const img = o && o.thumbnail ? `<img loading="lazy" referrerpolicy="no-referrer" alt="" src="${esc(o.thumbnail)}" onerror="this.style.display='none'">` : ic('image');
  const strip = opts.map((x, k) => x.preview_only && String(x.provider || '').startsWith('YouTube')
    ? \`<button type="button" class="opt" data-match-youtube data-yturl="\${esc(x.download_url || x.source_url || '')}" title="Analisar vídeo e localizar o trecho que combina com esta fala"><img loading="lazy" referrerpolicy="no-referrer" alt="" src="\${esc(x.thumbnail || '')}" onerror="this.style.opacity=0"><i>ANALISAR</i></button>\`
    : \`<button type="button" class="opt \${k === sel ? 'on' : ''}" data-pick="\${k}" title="\${esc(\`\${x.provider} · \${x.photographer || ''}\${x.media_match_score != null ? ' · IA ' + x.media_match_score + '%' : ''}\`)}"><img loading="lazy" referrerpolicy="no-referrer" alt="" src="\${esc(x.thumbnail || '')}" onerror="this.style.opacity=0"><i>\${x.media_type === 'video' ? '▶' : 'FOTO'}</i></button>\`).join('');
  const line = o ? `<div class="src-line"><span>${esc(o.provider)}</span>${o.photographer ? `<span>· ${esc(o.photographer)}</span>` : ''}${o.license ? `<span>· ${esc(o.license)}</span>` : ''}${o.source_url ? `<a href="${esc(o.source_url)}" target="_blank" rel="noopener">origem ${ic('link')}</a>` : ''}</div>` : '';
  const matchInfo = o && o.media_match_score != null ? `<small class="hint"><b>Compatibilidade visual da IA: ${Math.round(Number(o.media_match_score))}%</b>${o.media_match_reason ? ` · ${esc(o.media_match_reason)}` : ''}</small>` : '';
  const verificationInfo = o && !o.relevance_verified && s.media_verification?.status === 'unavailable' ? `<small class="hint">Prévia ainda não validada pela IA: ${esc(s.media_verification.message || 'verifique se a imagem corresponde à fala antes de montar.')}</small>` : '';
  const rejectedInfo = !opts.length && Number(s.rejected_media_count || 0) > 0 ? ` A IA conferiu as prévias e descartou ${Number(s.rejected_media_count)} resultado(s) que não correspondiam à fala.` : '';
  const searchUsageInfo = s.search_usage ? `<small class="hint">Consultas aos bancos: ${Number(s.search_usage.requests || 0)}/${Number(s.search_usage.limit || 0)}${s.search_usage.limit_reached ? ' · limite atingido' : ''}</small>` : '';
  const open = S.genOpen[s.id];
  const genBox = open && !stockOnly ? `<div class="gen-box"><div class="seg"><button type="button" class="${open.kind === 'image' ? 'on' : ''}" data-genkind="image">Imagem · Nano Banana</button><button type="button" class="${open.kind === 'video' ? 'on' : ''}" data-genkind="video">Vídeo · Veo</button></div><textarea data-genprompt placeholder="Descreva a cena…">${esc(open.prompt)}</textarea><div class="row">${open.kind === 'video' ? `<select data-gensec style="width:auto">${[4, 6, 8].map(n => `<option value="${n}" ${open.seconds === n ? 'selected' : ''}>${n} s</option>`).join('')}</select>` : ''}<button type="button" class="btn primary small" data-gen="go">${ic('spark')} Gerar</button><button type="button" class="btn ghost small" data-gen="close">Fechar</button></div><small class="hint">${open.kind === 'video' ? 'O Veo cobra por segundo na sua chave Gemini e leva alguns minutos.' : 'A imagem sai em alguns segundos e entra nas opções da cena.'}</small></div>` : '';
  const genMsg = gen.status === 'running' ? `<div class="gen-msg"><span class="spin"></span>${esc(gen.message || 'Gerando…')}</div>` : gen.status === 'failed' ? `<div class="gen-msg fail">${ic('alert')} ${esc(gen.message || 'Falhou')}</div>` : '';
  const ytOpen = S.ytOpen[s.id];
  const ytBox = ytOpen ? `
  <div class="gen-box">
    <div class="spread">
      <b style="color:var(--cyan)">${ic('film')} Importar do YouTube</b>
      <button type="button" class="text-btn" data-act2="close-yt">fechar</button>
    </div>
    <div class="q-row">
      <input type="text" data-ytinput placeholder="Cole o link do vídeo ou termos para pesquisar..." value="${esc(ytOpen.query || s.query || '')}">
      <button type="button" class="btn ghost small" data-act2="search-yt" title="Buscar no YouTube">${ic('search')} Buscar</button>
    </div>
    <div class="row">
      <button type="button" class="btn primary small" data-act2="extract-yt">${ic('scan-search')} Analisar e recortar trecho</button>
    </div>
    <div class="yt-results-strip" data-ytresults style="${(ytOpen.results || []).length ? '' : 'display:none'}">
      ${(ytOpen.results || []).map(r => `
        <button type="button" class="yt-opt" data-act2="extract-yt-pick" data-yturl="${esc(r.download_url)}" title="${esc(r.title)}">
          <img src="${esc(r.thumbnail)}" alt="" referrerpolicy="no-referrer">
          <span>${esc(r.title)}</span>
        </button>
      `).join('')}
    </div>
  </div>` : '';

  return `<article class="scene" data-scene="${s.id}" data-i="${i}"><div class="scene-pv">${img}<span class="scene-no">CENA ${String(i + 1).padStart(2, '0')}</span><span class="scene-t">${fmtTime(s.start)} – ${fmtTime(s.end)}</span>${o ? `<span class="scene-type" style="top:8px;bottom:auto;right:auto">${o.media_type === 'video' ? 'VÍDEO' : 'FOTO'}</span>` : ''}</div>
  <div class="scene-body"><div class="scene-text">${esc(s.text)}</div>
  <div class="q-row"><input type="text" data-q value="${esc(s.query || '')}" maxlength="160" title="Termos de busca"><button type="button" class="mini" data-act2="research" title="Buscar de novo">${ic('search')}</button></div>
  ${opts.length ? `<div class="opt-strip">${strip}</div>${line}${matchInfo}${verificationInfo}` : `<div class="scene-empty">Nenhuma mídia compatível foi encontrada. Mude a busca, escolha outras fontes ou envie um arquivo.${esc(rejectedInfo)}</div>`}
  ${searchUsageInfo}
  ${(s.search_notes || []).length ? `<small class="hint">${esc(s.search_notes.join(' · '))}</small>` : ''}
  <div class="scene-actions"><label class="btn ghost upl">${ic('upload')} Meu arquivo<input type="file" data-upload accept=".jpg,.jpeg,.png,.webp,.mp4,.mov,.webm,.m4v"></label>${flowOk ? `<button type="button" class="btn ghost" data-act2="gen">${ic('spark')} Gerar com IA</button>` : ''}<button type="button" class="btn ghost" data-act2="yt">${ic('film')} YouTube</button></div>
  ${ytBox}${genBox}${genMsg}</div></article>`;
}
function renderScenes(p) {
  const scenes = p.scenes || [], show = scenes.length > 0;
  $('#sceneHead').hidden = !show; S.scenesRev = p.scenes_rev || 0;
  $('#sceneGrid').classList.toggle('locked', isWorking(p.status));
  $('#sceneGrid').innerHTML = scenes.map((s, i) => sceneHtml(s, i, p)).join('');
  $('#sceneHint').textContent = isWorking(p.status) ? 'O robô está trabalhando. As cenas ficam liberadas quando ele terminar.' : 'Escolha a mídia de cada cena. Você pode buscar de novo, enviar um arquivo seu ou gerar com IA.';
}
function replaceScene(sc) {
  const p = S.project, i = p.scenes.findIndex(x => x.id === sc.id); if (i < 0) return;
  p.scenes[i] = sc; const el = $(`.scene[data-scene="${sc.id}"]`); if (el) el.outerHTML = sceneHtml(sc, i, p);
}
$('#sceneGrid').addEventListener('click', async e => {
  const card = e.target.closest('.scene'); if (!card) return; const sid = card.dataset.scene, p = S.project, id = S.projectId;
  const pick = e.target.closest('[data-pick]'), a2 = e.target.closest('[data-act2]'), g = e.target.closest('[data-gen]'), gk = e.target.closest('[data-genkind]'), ytm = e.target.closest('[data-match-youtube]');
  try {
    if (ytm) {
      const url = ytm.dataset.yturl;
      if (!url || !window.confirm("Você confirma que é dono deste vídeo ou possui licença/permissão expressa para reutilizá-lo? O OpenRouter vai analisar a linha do tempo, localizar o trecho que combina com a fala atual do SRT e importar um clipe de até dez segundos, além de salvar um quadro do mesmo trecho. O aplicativo não verifica a licença automaticamente.")) return;
      ytm.disabled = true;
      try {
        toast('OpenRouter analisando a linha do tempo do YouTube…');
        const res = await jpost('/api/youtube/download', { url, project_id: id, scene_id: sid, rights_confirmed: true });
        delete S.ytOpen[sid]; replaceScene(res.scene);
        toast('Trecho sincronizado importado: vídeo de até ' + Number(res.match?.duration || 0).toFixed(1) + ' s + quadro.');
      } catch (err) { toast(err.message); ytm.disabled = false; }
    } else if (pick) { const r = await jpost(`/api/projects/${id}/scenes/${sid}`, { selected: Number(pick.dataset.pick) }, 'PATCH'); replaceScene(r.scene); }
    else if (a2 && a2.dataset.act2 === 'research') {
      const q = $('[data-q]', card).value.trim(); a2.disabled = true; a2.innerHTML = '<span class="spin"></span>';
      const r = await jpost(`/api/projects/${id}/scenes/${sid}/search`, { query: q || null }); replaceScene(r.scene);
      if (r.messages?.length) toast(r.messages[0]);
    } else if (a2 && a2.dataset.act2 === 'gen') {
      const sc = p.scenes.find(x => x.id === sid); S.genOpen[sid] = S.genOpen[sid] || { kind: 'image', seconds: 6, prompt: (sc.text || '').slice(0, 300) }; replaceScene(sc);
    } else if (a2 && a2.dataset.act2 === 'yt') {
      const sc = p.scenes.find(x => x.id === sid); S.ytOpen[sid] = S.ytOpen[sid] || { query: sc.query || '' }; replaceScene(sc);
    } else if (a2 && a2.dataset.act2 === 'close-yt') {
      delete S.ytOpen[sid]; replaceScene(p.scenes.find(x => x.id === sid));
    } else if (a2 && a2.dataset.act2 === 'search-yt') {
      const inp = $('[data-ytinput]', card); const q = (inp ? inp.value : '').trim();
      if (!q) return toast('Digite termos ou link para buscar no YouTube.');
      a2.disabled = true; const old = a2.innerHTML; a2.innerHTML = '<span class="spin"></span>';
      try {
        const res = await jpost('/api/youtube/search', { query: q, per: 6 });
        S.ytOpen[sid] = S.ytOpen[sid] || {}; S.ytOpen[sid].query = q; S.ytOpen[sid].results = res.results || [];
        replaceScene(p.scenes.find(x => x.id === sid));
        toast(`${(res.results || []).length} vídeos encontrados no YouTube.`);
      } catch (err) { toast(err.message); } finally { a2.disabled = false; a2.innerHTML = old; }
    } else if (a2 && a2.dataset.act2 === 'extract-yt') {
      const inp = $('[data-ytinput]', card); const url = (inp ? inp.value : '').trim();
      if (!url) return toast('Informe a URL do vídeo do YouTube.');
      if (!window.confirm("Você confirma que é dono deste vídeo ou possui licença/permissão expressa para reutilizá-lo? O OpenRouter vai analisar a linha do tempo, localizar o trecho que combina com a fala atual do SRT e importar um clipe de até dez segundos, além de salvar um quadro do mesmo trecho. O aplicativo não verifica a licença automaticamente.")) return;
      a2.disabled = true; a2.innerHTML = '<span class="spin"></span> Analisando…';
      try {
        const res = await jpost('/api/youtube/download', { url, project_id: id, scene_id: sid, rights_confirmed: true });
        delete S.ytOpen[sid]; replaceScene(res.scene);
        toast('Trecho sincronizado importado: vídeo de até ' + Number(res.match?.duration || 0).toFixed(1) + ' s + quadro.');
      } catch (err) { toast(err.message); a2.disabled = false; a2.innerHTML = `${ic('scan-search')} Analisar e recortar trecho`; }
    } else if (a2 && a2.dataset.act2 === 'extract-yt-pick') {
      const url = a2.dataset.yturl; if (!url) return;
      if (!window.confirm("Você confirma que é dono deste vídeo ou possui licença/permissão expressa para reutilizá-lo? O OpenRouter vai analisar a linha do tempo, localizar o trecho que combina com a fala atual do SRT e importar um clipe de até dez segundos, além de salvar um quadro do mesmo trecho. O aplicativo não verifica a licença automaticamente.")) return;
      a2.disabled = true;
      try {
        const res = await jpost('/api/youtube/download', { url, project_id: id, scene_id: sid, rights_confirmed: true });
        delete S.ytOpen[sid]; replaceScene(res.scene);
        toast('Trecho sincronizado importado: vídeo de até ' + Number(res.match?.duration || 0).toFixed(1) + ' s + quadro.');
      } catch (err) { toast(err.message); a2.disabled = false; }
    } else if (gk) { S.genOpen[sid].kind = gk.dataset.genkind; replaceScene(p.scenes.find(x => x.id === sid)); }
    else if (g && g.dataset.gen === 'close') { delete S.genOpen[sid]; replaceScene(p.scenes.find(x => x.id === sid)); }
    else if (g && g.dataset.gen === 'go') {
      const o = S.genOpen[sid]; o.prompt = $('[data-genprompt]', card).value; const sec = $('[data-gensec]', card); if (sec) o.seconds = Number(sec.value);
      await jpost(`/api/projects/${id}/scenes/${sid}/generate`, { kind: o.kind, prompt: o.prompt, seconds: o.seconds });
      delete S.genOpen[sid]; await refetch(); startPoll(); toast('Geração enviada ao Google.');
    }
  } catch (err) { toast(err.message); if (a2) { a2.disabled = false; a2.innerHTML = ic('search'); } }
});
$('#sceneGrid').addEventListener('keydown', e => { if (e.key === 'Enter' && e.target.matches('[data-q]')) { e.preventDefault(); $('[data-act2="research"]', e.target.closest('.scene')).click(); } });
$('#sceneGrid').addEventListener('change', async e => {
  const inp = e.target.closest('[data-upload]'); if (!inp || !inp.files[0]) return;
  const card = inp.closest('.scene'), fd = new FormData(); fd.append('file', inp.files[0]); toast('Enviando arquivo…');
  try { const r = await api(`/api/projects/${S.projectId}/scenes/${card.dataset.scene}/upload`, { method: 'POST', body: fd }); replaceScene(r.scene); toast('Arquivo adicionado à cena.'); } catch (err) { toast(err.message); }
});

/* ---------- acompanhamento ao vivo */
function startPoll() { stopPoll(); S.tick = 0; poll(); S.poll = setInterval(poll, 1400); }
function stopPoll() { if (S.poll) clearInterval(S.poll); S.poll = null; }

let flowPoll = null;
function startFlowPoll() { stopFlowPoll(); pollFlowQueue(); flowPoll = setInterval(pollFlowQueue, 5000); }
function stopFlowPoll() { if (flowPoll) clearInterval(flowPoll); flowPoll = null; }
async function pollFlowQueue() {
  try {
    const res = await api('/api/flow/queue');
    S.flowQueue = res.items || [];
    renderFlowQueue();
  } catch (err) { /* tenta de novo no próximo ciclo */ }
}

/* ---------- Chat MCP do OpenCode */
let mcpChatHistory = [];
let mcpChatProjectId = null;

async function loadMcpChatProjects() {
  try {
    const res = await api('/api/projects');
    S.flowProjects = res || [];
    const sel = $('#mcpChatProjectSelect');
    if (!sel) return;
    const current = sel.value;
    sel.innerHTML = '<option value="">Selecione um projeto</option>' +
      res.map(p => `<option value="${esc(p.id)}" ${p.id === current ? 'selected' : ''}>${esc(p.title || 'Sem título')} (${p.scenes || 0} cenas · ${esc(String(p.id).slice(0, 6))})</option>`).join('');
  } catch (err) { /* ignora */ }
}

function mcpChatAppendMessage(text, role = 'assistant') {
  const container = $('#mcpChatMessages');
  if (!container) return;
  const div = document.createElement('div');
  div.style.padding = '10px 12px';
  div.style.borderRadius = '10px';
  div.style.fontSize = '13px';
  div.style.lineHeight = '1.5';
  if (role === 'user') {
    div.style.background = 'rgba(79,214,220,.12)';
    div.style.border = '1px solid rgba(79,214,220,.35)';
    div.style.marginLeft = 'auto';
    div.style.maxWidth = '80%';
    div.style.textAlign = 'left';
  } else if (role === 'result') {
    div.style.background = 'rgba(95,217,160,.12)';
    div.style.border = '1px solid rgba(95,217,160,.35)';
    div.style.marginLeft = '0';
    div.style.maxWidth = '100%';
  } else {
    div.style.background = 'rgba(10,18,34,.3)';
    div.style.border = '1px solid var(--line2)';
    div.style.marginLeft = '0';
    div.style.maxWidth = '100%';
  }
  div.textContent = text;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
}

async function mcpChatCall(tool, args) {
  const res = await jpost('/api/mcp/call', { tool, arguments: args });
  return res;
}

async function mcpChatSend() {
  const input = $('#mcpChatInput');
  const resultBox = $('#mcpChatResult');
  const style = $('#mcpChatStyleSelect')?.value || 'cinematic';
  const text = (input?.value || '').trim();
  if (!text) return;
  input.value = '';
  resultBox.style.display = 'none';
  resultBox.innerHTML = '';
  mcpChatAppendMessage(text, 'user');
  mcpChatHistory.push({ role: 'user', content: text });

  // detecta intenção simples
  const lower = text.toLowerCase();
  let reply = '';

  try {
    if (lower.includes('sugerir') || lower.includes('mídia') || lower.includes('cena') || lower.includes('roteiro')) {
      if (!mcpChatProjectId) {
        reply = 'Por favor, selecione um projeto no menu acima para que eu possa analisar o roteiro e sugerir imagens e vídeos por cena.';
      } else {
        const sugestao = await mcpChatCall('suggest_media_for_script', { project_id: mcpChatProjectId, max_blocks: 60 });
        reply = `Analisei o projeto "${sugestao.title || 'sem título'}" com ${sugestao.total_scenes} cenas. Aqui estão as sugestões de busca para cada uma:`;
        resultBox.style.display = 'block';
        resultBox.innerHTML = '<div class="spread tiny" style="margin-bottom:8px"><b>Sugestões de mídia por cena:</b></div>' +
          sugestao.sugestoes.map(s => `
            <div style="margin-bottom:8px;padding:8px;border:1px solid var(--line2);border-radius:8px;background:rgba(10,18,34,.2);font-size:12px">
              <div class="spread" style="margin-bottom:4px"><b>Cena ${s.index + 1}</b><span class="badge pill key" style="font-size:10px">${s.has_options ? 'já tem mídia' : 'sem mídia'}</span></div>
              <div style="color:var(--muted);margin-bottom:4px">${esc(s.texto)}</div>
              <div class="grid2" style="gap:8px"><div class="field"><span>Imagem</span><span class="tiny" style="color:var(--cyan)">${esc(s.image_query)}</span></div><div class="field"><span>Vídeo</span><span class="tiny" style="color:var(--blue)">${esc(s.video_query)}</span></div></div>
            </div>
          `).join('');
      }
    } else if (lower.includes('imagem') || lower.includes('image')) {
      const p = await mcpChatCall('generate_image_prompt', { scene_text: text, style });
      reply = p.error ? `Erro: ${p.error}` : `Aqui está um prompt para imagem (estilo ${p.style}):`;
      resultBox.style.display = 'block';
      resultBox.innerHTML = `<div style="background:rgba(79,214,220,.1);border:1px solid rgba(79,214,220,.3);padding:10px;border-radius:8px;font-family:var(--mono);font-size:12px">${esc(p.prompt)}</div>`;
    } else if (lower.includes('vídeo') || lower.includes('video')) {
      const p = await mcpChatCall('generate_video_prompt', { scene_text: text, duration: 6 });
      reply = p.error ? `Erro: ${p.error}` : `Aqui está um prompt para vídeo:`;
      resultBox.style.display = 'block';
      resultBox.innerHTML = `<div style="background:rgba(106,140,255,.1);border:1px solid rgba(106,140,255,.3);padding:10px;border-radius:8px;font-family:var(--mono);font-size:12px">${esc(p.prompt)}</div>`;
    } else if (lower.includes('projeto') || lower.includes('listar')) {
      const lista = await mcpChatCall('list_projects', {});
      reply = `Encontrei ${lista.total} projeto${lista.total !== 1 ? 's' : ''} no estúdio:`;
      resultBox.style.display = 'block';
      resultBox.innerHTML = '<div class="spread tiny" style="margin-bottom:8px"><b>Projetos:</b></div>' +
        lista.projects.map(p => `<div style="margin-bottom:4px">${esc(p.title || 'Sem título')} — ${p.scenes || 0} cenas — ${p.status}</div>`).join('');
    } else {
      reply = 'Não entendi sua solicitação. Tente: "sugerir mídias por cena", "prompt de imagem para [texto]" ou "prompt de vídeo para [texto]".';
    }
  } catch (err) {
    reply = `Erro ao processar: ${err.message}`;
  }

  if (reply) {
    mcpChatAppendMessage(reply);
    mcpChatHistory.push({ role: 'assistant', content: reply });
  }
}

async function mcpChatQuickAction(action) {
  const input = $('#mcpChatInput');
  const resultBox = $('#mcpChatResult');
  const style = $('#mcpChatStyleSelect')?.value || 'cinematic';
  if (!mcpChatProjectId) {
    toast('Selecione um projeto primeiro.');
    return;
  }
  try {
    const sugestao = await mcpChatCall('suggest_media_for_script', { project_id: mcpChatProjectId, max_blocks: 60 });
    let texto = '';
    if (action === 'image-prompt') {
      const primeira = sugestao.sugestoes[0];
      if (!primeira) return toast('Nenhuma cena encontrada.');
      const p = await mcpChatCall('generate_image_prompt', { scene_text: primeira.texto, style });
      texto = `Prompt de imagem (cena ${primeira.index + 1}): ${p.prompt}`;
      resultBox.style.display = 'block';
      resultBox.innerHTML = `<div style="background:rgba(79,214,220,.1);border:1px solid rgba(79,214,220,.3);padding:10px;border-radius:8px;font-family:var(--mono);font-size:12px">${esc(p.prompt)}</div>`;
    } else if (action === 'video-prompt') {
      const primeira = sugestao.sugestoes[0];
      if (!primeira) return toast('Nenhuma cena encontrada.');
      const p = await mcpChatCall('generate_video_prompt', { scene_text: primeira.texto, duration: 6 });
      texto = `Prompt de vídeo (cena ${primeira.index + 1}): ${p.prompt}`;
      resultBox.style.display = 'block';
      resultBox.innerHTML = `<div style="background:rgba(106,140,255,.1);border:1px solid rgba(106,140,255,.3);padding:10px;border-radius:8px;font-family:var(--mono);font-size:12px">${esc(p.prompt)}</div>`;
    } else {
      mcpChatAppendMessage(`Analisei o projeto "${sugestao.title}" com ${sugestao.total_scenes} cenas.`, 'assistant');
      resultBox.style.display = 'block';
      resultBox.innerHTML = '<div class="spread tiny" style="margin-bottom:8px"><b>Sugestões de mídia por cena:</b></div>' +
        sugestao.sugestoes.map(s => `
          <div style="margin-bottom:8px;padding:8px;border:1px solid var(--line2);border-radius:8px;background:rgba(10,18,34,.2);font-size:12px">
            <div class="spread" style="margin-bottom:4px"><b>Cena ${s.index + 1}</b><span class="badge pill key" style="font-size:10px">${s.has_options ? 'já tem mídia' : 'sem mídia'}</span></div>
            <div style="color:var(--muted);margin-bottom:4px">${esc(s.texto)}</div>
            <div class="grid2" style="gap:8px"><div class="field"><span>Imagem</span><span class="tiny" style="color:var(--cyan)">${esc(s.image_query)}</span></div><div class="field"><span>Vídeo</span><span class="tiny" style="color:var(--blue)">${esc(s.video_query)}</span></div></div>
          </div>
        `).join('');
      return;
    }
    mcpChatAppendMessage(texto, 'assistant');
  } catch (err) {
    toast(`Erro: ${err.message}`);
  }
}

/* ---------- Chat MCP para busca de mídias no projeto atual */
let projMcpHistory = [];

function projMcpAppendMessage(text, role = 'assistant') {
  const container = $('#projMcpMessages');
  if (!container) return;
  const div = document.createElement('div');
  div.style.padding = '10px 12px';
  div.style.borderRadius = '10px';
  div.style.fontSize = '13px';
  div.style.lineHeight = '1.5';
  if (role === 'user') {
    div.style.background = 'rgba(79,214,220,.12)';
    div.style.border = '1px solid rgba(79,214,220,.35)';
    div.style.marginLeft = 'auto';
    div.style.maxWidth = '80%';
  } else if (role === 'result') {
    div.style.background = 'rgba(95,217,160,.12)';
    div.style.border = '1px solid rgba(95,217,160,.35)';
    div.style.marginLeft = '0';
    div.style.maxWidth = '100%';
  } else {
    div.style.background = 'rgba(10,18,34,.3)';
    div.style.border = '1px solid var(--line2)';
    div.style.marginLeft = '0';
    div.style.maxWidth = '100%';
  }
  div.textContent = text;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
}

async function projMcpSend() {
  const input = $('#projMcpInput');
  const resultBox = $('#projMcpResult');
  const style = $('#projMcpStyleSelect')?.value || 'cinematic';
  const text = (input?.value || '').trim();
  if (!text) return;
  input.value = '';
  projMcpAppendMessage(text, 'user');
  projMcpHistory.push({ role: 'user', content: text });

  const lower = text.toLowerCase();
  let reply = '';

  try {
    if (lower.includes('sugerir') || lower.includes('mídia') || lower.includes('cena') || lower.includes('roteiro')) {
      const sugestao = await mcpChatCall('suggest_media_for_script', { project_id: S.projectId, max_blocks: 60 });
      reply = `Analisei o projeto "${sugestao.title || 'sem título'}" com ${sugestao.total_scenes} cenas. Aqui estão as sugestões de busca:`;
      resultBox.style.display = 'block';
      resultBox.innerHTML = '<div class="spread tiny" style="margin-bottom:8px"><b>Sugestões por cena:</b></div>' +
        sugestao.sugestoes.map(s => `
          <div style="margin-bottom:8px;padding:8px;border:1px solid var(--line2);border-radius:8px;background:rgba(10,18,34,.2);font-size:12px">
            <div class="spread" style="margin-bottom:4px"><b>Cena ${s.index + 1}</b><span class="badge pill key" style="font-size:10px">${s.has_options ? 'já tem mídia' : 'sem mídia'}</span></div>
            <div style="color:var(--muted);margin-bottom:4px">${esc(s.texto)}</div>
            <div class="grid2" style="gap:8px"><div class="field"><span>Imagem</span><span class="tiny" style="color:var(--cyan)">${esc(s.image_query)}</span></div><div class="field"><span>Vídeo</span><span class="tiny" style="color:var(--blue)">${esc(s.video_query)}</span></div></div>
          </div>
        `).join('');
    } else if (lower.includes('imagem')) {
      const p = await mcpChatCall('generate_image_prompt', { scene_text: text, style });
      reply = p.error ? `Erro: ${p.error}` : `Prompt de imagem (estilo ${p.style}):`;
      resultBox.style.display = 'block';
      resultBox.innerHTML = `<div style="background:rgba(79,214,220,.1);border:1px solid rgba(79,214,220,.3);padding:10px;border-radius:8px;font-family:var(--mono);font-size:12px">${esc(p.prompt)}</div>`;
    } else if (lower.includes('vídeo') || lower.includes('video')) {
      const p = await mcpChatCall('generate_video_prompt', { scene_text: text, duration: 6 });
      reply = p.error ? `Erro: ${p.error}` : `Prompt de vídeo:`;
      resultBox.style.display = 'block';
      resultBox.innerHTML = `<div style="background:rgba(106,140,255,.1);border:1px solid rgba(106,140,255,.3);padding:10px;border-radius:8px;font-family:var(--mono);font-size:12px">${esc(p.prompt)}</div>`;
    } else {
      reply = 'Tente: "sugira imagens para todas as cenas", "prompt de vídeo para [texto]" ou "qual imagem combina com [texto]?".';
    }
  } catch (err) {
    reply = `Erro: ${err.message}`;
  }

  if (reply) {
    projMcpAppendMessage(reply);
    projMcpHistory.push({ role: 'assistant', content: reply });
  }
}

async function projMcpSuggestAll() {
  const resultBox = $('#projMcpResult');
  try {
    const sugestao = await mcpChatCall('suggest_media_for_script', { project_id: S.projectId, max_blocks: 60 });
    projMcpAppendMessage(`Analisei o projeto "${sugestao.title}" com ${sugestao.total_scenes} cenas.`, 'assistant');
    resultBox.style.display = 'block';
    resultBox.innerHTML = '<div class="spread tiny" style="margin-bottom:8px"><b>Sugestões por cena:</b></div>' +
      sugestao.sugestoes.map(s => `
        <div style="margin-bottom:8px;padding:8px;border:1px solid var(--line2);border-radius:8px;background:rgba(10,18,34,.2);font-size:12px">
          <div class="spread" style="margin-bottom:4px"><b>Cena ${s.index + 1}</b><span class="badge pill key" style="font-size:10px">${s.has_options ? 'já tem mídia' : 'sem mídia'}</span></div>
          <div style="color:var(--muted);margin-bottom:4px">${esc(s.texto)}</div>
          <div class="grid2" style="gap:8px"><div class="field"><span>Imagem</span><span class="tiny" style="color:var(--cyan)">${esc(s.image_query)}</span></div><div class="field"><span>Vídeo</span><span class="tiny" style="color:var(--blue)">${esc(s.video_query)}</span></div></div>
        </div>
      `).join('');
  } catch (err) {
    toast(`Erro: ${err.message}`);
  }
}

async function refetch() { const p = await api(`/api/projects/${S.projectId}`); S.project = p; renderAll(p); S.logSeq = Math.max(S.logSeq, p.log_seq || 0); return p; }
async function poll() {
  const id = S.projectId; if (!id) return;
  try {
    const s = await api(`/api/projects/${id}/status?since=${S.logSeq}`); if (id !== S.projectId) return;
    s.log.forEach(addLog); S.logSeq = s.log_seq || S.logSeq;
    const prev = S.project || {}, merged = { ...prev, ...s, settings: prev.settings, scenes: prev.scenes };
    const typing = document.activeElement && $('#sceneGrid').contains(document.activeElement) && ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName);
    const changed = s.status !== prev.status || s.scenes_rev !== S.scenesRev || (prev.capcut || {}).status !== (s.capcut || {}).status || !!s.generating !== !!prev.generating || s.output_file !== prev.output_file;
    S.tick++;
    if ((changed || (s.generating && S.tick % 3 === 0)) && !typing) { await refetch(); }
    else { S.project = merged; renderStatus(merged); }
    const busy = isWorking(s.status) || s.generating || (s.capcut || {}).status === 'building';
    if (!busy) { stopPoll(); await refetch(); loadProjects(); }
  } catch (err) { /* tenta de novo no próximo ciclo */ }
}

/* ---------- editor de estilo e áudio de um projeto */
$('#editSettings').onclick = () => {
  const p = S.project; if (!p) return;
  if (isWorking(p.status)) return toast('Espere o robô terminar para mudar os ajustes.');
  EDIT.cfg = clone(p.settings); EDIT.projectId = p.id; EDIT.tab = 'style';
  $('#editor').hidden = false; document.body.style.overflow = 'hidden'; renderPane(EDIT);
};
function closeEditor() { $('#editor').hidden = true; document.body.style.overflow = ''; player.pause(); }
$('#closeEditor').onclick = closeEditor;
$('#editor').addEventListener('mousedown', e => { if (e.target.id === 'editor') closeEditor(); });
$('#saveEditor').onclick = async () => {
  const btn = $('#saveEditor'); btn.disabled = true;
  try { await jpost(`/api/projects/${EDIT.projectId}/settings`, EDIT.cfg, 'PATCH'); await refetch(); closeEditor(); toast('Ajustes salvos. Vale para a próxima montagem.'); }
  catch (err) { toast(err.message); } finally { btn.disabled = false; }
};

/* ---------- navegação, saúde e login */
async function refreshHealth() {
  S.healthStatus = 'checking';
  S.healthError = '';
  renderHealth();

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 12000);
  try {
    const health = await api('/api/health', { signal: controller.signal });
    if (!health || health.ok === false) {
      throw new Error('O servidor respondeu, mas informou que não está saudável.');
    }
    S.health = health;
    S.healthStatus = 'online';
    return health;
  } catch (err) {
    S.health = null;
    S.healthStatus = 'offline';
    S.healthError = err?.name === 'AbortError'
      ? 'Tempo limite ao consultar o servidor (12 segundos).'
      : (err?.message || 'Não foi possível consultar o servidor.');
    return null;
  } finally {
    clearTimeout(timeout);
    renderHealth();
  }
}

function renderHealth() {
  const host = $('#healthList');
  if (!host) return;
  const li = (cls, text) => `<li><span class="dot ${cls}"></span>${text}</li>`;

  if (S.healthStatus === 'checking') {
    host.innerHTML = li('', 'Verificando…');
    return;
  }
  if (S.healthStatus !== 'online' || !S.health) {
    host.innerHTML = [
      li('bad', 'Servidor indisponível'),
      li('warn', esc(S.healthError || 'Não foi possível consultar a API do servidor.')),
    ].join('');
    return;
  }

  const h = S.health;
  const src = Array.isArray(S.catalog?.sources) ? S.catalog.sources : [];
  const ready = src.filter(s => s.ready).length;
  const catalogLabel = S.catalog
    ? `${ready} de ${src.length} bancos prontos`
    : (S.catalogStatus === 'error' ? 'Catálogo de mídia indisponível' : 'Carregando bancos de mídia…');
  const catalogClass = S.catalog
    ? (ready >= 3 ? 'ok' : 'warn')
    : (S.catalogStatus === 'error' ? 'warn' : '');

  host.innerHTML = [
    li('ok', 'Servidor conectado'),
    li(h.ffmpeg_available ? 'ok' : 'bad', h.ffmpeg_available ? 'FFmpeg ativo' : 'FFmpeg ausente'),
    li(h.subtitles_available ? 'ok' : 'warn', h.subtitles_available ? 'Legendas queimadas' : 'Sem libass (legendas)'),
    li(catalogClass, catalogLabel),
    li(h.fish_audio ? 'ok' : '', h.fish_audio ? 'Fish Audio ligado' : 'Fish Audio sem chave'),
    li(h.flow_ai ? 'ok' : '', h.flow_ai ? 'IA do Google Flow ligada' : 'IA do Google Flow sem chave'),
    li(h.groq ? 'ok' : '', h.groq ? 'Groq (Whisper) ligado' : 'Groq sem chave'),
  ].join('');
  if (h.password_enabled) $('#logoutBtn').hidden = false;
  // rolagem automática da barra lateral quando houver novo conteúdo
  const side = document.querySelector('.side');
  if (side) side.scrollTop = side.scrollHeight;
}
$$('.nav-item').forEach(b => b.addEventListener('click', () => { showView(b.dataset.view); if (b.dataset.view === 'projects') loadProjects(); }));
$('#refreshProjects').onclick = loadProjects;
$('#backToProjects').onclick = () => { showView('projects'); loadProjects(); };
$('#prevTab').onclick = () => { const i = TABS.findIndex(t => t.id === CREATE.tab); if (i > 0) goTab(CREATE, TABS[i - 1].id); };
$('#nextTab').onclick = () => { const i = TABS.findIndex(t => t.id === CREATE.tab); if (i < TABS.length - 1) goTab(CREATE, TABS[i + 1].id); };
$('#submitProject').onclick = submitProject;
$('#loginForm').addEventListener('submit', async e => {
  e.preventDefault(); $('#loginError').hidden = true;
  try { await jpost('/api/login', { password: $('#loginPassword').value }); $('#loginOverlay').hidden = true; $('#loginPassword').value = ''; await init(); }
  catch (err) { $('#loginError').textContent = err.message; $('#loginError').hidden = false; }
});
$('#logoutBtn').onclick = async () => { await api('/api/logout', { method: 'POST' }); $('#loginOverlay').hidden = false; };

// Listeners para View Keys
$('#viewKeys')?.addEventListener('click', async e => {
  const t = e.target;
  const toggleBtn = t.closest('.toggle-key-vis');
  if (toggleBtn) {
    const input = toggleBtn.previousElementSibling;
    if (input) input.type = input.type === 'password' ? 'text' : 'password';
    return;
  }
  const testBtn = t.closest('.test-key-btn');
  if (testBtn) {
    return testSingleKey(testBtn.dataset.keyId, testBtn);
  }
  const saveBtn = t.closest('.save-single-key-btn');
  if (saveBtn) {
    const card = saveBtn.closest('.key-card');
    const input = card ? $('[data-env]', card) : null;
    const env = saveBtn.dataset.keyEnv;
    if (input && env) {
      const val = input.value.trim();
      if (!val) return toast('Digite um novo valor para a chave antes de salvar.');
      return saveKeyDict({ [env]: val });
    }
  }
});

$('#runSystemDoctorBtn')?.addEventListener('click', loadSystemDiagnostics);

$('#saveAllKeysBtn')?.addEventListener('click', () => {
  const toSave = {};
  $$('#keysCardsGrid [data-env]').forEach(inp => {
    if (inp.value && inp.value.trim()) {
      toSave[inp.dataset.env] = inp.value.trim();
    }
  });
  saveKeyDict(toSave);
});

$('#testAllKeysBtn')?.addEventListener('click', async () => {
  const btns = $$('#keysCardsGrid .test-key-btn').filter(btn => btn.dataset.keyId !== 'storyblocks_secret');
  for (const btn of btns) {
    await testSingleKey(btn.dataset.keyId, btn);
  }
  toast('Testes de chaves concluídos.');
});

// Listeners para View Flow
$('#viewFlow')?.addEventListener('click', async e => {
  const t = e.target;
  const kindBtn = t.closest('[data-flowkind]');
  if (kindBtn && !kindBtn.closest('#flowBatchKindSeg')) {
    $$('#flowKindSeg button').forEach(b => b.classList.toggle('on', b === kindBtn));
    S.flowKind = kindBtn.dataset.flowkind;
    const durField = $('#flowDurationField');
    if (durField) durField.style.display = S.flowKind === 'video' ? 'block' : 'none';
    return;
  }
  const presetBtn = t.closest('.flow-preset');
  if (presetBtn) {
    const inp = $('#flowPromptInput');
    if (inp) inp.value = presetBtn.dataset.preset;
    return;
  }
  if (t.closest('#copyMcpConfigBtn')) {
    const box = $('#mcpConfigJson');
    if (box) {
      await navigator.clipboard.writeText(box.value);
      toast('Configuração MCP copiada para a área de transferência!');
    }
    return;
  }
  if (t.closest('#goToKeysBtn')) {
    return showView('keys');
  }
  if (t.closest('#refreshFlowBtn')) {
    return loadFlowView();
  }
  // ---------- Upload de imagem de referência ----------
  const refInput = $('#flowRefFile');
  const refName = $('#flowRefName');
  if (refInput && !refInput.dataset.boundUpload) {
    refInput.dataset.boundUpload = '1';
    refInput.addEventListener('change', async () => {
      if (!refInput.files?.length) return;
      const file = refInput.files[0];
      const formData = new FormData();
      formData.append('file', file);
      try {
        const res = await jpostForm('/api/flow/upload-reference', formData);
        if (refName) refName.textContent = `✓ ${file.name}`;
        refInput.dataset.referencePath = res.path || '';
        toast('Imagem de referência enviada.');
      } catch (err) {
        toast(`Falha ao enviar referência: ${err.message}`);
        refInput.value = '';
      }
    });
  }

  // ---------- Upload de TXT com prompts ----------
  const txtInput = $('#flowTxtFile');
  const txtName = $('#flowTxtName');
  const batchCountHint = $('#flowBatchCountHint');
  const batchTextarea = $('#flowBatchPrompts');
  if (txtInput && !txtInput.dataset.boundUpload) {
    txtInput.dataset.boundUpload = '1';
    txtInput.addEventListener('change', async () => {
      if (!txtInput.files?.length) return;
      const file = txtInput.files[0];
      const formData = new FormData();
      formData.append('file', file);
      try {
        const res = await jpostForm('/api/flow/upload-txt-prompts', formData);
        if (txtName) txtName.textContent = `✓ ${file.name} (${res.total} prompts)`;
        txtInput.dataset.txtPrompts = JSON.stringify(res.prompts);
        if (batchCountHint) batchCountHint.textContent = `${res.total} prompts`;
        // Preenche o textarea com os prompts do arquivo
        if (batchTextarea && res.prompts?.length) {
          batchTextarea.value = res.prompts.join('\n');
        }
        toast(`${res.total} prompts carregados do arquivo.`);
      } catch (err) {
        toast(`Falha ao ler arquivo: ${err.message}`);
        txtInput.value = '';
      }
    });
  }

  // Contagem de prompts ao digitar no textarea
  if (batchTextarea && batchCountHint && !batchTextarea.dataset.boundCount) {
    batchTextarea.dataset.boundCount = '1';
    batchTextarea.addEventListener('input', () => {
      const prompts = (batchTextarea.value || '').split('\n').map(p => p.trim()).filter(p => p);
      batchCountHint.textContent = `${prompts.length} prompts`;
    });
  }

  if (t.closest('#flowGenerateSubmit')) {
    const btn = $('#flowGenerateSubmit');
    const prompt = ($('#flowPromptInput')?.value || '').trim();
    if (!prompt) return toast('Digite um prompt para gerar a mídia.');
    const ratio = $('#flowRatioSelect')?.value || '16:9';
    const seconds = Number($('#flowDurationSelect')?.value || 6);
    const model = $('#flowModelSelect')?.value || 'harbor_seal';
    const referenceImage = $('#flowRefFile')?.dataset?.referencePath || undefined;
    const statusBox = $('#flowGeneratingStatus');
    const statusText = $('#flowGeneratingText');

    btn.disabled = true;
    if (statusBox) statusBox.hidden = false;
    if (statusText) statusText.textContent = 'Enviando para a fila…';

    try {
      const res = await jpost('/api/flow/generate', {
        prompt, kind: S.flowKind, ratio, seconds, model, reference_image: referenceImage,
      });
      toast('Item adicionado à fila de geração.');
      if ($('#flowPromptInput')) $('#flowPromptInput').value = '';
      if (refName) refName.textContent = 'Nenhuma imagem escolhida';
      if ($('#flowRefFile')) { $('#flowRefFile').value = ''; delete $('#flowRefFile').dataset.referencePath; }
      await loadFlowView();
    } catch (err) {
      toast(`Falha ao adicionar à fila: ${err.message}`);
    } finally {
      btn.disabled = false;
      if (statusBox) statusBox.hidden = true;
    }
  }

  // ---------- Geração em lote (prompts infinitos) ----------
  const batchKindBtn = t.closest('#flowBatchKindSeg button');
  if (batchKindBtn) {
    $$('#flowBatchKindSeg button').forEach(b => b.classList.toggle('on', b === batchKindBtn));
    const durField = $('#flowBatchDurationField');
    if (durField) durField.style.display = batchKindBtn.dataset.flowkind === 'video' ? 'block' : 'none';
    return;
  }
  if (t.closest('#flowBatchGenerateSubmit')) {
    const btn = $('#flowBatchGenerateSubmit');
    const textarea = $('#flowBatchPrompts');
    let prompts = (textarea?.value || '').split('\n').map(p => p.trim()).filter(p => p);
    // Se houver arquivo TXT carregado, usa os prompts dele
    if (txtInput?.dataset.txtPrompts) {
      try { prompts = JSON.parse(txtInput.dataset.txtPrompts); } catch {}
    }
    if (!prompts.length) return toast('Digite pelo menos um prompt ou envie um arquivo TXT.');
    const kind = $('#flowBatchKindSeg button.on')?.dataset.flowkind || 'image';
    const ratio = $('#flowBatchRatioSelect')?.value || '16:9';
    const seconds = Number($('#flowBatchDurationSelect')?.value || Number($('#flowDurationSelect')?.value || 6));
    const model = $('#flowModelSelect')?.value || 'harbor_seal';
    const progressBox = $('#flowBatchProgress');
    const resultList = $('#flowBatchResultList');
    const msgEl = $('#flowBatchMsg');
    const pctEl = $('#flowBatchPct');
    const fillEl = $('#flowBatchFill');

    btn.disabled = true;
    progressBox.hidden = false;
    resultList.innerHTML = '';
    try {
      const res = await jpost('/api/flow/batch-generate', {
        prompts, kind, ratio, seconds, model,
      });
      msgEl.textContent = `${res.total} prompts adicionados à fila.`;
      pctEl.textContent = '100%';
      fillEl.style.width = '100%';
      toast(`${res.total} prompts adicionados à fila de geração.`);
      if (txtInput) { txtInput.value = ''; if (txtName) txtName.textContent = 'Nenhum arquivo escolhido'; delete txtInput.dataset.txtPrompts; }
      if (batchCountHint) batchCountHint.textContent = '0 prompts';
      await loadFlowView();
    } catch (err) {
      msgEl.textContent = 'Erro no lote.';
      toast(`Falha na geração em lote: ${err.message}`);
    } finally {
      btn.disabled = false;
    }
  }

  // ---------- Retry individual de item da fila ----------
  const retryBtn = t.closest('.retry-queue');
  if (retryBtn) {
    const id = retryBtn.dataset.id;
    retryBtn.disabled = true;
    retryBtn.textContent = 'Reprocessando…';
    try {
      await jpost('/api/flow/queue/retry', { id });
      toast('Item reenviado para a fila.');
      await loadFlowView();
    } catch (err) {
      toast(`Falha ao reprocessar: ${err.message}`);
    } finally {
      retryBtn.disabled = false;
    }
  }

  // ---------- Limpar concluídos da fila ----------
  if (t.closest('#flowQueueClearBtn')) {
    const btn = $('#flowQueueClearBtn');
    if (!confirm('Remover todos os itens concluídos e com erro da fila?')) return;
    btn.disabled = true;
    try {
      await jpost('/api/flow/queue/clear', { status: 'concluido' });
      await jpost('/api/flow/queue/clear', { status: 'erro' });
      toast('Fila limpa.');
      await loadFlowView();
    } catch (err) {
      toast(`Falha ao limpar fila: ${err.message}`);
    } finally {
      btn.disabled = false;
    }
  }

  // ---------- Limpar galeria ----------
  if (t.closest('#flowGalleryClearBtn')) {
    if (!confirm('Remover todos os arquivos da galeria? Isso não pode ser desfeito.')) return;
    try {
      const res = await jpost('/api/flow/gallery/clear');
      toast(`Galeria limpa (${res.removed} arquivos).`);
      await loadFlowView();
    } catch (err) {
      toast(`Falha ao limpar galeria: ${err.message}`);
    }
  }

  // ---------- Selecionar projeto → carregar cenas ----------
  const projectSelect = t.closest('.to-project-select');
  if (projectSelect) {
    const projectId = projectSelect.value;
    const itemId = projectSelect.dataset.itemId;
    const sceneSelect = $(`.to-project-scene[data-item-id="${esc(itemId)}"]`);
    if (!projectId || !sceneSelect) return;
    sceneSelect.disabled = true;
    sceneSelect.innerHTML = '<option value="">Carregando cenas…</option>';
    try {
      const proj = await api(`/api/projects/${projectId}`);
      const scenes = proj.scenes || [];
      sceneSelect.innerHTML = '<option value="">Selecione a cena</option>' + scenes.map((s, i) => {
        const label = s.title || s.query || `Cena ${i + 1}`;
        return `<option value="${esc(s.id)}">${esc(label)}</option>`;
      }).join('');
    } catch (err) {
      sceneSelect.innerHTML = '<option value="">Erro ao carregar cenas</option>';
    } finally {
      sceneSelect.disabled = false;
    }
  }

  // ---------- Adicionar item da fila à cena do projeto ----------
  const toProjectBtn = t.closest('.to-project-btn');
  if (toProjectBtn) {
    const itemId = toProjectBtn.dataset.itemId;
    const projectSelect = $(`.to-project-select[data-item-id="${esc(itemId)}"]`);
    const sceneSelect = $(`.to-project-scene[data-item-id="${esc(itemId)}"]`);
    const projectId = projectSelect?.value;
    const sceneId = sceneSelect?.value;
    if (!projectId) return toast('Selecione um projeto.');
    if (!sceneId) return toast('Selecione uma cena.');
    toProjectBtn.disabled = true;
    toProjectBtn.textContent = 'Adicionando…';
    try {
      await jpost(`/api/flow/queue/item/${itemId}/to-project`, { project_id: projectId, scene_id: sceneId });
      toast('Mídia adicionada à cena do projeto!');
      await loadFlowView();
    } catch (err) {
      toast(`Falha ao adicionar ao projeto: ${err.message}`);
    } finally {
      toProjectBtn.disabled = false;
    }
  }


  // ---------- Chat MCP: botão enviar ----------
  if (t.closest('#mcpChatSendBtn')) {
    mcpChatSend();
  }
  if (t.closest('#mcpChatInput') && e.key === 'Enter') {
    mcpChatSend();
  }

  // ---------- Chat MCP: ação rápida ----------
  const quickBtn = t.closest('#mcpChatQuickSeg button');
  if (quickBtn) {
    $$('#mcpChatQuickSeg button').forEach(b => b.classList.toggle('on', b === quickBtn));
    mcpChatQuickAction(quickBtn.dataset.mcpaction);
  }
});

$('#viewFlow')?.addEventListener('change', e => {
  if (e.target.id === 'mcpChatProjectSelect') mcpChatProjectId = e.target.value || null;
  else if (e.target.classList?.contains('to-project-select')) e.target.dispatchEvent(new MouseEvent('click', { bubbles: true }));
});
$('#viewFlow')?.addEventListener('keydown', e => {
  if (e.key === 'Enter' && e.target.id === 'mcpChatInput') { e.preventDefault(); mcpChatSend(); }
});

/* ---------- View Flow Blocos (animação 2D por cena) */
async function loadFlowBlocksView() {
  const pill = $('#flowBlocksApiPill');
  const chip = $('#flowBlocksProjetoChip');
  try {
    const res = await api('/api/health');
    const ready = !!(res.flow_ai || false);
    S.flowBlocks.ready = ready;
    if (pill) { pill.className = ready ? 'pill ok' : 'pill key'; pill.textContent = ready ? '● Nano Banana conectado' : 'falta GEMINI_API_KEY'; }
  } catch (err) {
    S.flowBlocks.ready = false; if (pill) { pill.className = 'pill key'; pill.textContent = 'sem conexão'; }
  }
  // Atualiza chip do projeto
  if (chip) {
    if (S.projectId) {
      try {
        const p = await api(`/api/projects/${S.projectId}`);
        chip.textContent = `Projeto: ${esc(p.title || 'sem título')}`;
        chip.style.background = 'rgba(95,217,160,.15)';
        chip.style.color = '#8bf0c0';
      } catch { chip.textContent = 'erro ao carregar projeto'; }
    } else {
      chip.textContent = 'sem projeto aberto';
      chip.style.background = '';
      chip.style.color = '';
    }
  }
  renderFlowBlocksList();
  // Se houver projeto aberto, tenta carregar blocos salvos
  if (S.projectId) {
    try {
      const estado = await api(`/api/flow/blocks/${S.projectId}`);
      S.flowBlocks.blocos = (estado.blocos || []).map(b => ({ ...b, imagem: b.imagem || null, status: b.status || 'pendente' }));
      S.flowBlocks.ratio = estado.ratio || '16:9';
      S.flowBlocks.projectId = S.projectId;
      renderFlowBlocksList();
    } catch { /* sem blocos salvos ainda */ }
  }
}

function renderFlowBlocksList() {
  const host = $('#flowBlocksList'); if (!host) return;
  const count = $('#flowBlocksCount'); if (count) count.textContent = `${S.flowBlocks.blocos.length} bloco${S.flowBlocks.blocos.length === 1 ? '' : 's'}`;
  const galCard = $('#flowBlocksGalleryCard'); const galGrid = $('#flowBlocksGalleryGrid');
  if (!S.flowBlocks.blocos.length) {
    host.innerHTML = '<div class="empty">Nenhum bloco ainda. Cole o roteiro (ou use o SRT do projeto) e clique em "Dividir em blocos e gerar prompts".</div>';
    if (galCard) galCard.hidden = true;
    return;
  }
  host.innerHTML = S.flowBlocks.blocos.map((b, i) => {
    const feito = b.status === 'concluido' && b.imagem;
    const gerando = b.status === 'gerando';
    const btnLabel = feito ? `${ic('refresh')} Refazer imagem` : `${ic('image')} Gerar imagem`;
    const btnCls = feito ? 'btn ghost small' : 'btn primary small';
    const btnDisabled = S.flowBlocks.busy || gerando;
    const imgHtml = b.imagem ? `<img src="${esc(b.imagem.url)}" alt="" referrerpolicy="no-referrer" style="width:100%;height:76px;object-fit:cover;border-radius:8px;border:1px solid var(--line2)">` : `<div style="width:100%;height:76px;border-radius:8px;border:1.5px dashed var(--line2);background:#0a1222;display:grid;place-items:center;color:var(--dim);font-size:11px">sem imagem</div>`;
    const tempo = b.start !== undefined && b.end !== undefined ? `<span class="tiny" style="color:var(--cyan)">⏱ ${fmtTime(b.start)} → ${fmtTime(b.end)}</span>` : '';
    return `<article class="flow-block ${feito ? 'ok' : ''}">
      <div class="spread" style="gap:8px;align-items:center">
        <span class="flow-block-num">${String(i + 1).padStart(2, '0')}</span>
        <div class="flow-block-body" style="min-width:0;flex:1">
          <div class="flow-block-text" style="font:600 13px var(--body);color:#eaf2ff;white-space:pre-wrap;overflow:hidden;text-overflow:ellipsis;max-height:44px">${esc(b.texto || '')}</div>
          ${tempo ? `<div style="margin-top:2px">${tempo}</div>` : ''}
          <div class="flow-block-prompt" style="font:11px var(--mono);color:#9fb0cf;margin-top:4px;white-space:pre-wrap;overflow:hidden;text-overflow:ellipsis;max-height:36px">${esc(b.prompt || '')}</div>
        </div>
        <div class="flow-block-actions" style="display:flex;gap:6px;flex-shrink:0">
          <button type="button" class="${btnCls}" data-flowblock-gen="${esc(b.id)}" ${btnDisabled ? 'disabled' : ''}>${btnLabel}</button>
          ${feito ? `<a class="btn ghost small" href="${esc(b.imagem.url)}" download title="Baixar">${ic('download')}</a>` : ''}
        </div>
        <span class="badge ${feito ? 'ready' : gerando ? 'work' : ''}">${feito ? 'PRONTO' : gerando ? 'GERANDO…' : 'PENDENTE'}</span>
      </div>
      ${imgHtml}
    </article>`;
  }).join('');
  // Galeria de imagens geradas
  const imagens = S.flowBlocks.blocos.filter(b => b.imagem);
  if (galCard && galGrid) {
    if (imagens.length) {
      galCard.hidden = false;
      galGrid.innerHTML = imagens.map(b => `
        <article class="pcard" style="display:flex;flex-direction:column;gap:8px">
          <img src="${esc(b.imagem.url)}" alt="" style="width:100%;height:140px;object-fit:cover;border-radius:10px;border:1px solid var(--line2)">
          <div style="display:flex;gap:8px">
            <a class="btn ghost small" href="${esc(b.imagem.url)}" download>${ic('download')} Baixar</a>
            <button class="btn ghost small" data-flowblock-use="${esc(b.id)}">${ic('box')} Usar na cena</button>
          </div>
          <p class="tiny" style="white-space:pre-wrap;overflow:hidden;text-overflow:ellipsis">${esc(b.prompt || '')}</p>
        </article>
      `).join('');
    } else {
      galCard.hidden = true;
    }
  }
}

async function flowBlocksGenBlocks() {
  const useSrt = $('#flowBlocksUseSrt')?.checked || false;
  const texto = $('#flowBlocksScript')?.value || '';
  if (!S.flowBlocks.ready) return toast('Configure GEMINI_API_KEY na tela de Chaves de API.');
  if (!texto.trim() && !useSrt) return toast('Cole o roteiro ou marque "Usar SRT do projeto".');
  S.flowBlocks.busy = true;
  const btn = $('#flowBlocksGenBtn'); const old = btn.innerHTML;
  btn.disabled = true; btn.innerHTML = '<span class="spin"></span> Processando…';
  $('#flowBlocksProgress').hidden = false;
  try {
    // Upload da imagem de referência, se houver
    let referencePath = null;
    const refInput = $('#flowBlocksRefFile');
    if (refInput && refInput.files && refInput.files[0]) {
      const fd = new FormData(); fd.append('reference', refInput.files[0]);
      const up = await api('/api/flow/upload-reference', { method: 'POST', body: fd });
      referencePath = up.path;
    }
    const res = await jpost('/api/flow/blocks-from-script', {
      script: texto,
      max_blocks: Number($('#flowBlocksMaxBlocks')?.value || 20),
      ratio: $('#flowBlocksRatio')?.value || '16:9',
      project_id: S.projectId || null,
      use_srt: useSrt,
      reference_image: referencePath,
    });
    S.flowBlocks.blocos = (res.blocos || []).map(b => ({ ...b, imagem: null, status: 'pendente' }));
    S.flowBlocks.ratio = $('#flowBlocksRatio')?.value || '16:9';
    S.flowBlocks.projectId = S.projectId || null;
    renderFlowBlocksList();
    toast(`${S.flowBlocks.blocos.length} blocos criados ${res.source === 'srt' ? 'do SRT' : 'do roteiro'}.`);
  } catch (err) { toast(err.message); } finally {
    S.flowBlocks.busy = false;
    btn.disabled = false; btn.innerHTML = old;
    $('#flowBlocksProgress').hidden = true;
  }
}

async function flowBlocksGenerateImage(blockId) {
  const b = S.flowBlocks.blocos.find(x => x.id === blockId); if (!b) return;
  if (S.flowBlocks.busy) return toast('Espere a geração atual terminar.');
  S.flowBlocks.busy = true;
  const idx = S.flowBlocks.blocos.findIndex(x => x.id === blockId);
  S.flowBlocks.blocos[idx].status = 'gerando';
  renderFlowBlocksList();
  try {
    const res = await jpost('/api/flow/generate-block-image', {
      block_id: blockId,
      prompt: b.prompt,
      ratio: S.flowBlocks.ratio || '16:9',
      project_id: S.projectId || null,
    });
    S.flowBlocks.blocos[idx].imagem = res.item;
    S.flowBlocks.blocos[idx].status = 'concluido';
    renderFlowBlocksList();
    toast(`Imagem do bloco ${blockId} gerada.`);
  } catch (err) {
    S.flowBlocks.blocos[idx].status = 'pendente';
    renderFlowBlocksList();
    toast(err.message);
  } finally {
    S.flowBlocks.busy = false;
  }
}

/* ---------- Flow Agent (extensão Chrome) */
async function loadFlowAgentConfig() {
  const cfg = await api('/api/flow-agent/config');
  S.flowAgentCfg = cfg;
  const enabled = $('#flowAgentEnabled');
  const urlInp = $('#flowAgentUrl');
  const statusPill = $('#flowAgentStatusPill');
  const statusMsg = $('#flowAgentStatusMsg');
  if (enabled) enabled.checked = !!cfg.ativo;
  if (urlInp) urlInp.value = cfg.url || 'http://localhost:8001';
  if (statusPill) {
    statusPill.className = cfg.ativo ? 'pill ok' : 'pill off';
    statusPill.textContent = cfg.ativo ? '● Ativado' : '○ Desativado';
  }
  if (statusMsg) statusMsg.textContent = cfg.ultimo_status || 'Não testado';
  renderFlowPills();
}
async function testFlowAgentConnection() {
  const urlInp = $('#flowAgentUrl');
  const enabled = $('#flowAgentEnabled');
  const btn = $('#flowAgentTestBtn');
  const msg = $('#flowAgentStatusMsg');
  const detail = $('#flowAgentStatusDetail');
  const statusPill = $('#flowAgentStatusPill');
  if (!urlInp || !urlInp.value.trim()) return toast('Informe a URL do servidor Flow Agent.');
  btn.disabled = true; btn.innerHTML = '<span class="spin"></span> Testando…';
  detail.hidden = true;
  try {
    const res = await jpost('/api/flow-agent/config', {
      ativo: enabled.checked,
      url: urlInp.value.trim(),
    });
    const st = await api('/api/flow-agent/status');
    if (st.online) {
      statusPill.className = 'pill ok';
      statusPill.textContent = '● Online';
      msg.textContent = 'Servidor respondendo.';
      detail.hidden = false;
      detail.innerHTML = `<b>Contas conectadas:</b> ${st.contas_conectadas || 0}<br><b>URL:</b> ${st.url}<br><b>Status:</b> ${st.ultimo_status}`;
      toast('Flow Agent online!');
    } else {
      statusPill.className = 'pill off';
      statusPill.textContent = '○ Offline';
      msg.textContent = 'Servidor não respondeu.';
      detail.hidden = false;
      detail.innerHTML = `<b>Erro:</b> ${st.ultimo_status || 'Desconhecido'}<br>Certifique-se de que o servidor está rodando em ${urlInp.value.trim()}`;
      toast('Flow Agent não respondeu.');
    }
  } catch (err) {
    statusPill.className = 'pill off';
    statusPill.textContent = '○ Erro';
    msg.textContent = err.message;
    toast(err.message);
  } finally {
    btn.disabled = false; btn.innerHTML = `${ic('chrome')} Testar conexão`;
  }
}
async function flowAgentGenerateImage(prompt, aspect, count) {
  const cfg = await api('/api/flow-agent/config');
  if (!cfg.ativo) throw new Error('Flow Agent não está ativado.');
  const res = await jpost('/api/flow-agent/image', { prompt, aspect, count });
  return res;
}
async function flowAgentGenerateVideo(prompt, aspect, duration, quality, startImage) {
  const cfg = await api('/api/flow-agent/config');
  if (!cfg.ativo) throw new Error('Flow Agent não está ativado.');
  const res = await jpost('/api/flow-agent/video', { prompt, aspect, duration, quality, start_image: startImage });
  return res;
}

/* ---------- Listeners View Flow Blocos */
$('#viewFlowBlocks')?.addEventListener('click', async e => {
  const genBtn = e.target.closest('[data-flowblock-gen]');
  if (genBtn) { e.stopPropagation(); return flowBlocksGenerateImage(genBtn.dataset.flowblockGen); }
  const useBtn = e.target.closest('[data-flowblock-use]');
  if (useBtn) { e.stopPropagation(); toast('Imagem copiada para a galeria. Use-a na edição do projeto.'); }
});
$('#viewFlowBlocks')?.addEventListener('click', async e => {
  if (e.target.closest('#flowBlocksGenBtn')) return flowBlocksGenBlocks();
  if (e.target.closest('#flowBlocksRefreshBtn')) return loadFlowBlocksView();
});
$('#viewFlowBlocks')?.addEventListener('change', e => {
  if (e.target.id === 'flowBlocksRefFile') {
    const name = document.getElementById('flowBlocksRefName');
    if (name) name.textContent = e.target.files[0] ? `✓ ${e.target.files[0].name}` : 'Nenhuma imagem escolhida';
  }
});

/* ---------- Listeners View Keys (Flow Agent) */
$('#viewKeys')?.addEventListener('click', async e => {
  if (e.target.closest('#flowAgentTestBtn')) return testFlowAgentConnection();
});
$('#viewKeys')?.addEventListener('change', e => {
  if (e.target.id === 'flowAgentEnabled') {
    const btn = $('#flowAgentTestBtn');
    if (btn) btn.disabled = false;
  }
});

/* ---------- Listeners View Flow (card do Flow Agent) */
$('#viewFlow')?.addEventListener('click', async e => {
  if (e.target.closest('#flowAgentTestBtn')) return testFlowAgentConnection();
});
$('#viewFlow')?.addEventListener('change', e => {
  if (e.target.id === 'flowAgentEnabled') {
    const btn = $('#flowAgentTestBtn');
    if (btn) btn.disabled = false;
  }
});

/* ---------- View Skills de Roteiro */
async function loadSkillsView() {
  const list = $('#skillsList');
  const count = $('#skillsCount');
  try {
    const res = await api('/api/skills');
    const skillsList = res.skills || [];
    if (count) count.textContent = skillsList.length + ' skill' + (skillsList.length === 1 ? '' : 's');
    if (!skillsList.length) {
      list.innerHTML = '<div class="empty">Nenhuma skill encontrada.</div>';
      return;
    }
    list.innerHTML = skillsList.map(s => `
      <article class="skill-card ${s.id === S.skills.selected ? 'selected' : ''}" data-skill-id="${esc(s.id)}">
        <div class="spread" style="gap:8px;align-items:flex-start">
          <div style="flex:1;min-width:0">
            <div class="skill-card-title" style="font:700 13px var(--head);color:#eaf2ff;white-space:pre-wrap;overflow:hidden;text-overflow:ellipsis">${esc(s.name)}</div>
            <div class="skill-card-cat" style="font:500 10px var(--mono);color:#9fb0cf;margin-top:2px">${esc(s.category)}</div>
            <div class="skill-card-desc" style="font:11.5px var(--body);color:#aebbd4;margin-top:4px;white-space:pre-wrap;overflow:hidden;text-overflow:ellipsis;max-height:60px">${esc(s.description)}</div>
          </div>
          <span class="badge ${s.id === S.skills.selected ? 'ready' : ''}">${s.id === S.skills.selected ? 'SELECIONADA' : 'SELECIONAR'}</span>
        </div>
      </article>
    `).join('');
    S.skillsList = skillsList;
  } catch (err) {
    list.innerHTML = '<div class="empty">Erro ao carregar skills: ' + esc(err.message) + '</div>';
  }
}

async function selectSkill(skillId) {
  S.skills = S.skills || { selected: null };
  S.skills.selected = skillId;
  loadSkillsView();
  const nome = (S.skillsList || []).find(s => s.id === skillId)?.name || skillId;
  toast('Skill selecionada: ' + nome);
}

async function generateSkillScript() {
  const skillId = S.skills?.selected;
  if (!skillId) return toast('Selecione uma skill primeiro.');
  const topic = $('#skillTopicInput')?.value?.trim();
  if (!topic) return toast('Digite o tópico do vídeo.');
  const language = $('#skillLanguageSelect')?.value || 'pt-BR';
  const charCount = $('#skillCharCountInput')?.value ? Number($('#skillCharCountInput').value) : null;
  const btn = $('#skillGenerateBtn');
  const progress = $('#skillProgress');
  const msg = $('#skillMsg');
  btn.disabled = true;
  progress.hidden = false;
  try {
    const res = await jpost('/api/skills/generate', { skill_id: skillId, topic, language, char_count: charCount });
    $('#skillResult').hidden = false;
    $('#skillResultMeta').textContent = res.skill_name + ' · ' + res.topic + ' · ' + res.language + (res.char_count ? ' · ' + res.char_count + ' caracteres' : '');
    if (res.generated) {
      msg.textContent = 'Roteiro gerado com sucesso!';
      $('#skillResultText').value = res.message || '';
    } else {
      msg.textContent = 'Skill carregada (geração automática indisponível).';
      $('#skillResultText').value = res.full_method || res.method || res.message || '';
      toast('Configure a GEMINI_API_KEY para gerar o roteiro automaticamente. O método da skill foi carregado.');
    }
  } catch (err) {
    msg.textContent = 'Erro ao gerar.';
    toast(err.message);
  } finally {
    btn.disabled = false;
    progress.hidden = true;
  }
}

async function useSkillScript() {
  const text = $('#skillResultText')?.value;
  if (!text) return toast('Nenhum roteiro gerado.');
  // Anexa o roteiro na aba Arquivos de "Novo vídeo"
  const blob = new Blob([text], { type: 'text/plain; charset=utf-8' });
  const file = new File([blob], 'roteiro_skill.txt', { type: 'text/plain' });
  setFile('script', file);
  if (CREATE) { CREATE.tab = 'files'; }
  showView('create');
  if (CREATE) renderPane(CREATE);
  updateCreateBar();
  toast('Roteiro anexado em "Novo vídeo" → Arquivos como roteiro_skill.txt.');
}

async function copySkillScript() {
  const text = $('#skillResultText')?.value;
  if (!text) return;
  await navigator.clipboard.writeText(text);
  toast('Texto copiado para a área de transferência.');
}

/* ---------- Listeners View Skills */
$('#viewSkills')?.addEventListener('click', async e => {
  const skillCard = e.target.closest('[data-skill-id]');
  if (skillCard) {
    e.stopPropagation();
    await selectSkill(skillCard.dataset.skillId);
    return;
  }
  if (e.target.closest('#skillGenerateBtn')) return generateSkillScript();
  if (e.target.closest('#skillUseBtn')) return useSkillScript();
  if (e.target.closest('#skillCopyBtn')) return copySkillScript();
  if (e.target.closest('#skillsRefreshBtn')) return loadSkillsView();
});
$('#viewSkills')?.addEventListener('click', async e => {
  if (e.target.closest('#skillsRefreshBtn')) return loadSkillsView();
});

/* ---------- View Groq (transcrição avulsa) */
$('#viewGroq')?.addEventListener('click', async e => {
  const use = e.target.closest('[data-groq-use]');
  if (use) return groqUseNewVideo(use.dataset.groqUse);
  if (e.target.closest('#groqSubmit')) return groqSubmit();
  if (e.target.closest('#groqRefreshBtn')) return loadGroqView();
});
$('#viewGroq')?.addEventListener('change', e => {
  if (e.target.id === 'groqAudio') {
    S.groq.file = e.target.files[0] || null;
    const name = document.getElementById('groqAudioName');
    if (name) name.textContent = S.groq.file ? `✓ ${S.groq.file.name}` : 'Nenhum arquivo escolhido';
    const drop = document.getElementById('groqDrop'); if (drop) drop.classList.toggle('filled', !!S.groq.file);
  } else if (e.target.id === 'groqScriptFile') {
    S.groq.scriptFile = e.target.files[0] || null;
    const name = document.getElementById('groqScriptName');
    if (name) name.textContent = S.groq.scriptFile ? `✓ ${S.groq.scriptFile.name}` : 'Nenhum arquivo escolhido';
  } else if (e.target.id === 'groqModel') {
    S.groq.model = e.target.value;
  } else if (e.target.id === 'groqLanguage') {
    S.groq.language = e.target.value;
  } else if (e.target.id === 'groqMode') {
    S.groq.mode = e.target.value;
  }
});
$('#viewGroq')?.addEventListener('input', e => {
  if (e.target.id === 'groqScriptText') S.groq.scriptText = e.target.value;
});

async function init() {
  S.healthStatus = 'checking';
  S.healthError = '';
  S.catalogStatus = 'loading';
  S.catalog = null;
  renderHealth();

  // A saúde do servidor é independente do catálogo: uma falha no catálogo
  // não pode deixar o indicador preso em "Verificando…".
  const [, catalogResult] = await Promise.allSettled([
    refreshHealth(),
    api('/api/catalog').then(catalog => {
      S.catalog = catalog;
      S.catalogStatus = 'loaded';
      renderHealth();
      return catalog;
    }).catch(err => {
      S.catalog = null;
      S.catalogStatus = 'error';
      renderHealth();
      throw err;
    }),
  ]);

  if (catalogResult.status === 'rejected') {
    const err = catalogResult.reason;
    if (!String(err?.message || err).includes('login')) {
      const prefix = S.healthStatus === 'online' ? 'Servidor conectado, mas' : 'Não foi possível iniciar o catálogo:';
      toast(`${prefix} ${err?.message || 'falha ao carregar os bancos de mídia.'}`);
    }
    return;
  }

  try {
    await loadMusic();
    if (!CREATE) {
      CREATE = { cfg: defaultCfg(), container: $('#createPane'), tabsEl: $('#createTabs'), tab: 'files', projectId: null };
      EDIT = { cfg: defaultCfg(), container: $('#editorPane'), tabsEl: $('#editorTabs'), tab: 'style', projectId: null };
      bindContext(CREATE); bindContext(EDIT);
    }
    hydrateIcons(); renderHealth(); renderPane(CREATE); updateSummary(); updateCreateBar(); await loadProjects();
    const m = location.hash.match(/#p=([a-f0-9]{32})/); if (m) openProject(m[1]);
  } catch (err) {
    if (!String(err?.message || err).includes('login')) toast(err?.message || String(err));
  }
}
init();
