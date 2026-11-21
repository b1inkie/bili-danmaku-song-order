/* Actual update state comes only from Python. No online HTML, simulated versions or restarts here. */
"use strict";
window.RealUpdater = (() => {
  const get = id => document.getElementById(id);
  let snapshot = null, requesting = false, confirmation = false;
  const active = !new URLSearchParams(location.search).has('preview') && !new URLSearchParams(location.search).has('updateDemo');
  function render(s) {
    snapshot = s;
    const busy=['checking','downloading','verifying','installing'].includes(s.phase);
    get('settings-update-badge').classList.toggle('hidden',!s.available);
    get('settings-update-badge').dataset.ready=String(s.phase==='ready');
    get('btn-settings').setAttribute('aria-label',s.available?'设置，有可用更新':'设置');
    get('btn-settings').title=s.available?'有新版本可更新':'设置';
    get('update-demo-current').textContent='v'+s.current+(s.frozen?'':'（源码运行）');
    get('update-demo-latest').textContent=s.latest?'v'+s.latest:'—';
    get('update-demo-backup').textContent=s.backup?'v'+s.backup:'无';
    get('update-demo-time').textContent=s.checkedAt||'尚未检查';
    const labels={idle:'未检查',checking:'检查中',available:'发现新版',latest:'已是最新版',downloading:'下载中',verifying:'校验中',ready:'等待安装',installing:'准备退出',error:'操作失败'};
    get('update-demo-status').textContent=labels[s.phase]||s.phase;
    get('update-demo-status').dataset.phase=s.phase;
    get('update-demo-message').textContent=s.message;
    get('update-demo-notes').classList.toggle('hidden',!s.notes);
    get('update-demo-notes').replaceChildren();
    if(s.notes){const p=document.createElement('p');p.style.whiteSpace='pre-line';p.textContent=s.notes;get('update-demo-notes').appendChild(p);}
    get('update-demo-progress-box').classList.toggle('hidden',!['downloading','verifying'].includes(s.phase));
    get('update-demo-progress').value=s.progress;get('update-demo-percent').textContent=s.progress+'%';
    get('update-demo-check').disabled=busy||s.phase==='ready'||confirmation;
    get('update-demo-download').classList.toggle('hidden',!s.available||s.phase==='ready'||!s.frozen);
    get('update-demo-download').disabled=busy||confirmation;
    get('update-demo-cancel').classList.toggle('hidden',!['downloading','verifying'].includes(s.phase));
    get('update-demo-install').classList.toggle('hidden',s.phase!=='ready');
    get('update-demo-install').disabled=confirmation;
    get('update-demo-rollback').disabled=!s.backup||busy||confirmation;
    get('update-recover').classList.toggle('hidden',!s.recovery);
    get('update-recover').disabled=busy||confirmation;
  }
  async function action(method,...args) {
    try { const value=await window.pywebview.api[method](...args);if(value?.phase)render(value); }
    catch(error){get('update-demo-message').textContent=error.message||String(error);}
  }
  async function poll() {
    if(requesting||!window.pywebview?.api?.update_state)return;
    requesting=true;
    try{render(await window.pywebview.api.update_state());}catch(_){}finally{requesting=false;}
  }
  async function install(rollback) {
    if(confirmation||!snapshot)return;
    confirmation=true;render(snapshot);
    try {
      const accepted=await ConfirmDialog.ask({title:rollback?'回退上一版本':'退出并更新',confirmText:rollback?'退出并回退':'退出并更新',
        message:(rollback?'将恢复上一版程序。':'新版本已下载并验证，将保留当前版本作为备份。')+'\n点歌台和小窗将关闭，接单暂时停止；网易云不会被关闭。\n配置、黑名单和用户主题不会被覆盖。请先保存工坊中的修改。'});
      if(accepted)await action('install_update',rollback);
    }finally{confirmation=false;if(snapshot)render(snapshot);}
  }
  function init() {
    if(!active)return;
    get('update-demo-scenarios')?.classList.add('hidden');
    get('update-mode-tag').textContent='GitHub 正式发布';
    get('update-mode-notice').textContent='从本项目 GitHub Release 检查更新。签名与哈希验证通过后才允许安装，不自动重启，不覆盖用户数据。源码运行只检查版本，不替换工作区。';
    get('update-schedule-note').textContent='界面启动5秒后首次后台检查，此后每4小时检查；可手动检查。更新失败不会打断直播。';
    get('update-demo-current').textContent='读取当前版本…';
    get('update-demo-check').textContent='检查更新';get('update-demo-download').textContent='下载更新';
    get('update-demo-install').textContent='退出并更新';get('update-demo-rollback').textContent='回退上一版本';
    get('update-demo-progress').setAttribute('aria-label','更新下载进度');
    get('update-demo-check').onclick=()=>action('check_update');
    get('update-demo-download').onclick=()=>action('download_update');
    get('update-demo-cancel').onclick=()=>action('cancel_update');
    get('update-demo-install').onclick=()=>install(false);
    get('update-demo-rollback').onclick=()=>install(true);
    get('update-recover').onclick=async()=>{
      if(await ConfirmDialog.ask({title:'恢复中断的更新',confirmText:'退出并恢复',message:'关闭当前点歌台，校验更新事务中的旧版文件并恢复。网易云和用户数据不变。请先保存工坊修改。'}))await action('recover_update');
    };
    window.addEventListener('pywebviewready',()=>{poll();setInterval(poll,500);});
  }
  return {init};
})();
document.addEventListener('DOMContentLoaded',()=>RealUpdater.init());
