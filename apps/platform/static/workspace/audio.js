/* Ephemeral browser grants and PCM only; provider keys never enter this code. */
async function audioTicket(form, url, mode) {
  const data = new FormData(); data.set('mode', mode); data.set('consent', 'yes');
  const response = await fetch(url, {method:'POST', credentials:'same-origin', body:data,
    headers:{'X-CSRFToken':form.querySelector('[name=csrfmiddlewaretoken]').value}});
  if (!response.ok) throw new Error('Could not authorize the test. Sign in again or wait a minute and retry.');
  return response.json();
}
function audioSocket(ticket) {
  const ws = new WebSocket(`wss://${location.host}${ticket.path}`);
  ws.binaryType = 'arraybuffer';
  ws.addEventListener('open', () => ws.send(JSON.stringify({ticket:ticket.ticket})), {once:true});
  return ws;
}
for (const form of document.querySelectorAll('.connection-check')) {
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const button = form.querySelector('button');
    const result = form.closest('.connection-card').querySelector('.connection-result');
    button.disabled = true; result.textContent = 'Starting a short connection test…';
    let ws, completed = false;
    const timeout = setTimeout(() => {if (!completed) {result.textContent='Connection test timed out. Please try again.';ws?.close();button.disabled=false;}}, 30000);
    try {
      ws = audioSocket(await audioTicket(form, form.dataset.ticketUrl, 'check'));
      ws.onmessage = event => {
        if (typeof event.data !== 'string') return;
        const message = JSON.parse(event.data);
        if (message.message) result.textContent = message.message;
        if (['result','error'].includes(message.type)) {completed=true;clearTimeout(timeout);button.disabled=false;}
      };
      ws.onclose = () => {clearTimeout(timeout);button.disabled=false;if(!completed) result.textContent='The connection closed before the provider confirmed the test. Please retry.';};
      ws.onerror = () => {result.textContent='The audio service could not be reached. Please try again.';};
      window.addEventListener('pagehide', () => ws.close(), {once:true});
    } catch (error) {clearTimeout(timeout);result.textContent=error.message;button.disabled=false;}
  });
}
const preview = document.querySelector('.voice-preview');
if (preview) {
  const form = preview.querySelector('.voice-start'), start = form.querySelector('button');
  const stop = preview.querySelector('.voice-stop'), mute = preview.querySelector('.voice-mute');
  const status = preview.querySelector('.voice-status');
  let stream, context, capture, source, ws, ready=false, muted=false, cursor=0, generation=0, timer;
  const playing = new Set();
  function clearAudio() {for(const node of playing) {try{node.stop();}catch{}}playing.clear();cursor=0;}
  function cleanup(message) {
    generation++;ready=false;clearTimeout(timer);clearAudio();
    if(capture){capture.port.onmessage=null;capture.disconnect();}source?.disconnect();
    stream?.getTracks().forEach(track=>track.stop());stream=null;
    if(context){context.close().catch(()=>{});context=null;}
    if(ws){ws.onclose=null;ws.onmessage=null;ws.onerror=null;ws.close();ws=null;}
    start.disabled=false;stop.disabled=true;mute.disabled=true;muted=false;
    mute.textContent='Mute microphone';mute.setAttribute('aria-pressed','false');
    if(message) status.textContent=message;
  }
  form.addEventListener('submit', async event => {
    event.preventDefault();start.disabled=true;stop.disabled=false;
    const current=++generation;
    status.textContent='Requesting microphone access…';
    try {
      const media=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true},video:false});
      if(current!==generation){media.getTracks().forEach(track=>track.stop());return;}
      stream=media;context=new AudioContext({sampleRate:24000});await context.resume();
      if(context.sampleRate!==24000) throw new Error('This browser does not support the preview audio format. Try desktop Chrome or Edge.');
      await context.audioWorklet.addModule(preview.dataset.workletUrl);
      if(current!==generation)return;
      capture=new AudioWorkletNode(context,'ampve-capture');source=context.createMediaStreamSource(stream);
      source.connect(capture);capture.connect(context.destination);
      capture.port.onmessage=event=>{
        if(ready&&!muted&&ws?.readyState===WebSocket.OPEN){
          if(ws.bufferedAmount>96000){cleanup('The network could not keep up. Microphone off; please retry.');return;}
          ws.send(event.data);
        }
      };
      const ticket=await audioTicket(form,preview.dataset.ticketUrl,'voice');
      if(current!==generation)return;
      ws=audioSocket(ticket);status.textContent='Connecting to your provider…';
      timer=setTimeout(()=>cleanup('Connection timed out. Microphone off.'),30000);
      ws.onmessage=event=>{
        if(typeof event.data==='string'){
          const message=JSON.parse(event.data);
          if(message.type==='ready'){clearTimeout(timer);ready=true;mute.disabled=false;status.textContent='Listening · Microphone on. Say hello.';}
          if(message.type==='clear')clearAudio();
          if(message.type==='result'||message.type==='error')cleanup(`${message.message} Microphone off.`);
        } else if(ready&&context){
          const pcm=new Int16Array(event.data);
          if(cursor-context.currentTime>2){cleanup('Playback fell behind. Microphone off; please retry.');return;}
          const buffer=context.createBuffer(1,pcm.length,24000), output=buffer.getChannelData(0);
          for(let i=0;i<pcm.length;i++)output[i]=pcm[i]/32768;
          const node=context.createBufferSource();node.buffer=buffer;node.connect(context.destination);
          cursor=Math.max(cursor,context.currentTime+0.03);node.start(cursor);cursor+=buffer.duration;
          playing.add(node);status.textContent=muted?'Companion speaking · Microphone muted.':'Companion speaking · Microphone on.';
          node.onended=()=>{playing.delete(node);if(!playing.size&&ready)status.textContent=muted?'Microphone muted.':'Listening · Microphone on.';};
        }
      };
      ws.onclose=()=>cleanup('Session ended. Microphone off.');
      ws.onerror=()=>cleanup('The audio service could not be reached. Microphone off.');
    } catch(error) {if(current===generation)cleanup(error.name==='NotAllowedError'?'Microphone permission was not granted.':error.message);}
  });
  stop.addEventListener('click',()=>cleanup('Session stopped. Microphone off.'));
  mute.addEventListener('click',()=>{muted=!muted;stream?.getAudioTracks().forEach(track=>{track.enabled=!muted;});mute.setAttribute('aria-pressed',String(muted));mute.textContent=muted?'Unmute microphone':'Mute microphone';status.textContent=muted?'Microphone muted.':'Listening · Microphone on.';});
  window.addEventListener('pagehide',()=>cleanup());
}
