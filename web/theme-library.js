"use strict";
const OnlineThemes = (() => {
  let timer=null, polling=false, actionBusy=false, current=null, previousFocus=null;
  const el=id=>document.getElementById(id);
  function open() {
    previousFocus=document.activeElement;
    el('online-theme-modal').classList.remove('hidden');
    el('online-theme-close').focus(); poll();
    if(timer===null)timer=setInterval(poll,500);
  }
  function close() {
    if(document.querySelector('.confirm-overlay'))return;
    el('online-theme-modal').classList.add('hidden');
    clearInterval(timer);timer=null;
    previousFocus?.focus({preventScroll:true});
  }
  function render(value) {
    const stamp=JSON.stringify(value);
    if(stamp===JSON.stringify(current))return;
    current=value;
    const running=['refreshing','downloading'].includes(value.phase);
    el('online-theme-refresh').disabled=running||actionBusy;
    el('online-theme-status').textContent=value.message;
    el('online-theme-status').dataset.error=String(value.phase==='error');
    el('online-theme-progress').classList.toggle('hidden',value.phase!=='downloading');
    el('online-theme-progress').value=value.progress;
    el('online-theme-load').classList.toggle('hidden',!value.installedId);
    const list=el('online-theme-list');list.replaceChildren();
    if(!value.themes.length){const empty=document.createElement('p');empty.className='online-theme-empty';empty.textContent='暂无在线主题。可刷新主题库，或继续导入本地 .songtheme。';list.append(empty);}
    for(const item of value.themes){
      const row=document.createElement('article');row.className='online-theme-item';
      const info=document.createElement('div');
      const title=document.createElement('h3');title.textContent=item.name;
      const meta=document.createElement('small');meta.textContent='v'+item.version+' · '+(item.author||'未署名')+' · '+(item.size/1024/1024).toFixed(2)+' MB';
      const description=document.createElement('p');description.textContent=item.description;
      const local=document.createElement('p');local.textContent=item.reason|| (item.installedId?'本地已安装 v'+item.installedVersion+'，下载不会覆盖原主题':'尚未安装');
      info.append(title,meta,description,local);
      const button=document.createElement('button');
      const newer=item.installedVersion && item.version.split('.').map(Number).some((part,index,parts)=>part>Number(item.installedVersion.split('.')[index])&&parts.slice(0,index).every((n,i)=>n===Number(item.installedVersion.split('.')[i])));
      button.textContent=!item.compatible?'需更新程序':item.installedId?(newer?'下载新版副本':'另存一份'):'下载主题';
      button.disabled=running||actionBusy||!item.compatible;
      button.onclick=()=>download(item);row.append(info,button);list.append(row);
    }
  }
  async function poll() {
    if(polling||!window.pywebview?.api||el('online-theme-modal').classList.contains('hidden'))return;
    polling=true;
    try{render(await window.pywebview.api.online_theme_state());}
    catch(error){el('online-theme-status').textContent=error.message||String(error);el('online-theme-status').dataset.error='true';}
    finally{polling=false;}
  }
  async function invoke(method,...args) {
    actionBusy=true;
    try{current=null;render(await window.pywebview.api[method](...args));}
    catch(error){el('online-theme-status').textContent=error.message||String(error);el('online-theme-status').dataset.error='true';}
    finally{actionBusy=false;current=null;poll();}
  }
  async function download(item) {
    if(actionBusy||['refreshing','downloading'].includes(current?.phase))return;
    if(item.installedId&&!await ConfirmDialog.ask({title:'下载主题副本',message:'本地已有「'+item.name+'」。下载后另存为新主题，不覆盖已有修改、不自动应用。',confirmText:'下载副本'}))return;
    await invoke('install_online_theme',item.id,item.version);
  }
  function init() {
    const button=document.createElement('button');button.id='open-online-themes';button.className='online-library-open';button.textContent='在线主题库';
    document.querySelector('.library-actions').after(button);button.onclick=open;
    el('online-theme-close').onclick=close;
    el('online-theme-modal').onclick=event=>{if(event.target===el('online-theme-modal'))close();};
    el('online-theme-refresh').onclick=()=>invoke('refresh_online_themes');
    el('online-theme-load').onclick=async()=>{
      const id=current?.installedId;if(!id||busy)return;
      if(!await discard())return;
      await run(async()=>{loadPayload(await window.pywebview.api.load_theme(id));await library();status('在线主题已载入工坊，尚未应用。');});close();
    };
    document.addEventListener('keydown',event=>{
      if(el('online-theme-modal').classList.contains('hidden')||document.querySelector('.confirm-overlay'))return;
      if(event.key==='Escape'){event.preventDefault();close();}
      if(event.key==='Tab'){
        const nodes=[...el('online-theme-modal').querySelectorAll('button:not(:disabled)')].filter(n=>!n.classList.contains('hidden'));
        if(!nodes.length)return;
        const first=nodes[0],last=nodes[nodes.length-1];
        if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}
        else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}
      }
    });
    window.addEventListener('pagehide',()=>clearInterval(timer),{once:true});
  }
  return {init,open,close};
})();
document.addEventListener('DOMContentLoaded',()=>OnlineThemes.init());
