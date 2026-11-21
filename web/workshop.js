"use strict";
const $ = id=>document.getElementById(id);
let schema, draft=null, assets={}, dirty=false, busy=false, mode="main";
let installedFonts = [];
let installedThemes = [], editingThemeId = null;
function updateDeleteButton() {
 const exists = installedThemes.some(theme => theme.id === editingThemeId);
 $('delete-theme').disabled = busy || !exists;
 $('delete-theme').title = exists ? '删除正在编辑的已保存主题' : '新草稿尚未保存，无需删除';
}
const labels={id:"主题 ID（英文小写/数字/连字符）",name:"主题名称 / 主播名",author:"作者",description:"简介",version:"主题版本",colors:"配色",text:"显示文案",character:"人物 OC",background:"背景",layout:"布局",decorations:"装饰",capture:"直播小窗",input:"输入框",secondary:"次要文字",muted:"辅助文字",accent:"强调色",button:"主按钮",buttonText:"按钮文字",border:"边框",signature:"英文签名 / 显示签名",heading:"大标题",subtitle:"副标题",eyebrow:"英文引导语",motto:"签名说明",image:"图片",scale:"人物缩放",x:"水平中心（%）",y:"向上偏移（px）",flip:"左右翻转",visible:"显示人物",dim:"背景暗化",characterSide:"人物所在侧",characterRatio:"人物栏比例",introHeight:"标题区高度（px）",cardOpacity:"卡片不透明度",glow:"光晕强度",rings:"显示装饰圆环",fade:"底部淡出强度",fontSize:"歌单字号（px）",compact:"默认精简显示"};
Object.assign(labels,{vertical:'竖排装饰文案',sceneNumber:'人物区装饰编号',sceneTitle:'人物区底部主题名',sectionNumber:'歌单前装饰编号'});
function status(text,error=false){$("status").textContent=text;$("status").dataset.error=String(error)}
function markDirty(){dirty=true;$("dirty-state").textContent="草稿 · 未保存"}
function get(path){return path.split('.').reduce((o,k)=>o[k],draft)}
function put(path,value){const parts=path.split('.'),last=parts.pop();parts.reduce((o,k)=>o[k],draft)[last]=value;markDirty();preview()}
function node(tag,text){const el=document.createElement(tag);if(text!=null)el.textContent=text;return el}
async function run(task){if(busy)return;busy=true;document.querySelectorAll('.header-actions button,.library-actions button,#theme-library').forEach(b=>b.disabled=true);try{await task()}catch(e){status(e.message||String(e),true)}finally{busy=false;document.querySelectorAll('.header-actions button,.library-actions button,#theme-library').forEach(b=>b.disabled=false);updateDeleteButton()}}
function loadPayload(payload){draft=structuredClone(payload.config);editingThemeId=draft.id;assets=payload.assets;dirty=false;updateDeleteButton();$('theme-library').value=installedThemes.some(t=>t.id===editingThemeId)?editingThemeId:'';$('dirty-state').textContent='已载入 · 未应用';renderFields();$('json-editor').value=JSON.stringify(draft,null,2);preview()}
function renderFields(){
 const parent=$("editor-fields");parent.replaceChildren();
 const render=(props,target,prefix="")=>{
  for(const [key,spec] of Object.entries(props)){
   if(['schemaVersion','template','fonts'].includes(key))continue;
   const path=prefix?prefix+'.'+key:key;
   if(spec.type==='object'){const group=node('fieldset'),legend=node('legend',labels[key]||key);group.append(legend);render(spec.properties,group,path);target.append(group);continue}
   const field=node('div');field.className='field';
   const backgroundLabels={scale:'背景缩放（倍）',x:'左右平移（px，正值向右）',y:'上下平移（px，正值向下）'};
   const label=node('label',(prefix==='background'&&backgroundLabels[key])||labels[key]||key);field.append(label);
   if(key==='image'){
    const tools=node('div');tools.className='image-tools';const choose=node('button','选择 PNG / 图片'),clear=node('button','清除');tools.append(choose,clear);
    const display=node('span',get(path)||'无图片');display.className='image-path';field.append(tools,display);
    choose.onclick=()=>run(async()=>{const result=await window.pywebview.api.choose_image();if(result){assets[result.path]=result.url;put(path,result.path);renderFields();status('图片已自动优化，透明底保留；请保存草稿。')}});
    clear.onclick=()=>{put(path,'');renderFields()};target.append(field);continue;
   }
   let input;
   if(spec.enum){input=node('select');spec.enum.forEach(v=>{const o=node('option',v==='left'?'左侧':v==='right'?'右侧':v);o.value=v;input.append(o)});input.value=get(path)}
   else{input=node('input');input.type=spec.type==='boolean'?'checkbox':spec.type==='number'?'range':spec.pattern?.startsWith('^#')?'color':'text';if(input.type==='checkbox')input.checked=get(path);else input.value=get(path);if(spec.maxLength)input.maxLength=spec.maxLength;
    if(spec.type==='number'){input.min=spec.minimum;input.max=spec.maximum;input.step=['introHeight','fontSize','x','y'].includes(key)?1:.01;const out=node('output',get(path));label.append(out);input.addEventListener('input',()=>out.textContent=input.value)}
   }
   input.id='field-'+path;label.htmlFor=input.id;
   input.addEventListener('input',()=>put(path,spec.type==='boolean'?input.checked:spec.type==='number'?Number(input.value):input.value));field.append(input);target.append(field);
   if(prefix==='text') {
    field.classList.add('text-font-field');
    const fontLabel=node('label','字体');const select=node('select');
    select.id='font-'+key;fontLabel.htmlFor=select.id;
    select.setAttribute('aria-label',(labels[key]||key)+'字体');
    select.append(new Option('模板默认字体',''));
    const selected=draft.fonts?.[key]||'';
    if(selected&&!installedFonts.includes(selected))select.append(new Option(selected+'（本机可能未安装，将自动回退）',selected));
    installedFonts.forEach(name=>select.append(new Option(name,name)));
    select.value=selected;
    select.onchange=()=>{if(!draft.fonts)draft.fonts={};put('fonts.'+key,select.value)};
    field.append(fontLabel,select);
   }
  }
 };render(schema.properties,parent);
}
function preview(){if(!draft)return;const frame=$("theme-preview");frame.contentWindow?.postMessage({type:'songdesk-theme-preview',payload:{config:draft,assets}},'*');fitPreview()}
function fitPreview(){const [w,h]=mode==='capture'?[420,620]:$("preview-size").value.split(',').map(Number),stage=$("preview-stage");const scale=Math.min((stage.clientWidth-28)/w,(stage.clientHeight-28)/h,1);const frame=$("theme-preview");frame.style.width=w+'px';frame.style.height=h+'px';frame.style.transform=`scale(${Math.max(.1,scale)})`;$("preview-wrap").style.width=w*scale+'px';$("preview-wrap").style.height=h*scale+'px'}
async function library(){installedThemes=(await window.pywebview.api.bootstrap()).themes;const select=$('theme-library');select.replaceChildren(new Option('选择主题…',''));installedThemes.forEach(t=>select.add(new Option(t.name,t.id)));select.value=installedThemes.some(t=>t.id===editingThemeId)?editingThemeId:'';updateDeleteButton()}
async function save(){const result=await window.pywebview.api.save_theme(draft);loadPayload(result);await library();$("theme-library").value=draft.id;$("dirty-state").textContent='已保存';status('主题已保存；主界面未切换，点击“保存并应用”即可启用。')}
async function discard(){return !dirty||await ConfirmDialog.ask({title:'放弃未保存修改',message:'草稿尚未保存，确定放弃当前修改？',confirmText:'放弃修改',danger:true})}
window.addEventListener('message',e=>{if(e.source===$("theme-preview").contentWindow&&e.data?.type==='songdesk-preview-ready')setTimeout(preview,80)});
window.addEventListener('resize',fitPreview);
window.addEventListener('beforeunload',e=>{if(dirty){e.preventDefault();e.returnValue='草稿尚未保存'}});
window.addEventListener('pywebviewready',()=>run(async()=>{
 const info=await window.pywebview.api.bootstrap();schema=info.schema;installedFonts=info.fonts||[];$("storage-path").textContent='本地主题目录：'+info.storage;
 await library();loadPayload(await window.pywebview.api.new_theme());status('草稿已创建。选择PNG图片、调整参数，右侧实时预览。');markDirty();
 $("copy-guide").onclick=()=>run(async()=>{const result=await window.pywebview.api.copy_theme_guide();if(result.copied)status('已复制 AI 提示词，直接粘贴给 AI，再补充风格要求和 PNG 素材即可。')});
 $('open-theme-directory').onclick=()=>run(async()=>{await window.pywebview.api.open_theme_directory();status('已打开本地主题目录，每个文件夹是一套独立主题。')});
 $('delete-theme').onclick=()=>run(async()=>{
  const theme=installedThemes.find(t=>t.id===editingThemeId);if(!theme)return;
  const confirmed=await ConfirmDialog.ask({title:'删除主题',message:`删除「${theme.name}」及其本地图片？${dirty?'未保存的修改也将丢弃。':''}\n如果正在使用此主题，主窗口和小窗将切回经典深色。删除后可重新导入主题包。`,confirmText:'删除主题',danger:true});
  if(!confirmed)return;
  await window.pywebview.api.delete_theme(theme.id);
  await library();loadPayload(await window.pywebview.api.new_theme());markDirty();
  status('主题已删除，已创建新的未保存草稿。');
 });
 $("new-theme").onclick=()=>run(async()=>{if(await discard()){loadPayload(await window.pywebview.api.new_theme());markDirty()}});
 $('theme-library').onchange=()=>run(async()=>{const chosen=$('theme-library').value;if(chosen&&await discard())loadPayload(await window.pywebview.api.load_theme(chosen));else $('theme-library').value=installedThemes.some(t=>t.id===editingThemeId)?editingThemeId:''});
 $("import-theme").onclick=()=>run(async()=>{if(!await discard())return;const p=await window.pywebview.api.import_theme();if(p){loadPayload(p);await library();status('导入成功，尚未应用。')}});
 $("save-theme").onclick=()=>run(save);
 $("apply-theme").onclick=()=>run(async()=>{await save();await window.pywebview.api.apply_theme(draft.id);status('已保存并应用，主窗口和直播小窗会自动同步。')});
 $("export-theme").onclick=()=>run(async()=>{await save();if(await window.pywebview.api.export_theme(draft.id))status('主题包已导出，可分享给其他用户或AI修改。')});
 $("refresh-json").onclick=()=>{$("json-editor").value=JSON.stringify(draft,null,2)};
 $("load-json").onclick=()=>run(async()=>{const value=JSON.parse($("json-editor").value);const payload=await window.pywebview.api.validate_theme(value);loadPayload(payload);markDirty();status('JSON校验通过并载入草稿，尚未保存。')});
 for(const target of ['main','capture'])$("preview-"+target).onclick=()=>{mode=target;$("preview-main").setAttribute('aria-pressed',String(mode==='main'));$("preview-capture").setAttribute('aria-pressed',String(mode==='capture'));$("theme-preview").src=mode==='main'?'index.html?preview=1':'capture.html?preview=1';fitPreview()};
 $("preview-size").onchange=fitPreview;$("theme-preview").addEventListener('load',()=>setTimeout(preview,100));
}));
