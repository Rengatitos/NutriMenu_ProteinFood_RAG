const roomList = document.getElementById('roomList');
const messages = document.getElementById('messages');
const composer = document.getElementById('composer');
const input = document.getElementById('messageInput');
const sendBtn = document.getElementById('sendBtn');
const statusLine = document.getElementById('statusLine');
const sidebar = document.getElementById('sidebar');
let currentRoomId = localStorage.getItem('nutrimenu_room_id');
let sending = false;

const escapeHtml = (s='') => String(s).replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));

function scrollBottom(){ messages.scrollTop = messages.scrollHeight; }
function shortDate(iso){
  if(!iso) return '';
  const d = new Date(iso); const now = new Date();
  const same = d.toDateString() === now.toDateString();
  return same ? 'Hoy' : d.toLocaleDateString('es-PE',{day:'2-digit',month:'short'});
}

function renderMessage(msg){
  const row = document.createElement('div');
  row.className = `message-row ${msg.role}`;
  if(msg.role !== 'user'){
    const avatar = document.createElement('div'); avatar.className='avatar bot'; row.appendChild(avatar);
  }
  const bubble = document.createElement('div'); bubble.className='message-bubble';
  bubble.textContent = msg.content || '';
  row.appendChild(bubble);
  if(msg.role === 'user'){
    const avatar = document.createElement('div'); avatar.className='avatar'; avatar.textContent='●'; row.appendChild(avatar);
  }
  if(msg.role === 'assistant' && msg.id){
    row.appendChild(createFeedback(msg.id, msg.feedback));
  }
  messages.appendChild(row);

  const products = msg.payload?.products || [];
  if(products.length) renderProducts(products);
  scrollBottom();
}

function createFeedback(messageId, selected=''){
  const box=document.createElement('div'); box.className='feedback';
  const label=document.createElement('span'); label.textContent='¿Esta respuesta fue útil?'; box.appendChild(label);
  [['useful','👍 Sí'],['not_useful','👎 No']].forEach(([rating,text])=>{
    const button=document.createElement('button'); button.type='button'; button.textContent=text;
    button.className=selected===rating?'selected':'';
    button.addEventListener('click',async()=>{
      box.querySelectorAll('button').forEach(item=>item.disabled=true);
      try{
        await api('/api/feedback',{method:'POST',body:JSON.stringify({room_id:currentRoomId,message_id:messageId,rating})});
        box.querySelectorAll('button').forEach(item=>item.classList.toggle('selected',item===button));
        label.textContent='Gracias por tu feedback';
      }catch(err){ statusLine.textContent=`No se guardó el feedback: ${err.message}`; }
      finally{ box.querySelectorAll('button').forEach(item=>item.disabled=false); }
    });
    box.appendChild(button);
  });
  return box;
}

function renderProducts(products){
  const section = document.createElement('section'); section.className='product-section';
  const grid = document.createElement('div'); grid.className='product-grid';
  const tpl = document.getElementById('productCardTemplate');
  products.forEach(p => {
    const node = tpl.content.cloneNode(true);
    const img = node.querySelector('.product-img');
    img.src = p.image_url; img.alt = `Imagen de ${p.producto}`;
    node.querySelector('.kcal-badge').textContent = `${p.kcal_min_est}–${p.kcal_max_est} kcal`;
    node.querySelector('.product-name').textContent = p.producto;
    node.querySelector('.product-desc').textContent = p.descripcion;
    node.querySelector('.product-price').textContent = `S/ ${Number(p.precio_pen).toFixed(2)}`;
    node.querySelector('.protein-pill').textContent = `Proteína: ${p.nivel_proteico}`;
    node.querySelector('.product-alert').textContent = `Alertas textuales: ${p.ingredientes_alerta || 'No identificadas en el texto'}`;
    grid.appendChild(node);
  });
  section.appendChild(grid);
  const note = document.createElement('div'); note.className='product-footnote';
  note.textContent = 'ⓘ Las kcal son estimadas y pueden variar. Las imágenes incluidas son placeholders reemplazables por fotos reales con el mismo nombre de archivo.';
  section.appendChild(note);
  messages.appendChild(section); scrollBottom();
}

async function api(url, options={}){
  const res = await fetch(url, {headers:{'Content-Type':'application/json'}, ...options});
  const data = await res.json().catch(()=>({}));
  if(!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

async function createRoom(){
  const data = await api('/api/rooms',{method:'POST',body:JSON.stringify({})});
  currentRoomId = data.room.id; localStorage.setItem('nutrimenu_room_id',currentRoomId);
  messages.innerHTML=''; await refreshRooms(); input.focus();
  sidebar.classList.remove('open');
}

async function refreshRooms(){
  const {rooms} = await api('/api/rooms');
  roomList.innerHTML='';
  rooms.forEach(room => {
    const el = document.createElement('div'); el.className=`room-item ${room.id===currentRoomId?'active':''}`;
    el.innerHTML = `<small>${escapeHtml(shortDate(room.updated_at))}</small><span class="room-title">${escapeHtml(room.title)}</span><span class="room-preview">${escapeHtml(room.preview || '')}</span>`;
    const del = document.createElement('button'); del.className='room-delete'; del.title='Eliminar'; del.textContent='⋯';
    del.addEventListener('click', async ev => {
      ev.stopPropagation(); if(!confirm('¿Eliminar esta conversación?')) return;
      await api(`/api/rooms/${room.id}`,{method:'DELETE'});
      if(room.id===currentRoomId){ currentRoomId=null; localStorage.removeItem('nutrimenu_room_id'); await ensureRoom(); }
      await refreshRooms();
    });
    el.appendChild(del);
    el.addEventListener('click', async ()=>{ currentRoomId=room.id; localStorage.setItem('nutrimenu_room_id',room.id); await loadCurrentRoom(); sidebar.classList.remove('open'); });
    roomList.appendChild(el);
  });
}

async function ensureRoom(){
  const {rooms} = await api('/api/rooms');
  const found = currentRoomId && rooms.some(r=>r.id===currentRoomId);
  if(!found){
    if(rooms.length){ currentRoomId=rooms[0].id; localStorage.setItem('nutrimenu_room_id',currentRoomId); }
    else { await createRoom(); return; }
  }
  await loadCurrentRoom();
}

async function loadCurrentRoom(){
  if(!currentRoomId) return;
  const data = await api(`/api/rooms/${currentRoomId}/messages`);
  messages.innerHTML='';
  data.messages.forEach(renderMessage); await refreshRooms();
}

async function sendText(text){
  if(sending || !text.trim()) return;
  sending=true; sendBtn.disabled=true; input.disabled=true;
  const clean=text.trim(); renderMessage({role:'user',content:clean}); input.value='';
  const typing=document.createElement('div'); typing.className='typing'; typing.textContent='Clara está consultando la carta de Protein Food…'; messages.appendChild(typing); scrollBottom();
  try{
    const data=await api('/api/chat',{method:'POST',body:JSON.stringify({room_id:currentRoomId,message:clean})});
    currentRoomId=data.room_id; localStorage.setItem('nutrimenu_room_id',currentRoomId);
    typing.remove(); renderMessage({id:data.message_id,role:'assistant',content:data.answer,payload:{products:data.products}});
    await refreshRooms();
  }catch(err){
    typing.remove(); renderMessage({role:'assistant',content:`No pude completar la consulta: ${err.message}`});
  }finally{
    sending=false; sendBtn.disabled=false; input.disabled=false; input.focus();
  }
}

composer.addEventListener('submit', e=>{ e.preventDefault(); sendText(input.value); });
document.getElementById('newChatBtn').addEventListener('click', createRoom);
document.getElementById('resetBtn').addEventListener('click', async ()=>{
  if(!currentRoomId) return; await api(`/api/rooms/${currentRoomId}/reset`,{method:'POST'}); messages.innerHTML=''; await refreshRooms();
});
document.querySelectorAll('.kcal-chip').forEach(btn=>btn.addEventListener('click',()=>sendText(btn.dataset.prompt)));
document.getElementById('mobileMenuBtn').addEventListener('click',()=>sidebar.classList.toggle('open'));
const cxDialog=document.getElementById('cxDialog');
document.getElementById('finishBtn').addEventListener('click',()=>cxDialog.showModal());
document.getElementById('cxForm').addEventListener('submit',async e=>{
  e.preventDefault();
  try{
    await api('/api/conversation-feedback',{method:'POST',body:JSON.stringify({
      room_id:currentRoomId,satisfaction:Number(document.getElementById('cxSatisfaction').value),
      nps:Number(document.getElementById('cxNps').value),
      resolved:document.getElementById('cxResolved').value==='true',comment:document.getElementById('cxComment').value
    })});
    cxDialog.close(); statusLine.textContent='Valoración de la conversación guardada.';
  }catch(err){statusLine.textContent=`No se guardó la valoración: ${err.message}`;}
});

async function boot(){
  try{
    const h=await api('/api/health');
    statusLine.textContent = h.ollama_ok ? `Ollama conectado · ${h.llm_model} · embeddings ${h.embedding_model}` : `Ollama no responde todavía · inicia Ollama y descarga ${h.llm_model}`;
    await ensureRoom();
  }catch(err){ statusLine.textContent=`Error de inicio: ${err.message}`; }
}
boot();
