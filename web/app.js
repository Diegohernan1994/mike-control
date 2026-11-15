let currentView = 'Resumen', activeAgent = null, generation = 0;
const content = document.querySelector('#content');
const error = document.querySelector('#error');
const names = {mike:'Mike',usbestroofing:'US Best Roofing',centrotai:'Centro TAI',pacific:'Pacific',gabriels:'Gabriels'};
const escapeHtml = s => String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
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
  if (!response.ok) throw new Error(response.status===409?'Ya hay una respuesta en curso en este chat. Esperá antes de enviar.':response.status===401?'Sesión no autorizada. Recargá e ingresá tus credenciales.':'No se pudo completar la consulta. Revisá la conexión y el estado del backend.');
  return response.json();
}
function select() {
  document.querySelectorAll('[data-view]').forEach(b=>b.classList.toggle('active',!activeAgent && b.dataset.view===currentView));
  document.querySelectorAll('[data-chat]').forEach(b=>b.classList.toggle('active',b.dataset.chat===activeAgent));
}
async function view(tab) {
  const ticket=++generation; currentView=tab;activeAgent=null;select();error.textContent='';
  document.querySelector('#title').textContent=tab==='Resumen'?'Todo bajo tu supervisión.':tab;
  content.textContent='Consultando…';
  try {
    const status=await api('/api/status');if(ticket!==generation)return;
    renderSidebar(status.agents);
    if(tab==='Resumen') {
      const check=status.latest_check, age=check ? Date.now()-Date.parse(check.checked_at) : null;
      const label=!check?'Sin mediciones':age>30*60*1000?'Medición vencida':check.status==='ok'?'Respondió':check.status==='redirect'?'Redirección':'Revisar conexión';
      const detail=check ? `Última consulta: ${escapeHtml(new Date(check.checked_at).toLocaleString())} · HTTP ${escapeHtml(check.http_status ?? 'sin respuesta')} · ${escapeHtml(check.duration_ms)} ms` : 'Todavía no se realizó una comprobación.';
      const checksHtml=(status.site_checks||[]).length
        ? (status.site_checks||[]).map(c=>{
            const st=c.status==='ok'?'Online':c.status==='redirect'?'Redirección':'Revisar conexión';
            return `<div class="row" style="padding:8px 0;border-bottom:1px solid #eceeed"><div><strong>${escapeHtml(names[c.site_id]||c.site_id)}</strong><div class="muted" style="font-size:12px">${escapeHtml(st)} · HTTP ${escapeHtml(c.http_status ?? 'sin respuesta')} · ${escapeHtml(c.duration_ms)} ms · ${escapeHtml(new Date(c.checked_at).toLocaleString())}</div></div><button data-open-site="${escapeHtml(c.site_id)}">Abrir chat ↗</button></div>`;
          }).join('')
        : '<p class="muted">Todavía no hay mediciones guardadas.</p>';
      content.innerHTML=`<div class="stats"><div class="card"><small>POSTGRESQL</small><div class="value">Conectado</div><small>Historial central de conversaciones</small></div><div class="card"><small>SITIO PILOTO</small><div class="value">${label}</div><small>${detail}</small></div><div class="card"><small>MONITOREO</small><div class="value">${status.monitoring==='enabled'?'Activado':'Desactivado'}</div><small>Consulta HTTP cada ${status.scan_interval_minutes} min</small></div></div><section class="card"><h2>Estado de sitios monitoreados</h2>${checksHtml}</section><section class="card"><h2>Vos decidís</h2><p>${status.execution==='approval_required'?'Las acciones de escritura siempre pasan por la pestaña Aprobaciones antes de ejecutarse.':'El ejecutor está deshabilitado. El chat no autoriza ni ejecuta acciones.'}</p></section>`;
      content.querySelectorAll('[data-open-site]').forEach(b=>b.addEventListener('click',()=>chat(b.dataset.openSite)));
    }
    else if(tab==='Memoria'){
      const agentNames=(status.agents||[]).map(a=>escapeHtml(a.name)).join(', ');
      content.innerHTML=`<section class="card"><h2>Historial persistente</h2><p>Los mensajes de cada chat (${agentNames}) se guardan separados en PostgreSQL. Abrí cada conversación para consultar los últimos 100 mensajes.</p><p>Las acciones aprobadas y mediciones de disponibilidad también quedan guardadas en PostgreSQL. Con OpenAI configurado, cada envío comparte hasta 40 mensajes recientes de ese chat (máximo 24.000 caracteres) para generar una respuesta.</p></section>`;
    }
    else if(tab==='Configuración'){
      const siteRows=(status.agents||[]).filter(a=>a.kind!=='system').map(a=>{
        const prefix=a.id.toUpperCase();
        const envHint=a.kind==='wordpress'
          ? `${prefix}_WP_URL + ${prefix}_WP_BRIDGE_SECRET`
          : `${prefix}_GITHUB_REPO + ${prefix}_GITHUB_TOKEN`;
        const delBtn=a.custom?`<button data-del-site="${escapeHtml(a.id)}" style="background:#eee;color:#222">Quitar</button>`:'';
        return `<div class="row" style="padding:8px 0;border-bottom:1px solid #eceeed"><div><strong>${escapeHtml(a.name)}</strong> <span class="muted">(${escapeHtml(a.kind==='wordpress'?'WordPress':'Astro / Vercel')} · ${escapeHtml(a.id)})</span><div class="muted" style="font-size:12px">Variables en Easypanel: <code>${escapeHtml(envHint)}</code></div></div>${delBtn}</div>`;
      }).join('');
      content.innerHTML=`<section class="card"><h2>Conexiones</h2><p>PostgreSQL: conectado<br>OpenAI: ${status.ai==='configured'?'configurado; se verifica al enviar':'sin configurar'}<br>Telegram: sin conectar<br>SSH WordPress (solo lectura): ${status.ssh==='read_only'?'activo ('+escapeHtml((status.ssh_sites||[]).map(s=>names[s]||s).join(', '))+')':'sin conectar'}<br>Monitoreo HTTP: ${status.monitoring==='enabled'?'activado':'desactivado'}<br>WordPress Bridge: ${(status.wp_sites||[]).length?escapeHtml((status.wp_sites||[]).map(s=>names[s]||s).join(', ')):'sin configurar'}<br>GitHub / Vercel GitOps: ${(status.git_sites||[]).length?escapeHtml((status.git_sites||[]).map(s=>names[s]||s).join(', ')):'sin configurar'}</p><p>Las credenciales se configuran en Easypanel, nunca en este chat.</p></section><section class="card"><h2>Agregar sitio al panel</h2><p class="muted">Creá un chat nuevo organizado en WordPress o Astro / Vercel sin editar código.</p><form id="add-site-form" style="display:flex;flex-wrap:wrap;gap:8px;margin-top:10px"><input name="name" placeholder="Nombre (ej: Exodus Remodeling)" maxlength="80" required style="flex:2;min-width:160px;padding:8px;border:1px solid #d7dcd9;border-radius:8px"><input name="id" placeholder="ID corto (ej: exodus)" pattern="[a-z0-9][a-z0-9_-]{1,31}" maxlength="32" required style="flex:1;min-width:120px;padding:8px;border:1px solid #d7dcd9;border-radius:8px"><input name="url" type="url" placeholder="URL monitoreo (opcional: https://...)" maxlength="300" style="flex:2;min-width:200px;padding:8px;border:1px solid #d7dcd9;border-radius:8px"><select name="kind" style="padding:8px;border:1px solid #d7dcd9;border-radius:8px"><option value="wordpress">WordPress</option><option value="vercel">Astro / Vercel</option></select><button type="submit">Agregar sitio</button></form><div style="margin-top:16px">${siteRows}</div></section>`;
      document.querySelector('#add-site-form')?.addEventListener('submit',async e=>{
        e.preventDefault();
        const fd=new FormData(e.currentTarget);
        error.textContent='';
        try{
          await api('/api/sites',{method:'POST',body:JSON.stringify({id:String(fd.get('id')||'').trim().toLowerCase(),name:String(fd.get('name')||'').trim(),kind:String(fd.get('kind')||'wordpress'),url:String(fd.get('url')||'').trim()})});
          if(ticket===generation)await view('Configuración');
        }catch(err){if(ticket===generation)error.textContent=err.message;}
      });
      content.querySelectorAll('[data-del-site]').forEach(btn=>btn.addEventListener('click',async()=>{
        btn.disabled=true;error.textContent='';
        try{await api('/api/sites/'+btn.dataset.delSite,{method:'DELETE'});if(ticket===generation)await view('Configuración');}
        catch(err){if(ticket===generation){error.textContent=err.message;btn.disabled=false;}}
      }));
    }
    else if(tab==='Aprobaciones'){
      const data=await api('/api/proposals');if(ticket!==generation)return;
      const items=data.proposals||[];
      if(!items.length){
        content.innerHTML='<section class="card"><h2>Sin acciones pendientes</h2><p>Cuando un agente proponga un cambio en WordPress (guardar página, crear respaldo, etc.), aparecerá acá para que lo apruebes o rechaces.</p></section>';
      }else{
        content.innerHTML=items.map(p=>{
          const siteLabel=escapeHtml(names[p.site_id]||p.site_id);
          const paramsStr=escapeHtml(JSON.stringify(p.params_json||{},null,2));
          const actions=p.status==='pending'
            ? `<div class="row" style="margin-top:12px;gap:8px;justify-content:flex-start"><button data-approve="${p.id}">Aprobar y ejecutar</button><button data-reject="${p.id}" style="background:#eee;color:#222">Rechazar</button></div>`
            : '';
          const resultStr=p.result_json?`<pre style="margin-top:8px;white-space:pre-wrap;font-size:12px;background:#f6f7f6;padding:8px;border-radius:6px">${escapeHtml(JSON.stringify(p.result_json,null,2))}</pre>`:'';
          return `<section class="card"><div class="row"><div><strong>#${p.id} · ${siteLabel} · ${escapeHtml(p.tool_name)}</strong><div class="muted" style="font-size:12px">Estado: ${escapeHtml(p.status)} · Vence: ${escapeHtml(new Date(p.expires_at).toLocaleString())}</div></div></div><pre style="margin-top:8px;white-space:pre-wrap;font-size:12px;background:#f6f7f6;padding:8px;border-radius:6px">${paramsStr}</pre>${resultStr}${actions}</section>`;
        }).join('');
        content.querySelectorAll('[data-approve]').forEach(btn=>btn.addEventListener('click',async()=>{
          btn.disabled=true;btn.textContent='Ejecutando…';error.textContent='';
          try{await api('/api/proposals/'+btn.dataset.approve+'/approve',{method:'POST'});if(ticket===generation)await view('Aprobaciones');}
          catch(e){if(ticket===generation){error.textContent=e.message;btn.disabled=false;btn.textContent='Aprobar y ejecutar';}}
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
        ? inc.map(i=>`<section class="card"><strong>${escapeHtml(names[i.site_id]||i.site_id)}</strong> · ${escapeHtml(i.status)} · HTTP ${escapeHtml(i.http_status ?? 'sin respuesta')} · ${escapeHtml(i.duration_ms)} ms<div class="muted" style="font-size:12px">${escapeHtml(new Date(i.checked_at).toLocaleString())}</div></section>`).join('')
        : '<section class="card"><h2>Sin incidentes recientes</h2><p>No se registraron caídas ni respuestas fuera de rango en los sitios monitoreados.</p></section>';
    }
    document.querySelector('#open-agent')?.addEventListener('click',()=>chat('usbestroofing'));
  }catch(e){if(ticket===generation){content.textContent='';error.textContent=e.message;}}
}
async function chat(agent) {
  if(!names[agent])return;
  const ticket=++generation;activeAgent=agent;select();error.textContent='';
  document.querySelector('#title').textContent=names[agent];
  content.innerHTML='<p class="muted">Historial en PostgreSQL · Respuestas de IA si OpenAI está configurado. Los mensajes no ejecutan órdenes.</p><div id="messages" aria-live="polite">Cargando historial…</div><form class="composer"><textarea aria-label="Mensaje" placeholder="Escribí tu mensaje…" maxlength="8000" required></textarea><button type="submit">Enviar ↑</button></form>';
  document.querySelector('form').addEventListener('submit',e=>send(e,agent,ticket));
  await refresh(agent,ticket);
}
async function refresh(agent,ticket) {
  try{const data=await api('/api/agents/'+agent+'/messages');if(ticket!==generation)return;
    const box=document.querySelector('#messages');
    box.innerHTML=data.messages.length?data.messages.map(m=>`<div class="message">${escapeHtml(m.content)}<span class="date">${m.role==='user'?'Vos':m.role==='assistant'?names[agent]:'Sistema'} · ${escapeHtml(new Date(m.created_at).toLocaleString())}</span></div>`).join(''):'<p class="muted">Esta conversación aún no tiene mensajes.</p>';box.scrollTop=box.scrollHeight;
  }catch(e){if(ticket===generation)error.textContent=e.message;}
}
async function send(e,agent,ticket) {
  e.preventDefault();const form=e.currentTarget, input=form.querySelector('textarea'),button=form.querySelector('button');
  const text=input.value.trim();if(!text)return;button.disabled=true;button.textContent='Respondiendo…';input.disabled=true;error.textContent='';
  try{const result=await api('/api/agents/'+agent+'/messages',{method:'POST',body:JSON.stringify({content:text})});
    input.value='';if(ticket===generation){await refresh(agent,ticket);error.textContent=result.warning || (result.ai==='not_connected'?'Mensaje guardado. Falta configurar OPENAI_API_KEY en Easypanel.':'');}
  }catch(e){if(ticket===generation)error.textContent=e.message;}finally{button.disabled=false;input.disabled=false;button.textContent='Enviar ↑';}
}
document.querySelectorAll('[data-view]').forEach(b=>b.addEventListener('click',()=>view(b.dataset.view)));
document.querySelectorAll('[data-chat]').forEach(b=>b.addEventListener('click',()=>chat(b.dataset.chat)));
view('Resumen');
