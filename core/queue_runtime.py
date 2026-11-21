"""Bounded consumption hook: observes native end(code=0), never treats pause/ID change as EOF."""
INSTALL = r'''
(() => {
 const desk=window.__songdesk;
 if(!desk.consumer){
   let audio=null;
   for(const mod of Object.values(window.__songdesk_require__.c)){
     let values=[mod.exports];try{values.push(...Object.values(mod.exports||{}))}catch(_){}
     for(const v of values)if(v?.AudioPlayer?.subscribePlayStatus)audio=v.AudioPlayer;
   }
   if(!audio)throw Error('未找到播放结束事件接口，消费队列未启用');
   const q={active:false,lease:0,seq:0,events:[]};desk.consumer=q;
   try{audio.subscribePlayStatus({type:'end',callback:event=>{
     if(!q.active||Date.now()>q.lease||event?.info?.code!==0)return;
     const id=String(event.playId||'').split('_')[0];
     if(!/^\d+$/.test(id))return;
     q.events.push({seq:++q.seq,id,playId:String(event.playId)});
     if(q.events.length>100)q.events.shift();
   }});}catch(e){delete desk.consumer;throw e;}
 }
 return true;
})()
'''
TICK = r'''
(async()=>{
 const q=window.__songdesk.consumer, store=window.__songdesk.store;
 if(!q.active||Date.now()>q.lease)q.events=[];
 q.active=ENABLED;q.lease=Date.now()+15000;
 if(!q.active){q.events=[];return {events:[],seq:q.seq};}
 const mode=store.getStore().playing.playingMode;
 if(mode!=='playOrder'){
   // switchPlayingMode from AI restores a different saved queue. Update the actual
   // mode reducer instead, preserving the user's current queue and current track.
   await store.getDispatch()({type:'playing/onUpdate',payload:{playingMode:'playOrder',lastPlayingMode:mode}});
   await store.getDispatch()({type:'playing/onSwitchPlayingMode',payload:{playingMode:'playOrder',triggerScene:'playingList'}});
 }
 return {events:q.events,seq:q.seq,mode:store.getStore().playing.playingMode};
})()
'''
REMOVE_ENDED = r'''
(async()=>{
 const {id,playId}=INPUT,store=window.__songdesk.store,s=store.getStore(),p=s.playing;
 const current=String(p.curPlaying?.resourceId||'');
 // Replaying the same song is not the old completed playback instance.
 if(current===id && p.playId && String(p.playId)!==playId)return 'stale';
 if(current===id && p.playingState!==-1 && p.playingState!==0)return 'waiting';
 const item=s.playingList.curPlayingList.find(x=>String(x.resourceId)===id);
 if(!item)return 'removed';
 // The last song ended: clear current playback first so removal cannot wrap
 // around and unexpectedly start older, already-present songs at the list head.
 if(current===id){
   await store.getDispatch()({type:'playing/stop',payload:{nativePlayerStop:true,triggerScene:'playingList'}});
   await store.getDispatch()({type:'playing/clearPlayingInfo'});
 }
 await store.getDispatch()({type:'playingList/removeItemFromCurPlayingListByIds',payload:{removeIds:[item],triggerScene:'playingList'}});
 return 'sent';
})()
'''
