let currentView = 'Resumen', activeAgent = null, generation = 0;
const content = document.querySelector('#content');
const error = document.querySelector('#error');
const names = {mike:'Mike',usbestroofing:'US Best Roofing'};
const escapeHtml = s => String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
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
    if(tab==='Resumen') content.innerHTML=`<div class="stats"><div class="card"><small>POSTGRESQL</small><div class="value">Conectado</div><small>Historial central de conversaciones</small></div><div class="card"><small>SITIO PILOTO</small><div class="value">Sin mediciones</div><small>usbestroofing.com</small></div><div class="card"><small>ESCANEO PREVISTO</small><div class="value">${status.scan_interval_minutes} min</div><small>Aún no implementado</small></div></div><section class="card"><div class="row"><div><h2>US Best Roofing</h2><p class="muted">WordPress · DigitalOcean · SSH sin conectar</p></div><button id="open-agent">Abrir chat ↗</button></div></section><section class="card"><h2>Vos decidís</h2><p>El ejecutor está deshabilitado. Este backend no puede modificar tus sitios. Las respuestas de IA requieren la clave configurada. El chat no autoriza ni ejecuta acciones.</p></section>`;
    else if(tab==='Memoria')content.innerHTML='<section class="card"><h2>Historial persistente</h2><p>Los mensajes de Mike y US Best Roofing se guardan separados en PostgreSQL. Abrí cada conversación para consultar los últimos 100 mensajes.</p><p>La memoria de incidentes, resúmenes y acciones se implementará con sus respectivos servicios. Con OpenAI configurado, cada envío comparte hasta 40 mensajes recientes de ese chat (máximo 24.000 caracteres) para generar una respuesta. No hay búsqueda en todo el archivo ni memoria semántica todavía.</p></section>';
    else if(tab==='Configuración')content.innerHTML=`<section class="card"><h2>Conexiones</h2><p>PostgreSQL: conectado<br>OpenAI: ${status.ai==='configured'?'configurado; se verifica al enviar':'sin configurar'}<br>Telegram: sin conectar<br>SSH: sin conectar<br>Escaneos cada 15 minutos: no implementados<br>Ejecución remota: deshabilitada</p><p>Las credenciales se configuran en Easypanel, nunca en este chat.</p></section>`;
    else content.innerHTML=`<section class="card"><h2>${tab==='Incidentes'?'Sin monitoreo activo':'Sin acciones para aprobar'}</h2><p>${tab==='Incidentes'?'Todavía no hay comprobaciones. Esta pantalla no confirma que el sitio esté sano.':'El circuito de propuestas y autorizaciones todavía no está implementado. Ningún mensaje constituye una aprobación de ejecución.'}</p></section>`;
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
