"""Allowlisted queue operations executed inside the local NetEase client."""
SNAPSHOT = r'''
(() => {
 const s=window.__songdesk.store.getStore(), p=s.playing;
 return {current:p.curPlaying?String(p.curPlaying.resourceId):null,
   playing:p.playingState===2, status:p.playingState, mode:p.playingMode,
   items:s.playingList.curPlayingList.map(x=>{const t=x.track||{};return {
     id:String(x.resourceId),name:t.name||'未知歌曲',
     singer:(t.artists||t.ar||[]).map(a=>a.name).join(' / '),
     duration:Math.round(Number(t.duration||t.dt||0)/1000)
   }})};
})()
'''
# No arbitrary JS/actions from frontend; only this allowlist consumes validated numeric IDs.
ACTION = r'''
(async () => {
 const {songId,command,direction,expectedIds}=INPUT;
 const store=window.__songdesk.store, s=store.getStore(), list=s.playingList.curPlayingList;
 if(command==='clear') {
   if(JSON.stringify(list.map(x=>String(x.resourceId)))!==JSON.stringify(expectedIds))throw Error('歌单已变化，请重新确认清空');
   await store.getDispatch()({type:'playingList/removeItemFromCurPlayingListByIds',payload:{removeIds:list.slice(),triggerScene:'playingList'}});
   return true;
 }
 const item=list.find(x=>String(x.resourceId)===songId);
 if(!item)throw Error('歌曲已不在歌单，请刷新后重试');
 const dispatch=store.getDispatch(), current=String(s.playing.curPlaying?.resourceId||'');
 if(command==='toggle') {
   if(current===songId)await dispatch({type:s.playing.playingState===2?'playing/pause':'playing/resume',payload:{triggerScene:'playingList'}});
   else await dispatch({type:'playing/playOneTrackInPlayingList',payload:{item,switchType:'ui',triggerScene:'playingList'}});
 } else if(command==='move') {
   const index=list.indexOf(item), destination=index+direction;
   if(destination<0||destination>=list.length)throw Error('歌曲已在歌单边界');
   // Client offset is the insertion boundary BEFORE removing the moving item.
   await dispatch({type:'playingList/sortPlayingList',payload:{trackList:[item],options:{offset:direction<0?index-1:index+2}}});
 } else if(command==='delete') {
   await dispatch({type:'playingList/removeItemFromCurPlayingListByIds',payload:{removeIds:[item],triggerScene:'playingList'}});
 } else throw Error('不支持的歌单操作');
 return true;
})()
'''
