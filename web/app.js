let currentView = 'Resumen', activeAgent = null, generation = 0;
let lang = localStorage.getItem('mike-lang') === 'en' ? 'en' : 'es';
const content = document.querySelector('#content');
const error = document.querySelector('#error');
const names = {mike:'Mike',usbestroofing:'US Best Roofing',centrotai:'Centro TAI',pacific:'Pacific',gabriels:'Gabriels'};
const escapeHtml = s => String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

const I18N = {
  es: {
    doc_title: 'Mike · Control',
    nav_workspace: 'ESPACIO DE TRABAJO',
    nav_overview: 'Vista general',
    nav_chat_mike: 'Chat con Mike',
    nav_wp_agents: 'AGENTES WORDPRESS',
    nav_vercel_agents: 'ASTRO / VERCEL',
    header_ops: 'Centro de operaciones',
    header_badge: 'Chat y control de disponibilidad',
    tab_overview: 'Resumen',
    tab_incidents: 'Incidentes',
    tab_approvals: 'Aprobaciones',
    tab_memory: 'Memoria',
    tab_settings: 'Configuración',
    footer_note: 'El chat no ejecuta órdenes ni realiza cambios en tus sitios. No ingreses credenciales en el chat.',
    hero_title: 'Todo bajo tu supervisión.',
    loading: 'Consultando…',
    err_409: 'Ya hay una respuesta en curso en este chat. Esperá antes de enviar.',
    err_401: 'Sesión no autorizada. Recargá e ingresá tus credenciales.',
    err_generic: 'No se pudo completar la consulta. Revisá la conexión y el estado del backend.',
    no_checks: 'Sin mediciones',
    stale_check: 'Medición vencida',
    responded: 'Respondió',
    redirect: 'Redirección',
    check_conn: 'Revisar conexión',
    no_response: 'sin respuesta',
    last_check: 'Última consulta',
    no_check_yet: 'Todavía no se realizó una comprobación.',
    online: 'Online',
    open_chat: 'Abrir chat ↗',
    no_saved_checks: 'Todavía no hay mediciones guardadas.',
    pg_connected: 'Conectado',
    pg_desc: 'Historial central de conversaciones',
    pilot_site: 'SITIO PILOTO',
    monitoring: 'MONITOREO',
    enabled: 'Activado',
    disabled: 'Desactivado',
    scan_every: 'Consulta HTTP cada {n} min',
    monitored_sites: 'Estado de sitios monitoreados',
    you_decide: 'Vos decidís',
    exec_approval: 'Las acciones de escritura siempre pasan por la pestaña Aprobaciones antes de ejecutarse.',
    exec_disabled: 'El ejecutor está deshabilitado. El chat no autoriza ni ejecuta acciones.',
    memory_title: 'Historial persistente',
    memory_p1: 'Los mensajes de cada chat ({agents}) se guardan separados en PostgreSQL. Abrí cada conversación para consultar los últimos 100 mensajes.',
    memory_p2: 'Las acciones aprobadas y mediciones de disponibilidad también quedan guardadas en PostgreSQL. Con OpenAI configurado, cada envío comparte hasta 40 mensajes recientes de ese chat (máximo 24.000 caracteres) para generar una respuesta.',
    edit: 'Editar',
    remove: 'Quitar',
    save_changes: 'Guardar cambios',
    confirm_remove_site: '¿Quitar este sitio del panel?',
    env_vars: 'Variables en Easypanel',
    monitoring_label: 'Monitoreo',
    connections: 'Conexiones',
    conn_pg: 'PostgreSQL: conectado',
    conn_ai: 'OpenAI',
    ai_configured: 'configurado; se verifica al enviar',
    not_configured: 'sin configurar',
    conn_tg: 'Telegram: sin conectar',
    conn_ssh: 'SSH WordPress (solo lectura)',
    active: 'activo',
    not_connected: 'sin conectar',
    conn_http: 'Monitoreo HTTP',
    enabled_lower: 'activado',
    disabled_lower: 'desactivado',
    conn_wp: 'WordPress Bridge',
    conn_git: 'GitHub / Vercel GitOps',
    creds_note: 'Las credenciales se configuran en Easypanel, nunca en este chat.',
    add_site_title: 'Agregar sitio al panel',
    add_site_desc: 'Creá un chat nuevo organizado en WordPress o Astro / Vercel sin editar código.',
    ph_name: 'Nombre (ej: Exodus Remodeling)',
    ph_id: 'ID corto (ej: exodus)',
    ph_url: 'URL monitoreo (opcional: https://...)',
    add_site_btn: 'Agregar sitio',
    no_pending_title: 'Sin acciones pendientes',
    no_pending_desc: 'Cuando un agente proponga un cambio en WordPress (guardar página, crear respaldo, etc.), aparecerá acá para que lo apruebes o rechaces.',
    approve_exec: 'Aprobar y ejecutar',
    executing: 'Ejecutando…',
    reject: 'Rechazar',
    status_label: 'Estado',
    expires_label: 'Vence',
    no_incidents_title: 'Sin incidentes recientes',
    no_incidents_desc: 'No se registraron caídas ni respuestas fuera de rango en los sitios monitoreados.',
    chat_hint: 'Historial en PostgreSQL · Respuestas de IA si OpenAI está configurado.',
    clear_chat: 'Limpiar chat',
    confirm_clear_chat: '¿Borrar todos los mensajes de este chat?',
    loading_history: 'Cargando historial…',
    msg_label: 'Mensaje',
    msg_placeholder: 'Escribí tu mensaje…',
    send_btn: 'Enviar ↑',
    sending_btn: 'Respondiendo…',
    you: 'Vos',
    system: 'Sistema',
    no_messages: 'Esta conversación aún no tiene mensajes.',
    ai_missing_key: 'Mensaje guardado. Falta configurar OPENAI_API_KEY en Easypanel.'
  },
  en: {
    doc_title: 'Mike · Control',
    nav_workspace: 'WORKSPACE',
    nav_overview: 'Overview',
    nav_chat_mike: 'Chat with Mike',
    nav_wp_agents: 'WORDPRESS AGENTS',
    nav_vercel_agents: 'ASTRO / VERCEL',
    header_ops: 'Operations Center',
    header_badge: 'Chat & uptime monitoring',
    tab_overview: 'Overview',
    tab_incidents: 'Incidents',
    tab_approvals: 'Approvals',
    tab_memory: 'Memory',
    tab_settings: 'Settings',
    footer_note: 'Chat does not run commands or make changes to your sites. Do not enter credentials in chat.',
    hero_title: 'Everything under your supervision.',
    loading: 'Loading…',
    err_409: 'A response is already in progress in this chat. Please wait before sending.',
    err_401: 'Unauthorized session. Reload and enter your credentials.',
    err_generic: 'Could not complete request. Check your connection and backend status.',
    no_checks: 'No checks yet',
    stale_check: 'Stale check',
    responded: 'Responded',
    redirect: 'Redirect',
    check_conn: 'Check connection',
    no_response: 'no response',
    last_check: 'Last check',
    no_check_yet: 'No check has been performed yet.',
    online: 'Online',
    open_chat: 'Open chat ↗',
    no_saved_checks: 'No saved checks yet.',
    pg_connected: 'Connected',
    pg_desc: 'Central conversation history',
    pilot_site: 'PILOT SITE',
    monitoring: 'MONITORING',
    enabled: 'Enabled',
    disabled: 'Disabled',
    scan_every: 'HTTP check every {n} min',
    monitored_sites: 'Monitored sites status',
    you_decide: 'You decide',
    exec_approval: 'Write actions always go through the Approvals tab before executing.',
    exec_disabled: 'Executor is disabled. Chat does not authorize or run actions.',
    memory_title: 'Persistent history',
    memory_p1: 'Messages for each chat ({agents}) are stored separately in PostgreSQL. Open any conversation to view the last 100 messages.',
    memory_p2: 'Approved actions and uptime checks are also saved in PostgreSQL. With OpenAI configured, each message shares up to 40 recent messages from that chat (max 24,000 characters) to generate a response.',
    edit: 'Edit',
    remove: 'Remove',
    save_changes: 'Save changes',
    confirm_remove_site: 'Remove this site from the panel?',
    env_vars: 'Easypanel env vars',
    monitoring_label: 'Monitoring',
    connections: 'Connections',
    conn_pg: 'PostgreSQL: connected',
    conn_ai: 'OpenAI',
    ai_configured: 'configured; verified on send',
    not_configured: 'not configured',
    conn_tg: 'Telegram: not connected',
    conn_ssh: 'WordPress SSH (read-only)',
    active: 'active',
    not_connected: 'not connected',
    conn_http: 'HTTP Monitoring',
    enabled_lower: 'enabled',
    disabled_lower: 'disabled',
    conn_wp: 'WordPress Bridge',
    conn_git: 'GitHub / Vercel GitOps',
    creds_note: 'Credentials are configured in Easypanel, never in this chat.',
    add_site_title: 'Add site to panel',
    add_site_desc: 'Create a new chat organized under WordPress or Astro / Vercel without editing code.',
    ph_name: 'Name (e.g., Exodus Remodeling)',
    ph_id: 'Short ID (e.g., exodus)',
    ph_url: 'Monitoring URL (optional: https://...)',
    add_site_btn: 'Add site',
    no_pending_title: 'No pending actions',
    no_pending_desc: 'When an agent proposes a WordPress change (save page, create backup, etc.), it will appear here for you to approve or reject.',
    approve_exec: 'Approve & execute',
    executing: 'Executing…',
    reject: 'Reject',
    status_label: 'Status',
    expires_label: 'Expires',
    no_incidents_title: 'No recent incidents',
    no_incidents_desc: 'No outages or out-of-range responses were recorded on monitored sites.',
    chat_hint: 'PostgreSQL history · AI responses if OpenAI is configured.',
    clear_chat: 'Clear chat',
    confirm_clear_chat: 'Delete all messages in this chat?',
    loading_history: 'Loading history…',
    msg_label: 'Message',
    msg_placeholder: 'Type your message…',
    send_btn: 'Send ↑',
    sending_btn: 'Replying…',
    you: 'You',
    system: 'System',
    no_messages: 'This conversation has no messages yet.',
    ai_missing_key: 'Message saved. OPENAI_API_KEY is not configured in Easypanel.'
  }
};

const t = (key, vars = {}) => {
  let s = (I18N[lang] && I18N[lang][key]) || I18N.es[key] || key;
  for (const [k, v] of Object.entries(vars)) s = s.replace(`{${k}}`, v);
  return s;
};
const locale = () => lang === 'en' ? 'en-US' : 'es';
const fmtDate = d => new Date(d).toLocaleString(locale());
const tabTitle = tab => ({
  Resumen: t('hero_title'),
  Incidentes: t('tab_incidents'),
  Aprobaciones: t('tab_approvals'),
  Memoria: t('tab_memory'),
  'Configuración': t('tab_settings')
}[tab] || tab);

function applyStaticI18n() {
  document.documentElement.lang = lang === 'en' ? 'en-US' : 'es';
  document.title = t('doc_title');
  document.querySelectorAll('[data-i18n]').forEach(el => {
    el.textContent = t(el.dataset.i18n);
  });
  document.querySelectorAll('[data-lang]').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.lang === lang);
  });
}

function setLang(next) {
  lang = next === 'en' ? 'en' : 'es';
  localStorage.setItem('mike-lang', lang);
  applyStaticI18n();
  if (activeAgent) chat(activeAgent);
  else view(currentView);
}

function renderSidebar(agents) {
  if(!Array.isArray(agents)||!agents.length)return;
  agents.forEach(a=>{names[a.id]=a.name;});
  const wpBox=document.querySelector('#nav-wordpress');
  const vcBox=document.querySelector('#nav-vercel');
  if(wpBox)wpBox.innerHTML=agents.filter(a=>a.kind==='wordpress').map(a=>`<button data-chat="${escapeHtml(a.id)}">${escapeHtml(a.name)}</button>`).join('');
  if(vcBox)vcBox.innerHTML=agents.filter(a=>a.kind==='vercel').map(a=>`<button data-chat="${escapeHtml(a.id)}">${escapeHtml(a.name)}</button>`).join('');
  document.querySelectorAll('aside [data-chat]').forEach(b=>b.addEventListener('click',()=>chat(b.dataset.chat)));
  select();
}
async function api(path, options={}) {
  const response = await fetch(path,{...options, headers:{'Content-Type':'application/json','X-Mike-Request':'1',...options.headers}});
  if (!response.ok) throw new Error(response.status===409?t('err_409'):response.status===401?t('err_401'):t('err_generic'));
  return response.json();
}
function select() {
  document.querySelectorAll('[data-view]').forEach(b=>b.classList.toggle('active',!activeAgent && b.dataset.view===currentView));
  document.querySelectorAll('[data-chat]').forEach(b=>b.classList.toggle('active',b.dataset.chat===activeAgent));
}
async function view(tab) {
  const ticket=++generation; currentView=tab;activeAgent=null;select();error.textContent='';
  document.querySelector('#title').textContent=tabTitle(tab);
  content.textContent=t('loading');
  try {
    const status=await api('/api/status');if(ticket!==generation)return;
    renderSidebar(status.agents);
    if(tab==='Resumen') {
      const check=status.latest_check, age=check ? Date.now()-Date.parse(check.checked_at) : null;
      const label=!check?t('no_checks'):age>30*60*1000?t('stale_check'):check.status==='ok'?t('responded'):check.status==='redirect'?t('redirect'):t('check_conn');
      const detail=check ? `${t('last_check')}: ${escapeHtml(fmtDate(check.checked_at))} · HTTP ${escapeHtml(check.http_status ?? t('no_response'))} · ${escapeHtml(check.duration_ms)} ms` : t('no_check_yet');
      const checksHtml=(status.site_checks||[]).length
        ? (status.site_checks||[]).map(c=>{
            const st=c.status==='ok'?t('online'):c.status==='redirect'?t('redirect'):t('check_conn');
            return `<div class="row" style="padding:8px 0;border-bottom:1px solid #eceeed"><div><strong>${escapeHtml(names[c.site_id]||c.site_id)}</strong><div class="muted" style="font-size:12px">${escapeHtml(st)} · HTTP ${escapeHtml(c.http_status ?? t('no_response'))} · ${escapeHtml(c.duration_ms)} ms · ${escapeHtml(fmtDate(c.checked_at))}</div></div><button data-open-site="${escapeHtml(c.site_id)}">${t('open_chat')}</button></div>`;
          }).join('')
        : `<p class="muted">${t('no_saved_checks')}</p>`;
      content.innerHTML=`<div class="stats"><div class="card"><small>POSTGRESQL</small><div class="value">${t('pg_connected')}</div><small>${t('pg_desc')}</small></div><div class="card"><small>${t('pilot_site')}</small><div class="value">${label}</div><small>${detail}</small></div><div class="card"><small>${t('monitoring')}</small><div class="value">${status.monitoring==='enabled'?t('enabled'):t('disabled')}</div><small>${t('scan_every',{n:status.scan_interval_minutes})}</small></div></div><section class="card"><h2>${t('monitored_sites')}</h2>${checksHtml}</section><section class="card"><h2>${t('you_decide')}</h2><p>${status.execution==='approval_required'?t('exec_approval'):t('exec_disabled')}</p></section>`;
      content.querySelectorAll('[data-open-site]').forEach(b=>b.addEventListener('click',()=>chat(b.dataset.openSite)));
    }
    else if(tab==='Memoria'){
      const agentNames=(status.agents||[]).map(a=>escapeHtml(a.name)).join(', ');
      content.innerHTML=`<section class="card"><h2>${t('memory_title')}</h2><p>${t('memory_p1',{agents:agentNames})}</p><p>${t('memory_p2')}</p></section>`;
    }
    else if(tab==='Configuración'){
      const siteRows=(status.agents||[]).filter(a=>a.kind!=='system').map(a=>{
        const prefix=a.id.toUpperCase();
        const envHint=a.kind==='wordpress'
          ? `${prefix}_WP_URL + ${prefix}_WP_BRIDGE_SECRET`
          : `${prefix}_GITHUB_REPO + ${prefix}_GITHUB_TOKEN`;
        const actions=`<div style="display:flex;gap:6px"><button data-edit-site="${escapeHtml(a.id)}" style="background:#eee;color:#222">${t('edit')}</button><button data-del-site="${escapeHtml(a.id)}" style="background:#eee;color:#222">${t('remove')}</button></div>`;
        return `<div class="row" style="padding:8px 0;border-bottom:1px solid #eceeed"><div><strong>${escapeHtml(a.name)}</strong> <span class="muted">(${escapeHtml(a.kind==='wordpress'?'WordPress':'Astro / Vercel')} · ${escapeHtml(a.id)})</span><div class="muted" style="font-size:12px">${t('env_vars')}: <code>${escapeHtml(envHint)}</code>${a.url?` · ${t('monitoring_label')}: `+escapeHtml(a.url):''}</div></div>${actions}</div>`;
      }).join('');
      content.innerHTML=`<section class="card"><h2>${t('connections')}</h2><p>${t('conn_pg')}<br>${t('conn_ai')}: ${status.ai==='configured'?t('ai_configured'):t('not_configured')}<br>${t('conn_tg')}<br>${t('conn_ssh')}: ${status.ssh==='read_only'?t('active')+' ('+escapeHtml((status.ssh_sites||[]).map(s=>names[s]||s).join(', '))+')':t('not_connected')}<br>${t('conn_http')}: ${status.monitoring==='enabled'?t('enabled_lower'):t('disabled_lower')}<br>${t('conn_wp')}: ${(status.wp_sites||[]).length?escapeHtml((status.wp_sites||[]).map(s=>names[s]||s).join(', ')):t('not_configured')}<br>${t('conn_git')}: ${(status.git_sites||[]).length?escapeHtml((status.git_sites||[]).map(s=>names[s]||s).join(', ')):t('not_configured')}</p><p>${t('creds_note')}</p></section><section class="card"><h2>${t('add_site_title')}</h2><p class="muted">${t('add_site_desc')}</p><form id="add-site-form" style="display:flex;flex-wrap:wrap;gap:8px;margin-top:10px"><input name="name" placeholder="${t('ph_name')}" maxlength="80" required style="flex:2;min-width:160px;padding:8px;border:1px solid #d7dcd9;border-radius:8px"><input name="id" placeholder="${t('ph_id')}" pattern="[a-z0-9][a-z0-9_-]{1,31}" maxlength="32" required style="flex:1;min-width:120px;padding:8px;border:1px solid #d7dcd9;border-radius:8px"><input name="url" type="url" placeholder="${t('ph_url')}" maxlength="300" style="flex:2;min-width:200px;padding:8px;border:1px solid #d7dcd9;border-radius:8px"><select name="kind" style="padding:8px;border:1px solid #d7dcd9;border-radius:8px"><option value="wordpress">WordPress</option><option value="vercel">Astro / Vercel</option></select><button type="submit">${t('add_site_btn')}</button></form><div style="margin-top:16px">${siteRows}</div></section>`;
      document.querySelector('#add-site-form')?.addEventListener('submit',async e=>{
        e.preventDefault();
        const fd=new FormData(e.currentTarget);
        error.textContent='';
        try{
          await api('/api/sites',{method:'POST',body:JSON.stringify({id:String(fd.get('id')||'').trim().toLowerCase(),name:String(fd.get('name')||'').trim(),kind:String(fd.get('kind')||'wordpress'),url:String(fd.get('url')||'').trim()})});
          if(ticket===generation)await view('Configuración');
        }catch(err){if(ticket===generation)error.textContent=err.message;}
      });
      content.querySelectorAll('[data-edit-site]').forEach(btn=>btn.addEventListener('click',()=>{
        const target=(status.agents||[]).find(a=>a.id===btn.dataset.editSite);
        const form=document.querySelector('#add-site-form');
        if(!target||!form)return;
        form.elements.name.value=target.name||'';
        form.elements.id.value=target.id||'';
        form.elements.url.value=target.url||'';
        form.elements.kind.value=target.kind||'wordpress';
        form.querySelector('button[type="submit"]').textContent=t('save_changes');
        form.scrollIntoView({behavior:'smooth',block:'center'});
      }));
      content.querySelectorAll('[data-del-site]').forEach(btn=>btn.addEventListener('click',async()=>{
        if(!confirm(t('confirm_remove_site')))return;
        btn.disabled=true;error.textContent='';
        try{await api('/api/sites/'+btn.dataset.delSite,{method:'DELETE'});if(ticket===generation)await view('Configuración');}
        catch(err){if(ticket===generation){error.textContent=err.message;btn.disabled=false;}}
      }));
    }
    else if(tab==='Aprobaciones'){
      const data=await api('/api/proposals');if(ticket!==generation)return;
      const items=data.proposals||[];
      if(!items.length){
        content.innerHTML=`<section class="card"><h2>${t('no_pending_title')}</h2><p>${t('no_pending_desc')}</p></section>`;
      }else{
        content.innerHTML=items.map(p=>{
          const siteLabel=escapeHtml(names[p.site_id]||p.site_id);
          const paramsStr=escapeHtml(JSON.stringify(p.params_json||{},null,2));
          const actions=p.status==='pending'
            ? `<div class="row" style="margin-top:12px;gap:8px;justify-content:flex-start"><button data-approve="${p.id}">${t('approve_exec')}</button><button data-reject="${p.id}" style="background:#eee;color:#222">${t('reject')}</button></div>`
            : '';
          const resultStr=p.result_json?`<pre style="margin-top:8px;white-space:pre-wrap;font-size:12px;background:#f6f7f6;padding:8px;border-radius:6px">${escapeHtml(JSON.stringify(p.result_json,null,2))}</pre>`:'';
          return `<section class="card"><div class="row"><div><strong>#${p.id} · ${siteLabel} · ${escapeHtml(p.tool_name)}</strong><div class="muted" style="font-size:12px">${t('status_label')}: ${escapeHtml(p.status)} · ${t('expires_label')}: ${escapeHtml(fmtDate(p.expires_at))}</div></div></div><pre style="margin-top:8px;white-space:pre-wrap;font-size:12px;background:#f6f7f6;padding:8px;border-radius:6px">${paramsStr}</pre>${resultStr}${actions}</section>`;
        }).join('');
        content.querySelectorAll('[data-approve]').forEach(btn=>btn.addEventListener('click',async()=>{
          btn.disabled=true;btn.textContent=t('executing');error.textContent='';
          try{await api('/api/proposals/'+btn.dataset.approve+'/approve',{method:'POST'});if(ticket===generation)await view('Aprobaciones');}
          catch(e){if(ticket===generation){error.textContent=e.message;btn.disabled=false;btn.textContent=t('approve_exec');}}
        }));
        content.querySelectorAll('[data-reject]').forEach(btn=>btn.addEventListener('click',async()=>{
          btn.disabled=true;error.textContent='';
          try{await api('/api/proposals/'+btn.dataset.reject+'/reject',{method:'POST'});if(ticket===generation)await view('Aprobaciones');}
          catch(e){if(ticket===generation){error.textContent=e.message;btn.disabled=false;}}
        }));
      }
    }
    else {
      const inc=status.incidents||[];
      content.innerHTML=inc.length
        ? inc.map(i=>`<section class="card"><strong>${escapeHtml(names[i.site_id]||i.site_id)}</strong> · ${escapeHtml(i.status)} · HTTP ${escapeHtml(i.http_status ?? t('no_response'))} · ${escapeHtml(i.duration_ms)} ms<div class="muted" style="font-size:12px">${escapeHtml(fmtDate(i.checked_at))}</div></section>`).join('')
        : `<section class="card"><h2>${t('no_incidents_title')}</h2><p>${t('no_incidents_desc')}</p></section>`;
    }
    document.querySelector('#open-agent')?.addEventListener('click',()=>chat('usbestroofing'));
  }catch(e){if(ticket===generation){content.textContent='';error.textContent=e.message;}}
}
async function chat(agent) {
  if(!names[agent])return;
  const ticket=++generation;activeAgent=agent;select();error.textContent='';
  document.querySelector('#title').textContent=names[agent];
  content.innerHTML=`<div class="row" style="margin-bottom:8px"><p class="muted" style="margin:0">${t('chat_hint')}</p><button id="clear-chat" type="button" style="background:#eee;color:#222;padding:6px 10px;font-size:12px">${t('clear_chat')}</button></div><div id="messages" aria-live="polite">${t('loading_history')}</div><form class="composer"><textarea aria-label="${t('msg_label')}" placeholder="${t('msg_placeholder')}" maxlength="8000" required></textarea><button type="submit">${t('send_btn')}</button></form>`;
  document.querySelector('form').addEventListener('submit',e=>send(e,agent,ticket));
  document.querySelector('#clear-chat').addEventListener('click',async()=>{
    if(!confirm(t('confirm_clear_chat')))return;
    error.textContent='';
    try{await api('/api/agents/'+agent+'/messages',{method:'DELETE'});if(ticket===generation)await refresh(agent,ticket);}
    catch(e){if(ticket===generation)error.textContent=e.message;}
  });
  await refresh(agent,ticket);
}
async function refresh(agent,ticket) {
  try{const data=await api('/api/agents/'+agent+'/messages');if(ticket!==generation)return;
    const box=document.querySelector('#messages');
    box.innerHTML=data.messages.length?data.messages.map(m=>`<div class="message">${escapeHtml(m.content)}<span class="date">${m.role==='user'?t('you'):m.role==='assistant'?names[agent]:t('system')} · ${escapeHtml(fmtDate(m.created_at))}</span></div>`).join(''):`<p class="muted">${t('no_messages')}</p>`;box.scrollTop=box.scrollHeight;
  }catch(e){if(ticket===generation)error.textContent=e.message;}
}
async function send(e,agent,ticket) {
  e.preventDefault();const form=e.currentTarget, input=form.querySelector('textarea'),button=form.querySelector('button');
  const text=input.value.trim();if(!text)return;button.disabled=true;button.textContent=t('sending_btn');input.disabled=true;error.textContent='';
  try{const result=await api('/api/agents/'+agent+'/messages',{method:'POST',body:JSON.stringify({content:text})});
    input.value='';if(ticket===generation){await refresh(agent,ticket);error.textContent=result.warning || (result.ai==='not_connected'?t('ai_missing_key'):'');}
  }catch(e){if(ticket===generation)error.textContent=e.message;}finally{button.disabled=false;input.disabled=false;button.textContent=t('send_btn');}
}
document.querySelectorAll('[data-lang]').forEach(b=>b.addEventListener('click',()=>setLang(b.dataset.lang)));
document.querySelectorAll('[data-view]').forEach(b=>b.addEventListener('click',()=>view(b.dataset.view)));
document.querySelectorAll('[data-chat]').forEach(b=>b.addEventListener('click',()=>chat(b.dataset.chat)));
applyStaticI18n();
view('Resumen');
