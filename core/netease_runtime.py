"""Bootstrap NetEase webpack by capabilities, not version-specific module IDs."""
RUNTIME = r'''
(() => {
  if (window.__songdesk && window.__songdesk.store) return;
  const chunks = window.webpackJsonp;
  if (!chunks || typeof chunks.push !== 'function') throw Error('未找到网易云 webpack 运行时');
  const id = 'songdesk_' + Date.now();
  chunks.push([[id],{[id]:function(module,exports,require){window.__songdesk_require__=require;}},[[id]]]);
  const req = window.__songdesk_require__;
  if (!req || !req.c || !req.m) throw Error('不支持的网易云模块加载器');
  let store = null, request = null;
  for (const mod of Object.values(req.c)) {
    const exp = mod.exports;
    let values = [exp];
    try { if(exp) values = values.concat(Object.keys(exp).map(k=>exp[k])); } catch(_) {}
    for(const v of values) {
      if(v && typeof v.getStore === 'function' && typeof v.getDispatch === 'function') {
        try {const s=v.getStore();if(s.playing && s.playingList && Array.isArray(s.playingList.curPlayingList))store=v;}catch(_){}
      }
    }
  }
  // Factory that delegates HTTP requests to the client's encrypted request layer.
  for(const [key, factory] of Object.entries(req.m)) {
    const text=String(factory);
    if(!text.includes('defaultOptions') || !text.includes('formatOption') || !text.includes('fetchFrontEndEncryptError'))continue;
    const exp=req(key);
    for(const v of Object.values(exp||{})) {
      if(typeof v==='function' && String(v).includes('defaultOptions') && String(v).includes('formatOption')) {request=v;break;}
    }
    if(request)break;
  }
  if(!store)throw Error('未找到兼容的网易云播放状态接口');
  if(!request)throw Error('未找到兼容的网易云搜索请求接口');
  const models=store.app && store.app._models;
  const actions=new Set();
  for(const m of models||[])for(const key of Object.keys(m.effects||{}))actions.add(key.includes('/')?key:m.namespace+'/'+key);
  if(!actions.has('playingList/addItemToCurPlayingList') || !actions.has('playingList/jump2Track'))throw Error('网易云缺少入队或切歌动作');
  window.__songdesk={store,request,actions};
})();
'''
STATE = r'''
(() => {
 const s=window.__songdesk.store.getStore(), p=s.playing;
 return {current:p.curPlaying?Number(p.curPlaying.resourceId):null,
         name:p.curPlaying?.track?.name||'',status:p.playingState,mode:p.playingMode,
         queue:s.playingList.curPlayingList.map(x=>Number(x.resourceId))};
})()
'''
