"""Generate the public theme schema and template; no application runtime side effects."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bootstrap import setup
import os
os.chdir(setup())
import json
from pathlib import Path
s=lambda default,maximum=100:{'type':'string','maxLength':maximum,'default':default}
n=lambda default,lo,hi:{'type':'number','minimum':lo,'maximum':hi,'default':default}
b=lambda default:{'type':'boolean','default':default}
color=lambda value:{'type':'string','pattern':'^#[0-9a-fA-F]{6}$','default':value}
image=lambda:{'type':'string','pattern':r'^$|^assets/[A-Za-z0-9_-]+\.(png|jpg|jpeg|webp)$','maxLength':160,'default':''}
obj=lambda props:{'type':'object','additionalProperties':False,'properties':props,'default':{}}
props={
 'schemaVersion':{'const':1},'id':{'type':'string','pattern':'^[a-z][a-z0-9-]{2,47}$'},'name':s('我的主题',40),
 'author':s('',60),'description':s('',300),'version':s('1.0.0',30),'template':{'const':'rose-nocturne'},
 'colors':obj({k:color(v) for k,v in {'background':'#110e14','card':'#201820','input':'#2a2028','text':'#f5e9dc','secondary':'#c7acaf','muted':'#a38690','accent':'#dc8c9b','button':'#edd7c2','buttonText':'#39202b','border':'#4c333e'}.items()}),
 'text':obj({'name':s('这里是名字',24),'signature':s('这里是签名',32),'heading':s('这里是主标题',32),'subtitle':s('这里是副标题',60),'eyebrow':s('这里是引导语',60),'motto':s('这里是签名说明',80),'vertical':s('',60),'sceneNumber':s('',12),'sceneTitle':s('',60),'sectionNumber':s('',12)}),
 'fonts':obj({key:{'type':'string','maxLength':100,'pattern':r'^[^\x00-\x1f\x7f]*$','default':''} for key in ('name','signature','heading','subtitle','eyebrow','motto','vertical','sceneNumber','sceneTitle','sectionNumber')}),
 'character':obj({'image':image(),'scale':n(1,.5,1.6),'x':n(50,15,85),'y':n(0,-100,100),'flip':b(False),'visible':b(True)}),
 'background':obj({'image':image(),'dim':n(.65,0,1),'scale':n(1,.5,3),'x':n(0,-1000,1000),'y':n(0,-1000,1000)}),
 'layout':obj({'characterSide':{'enum':['left','right'],'default':'left'},'characterRatio':n(.43,.28,.43),'introHeight':n(118,90,140),'cardOpacity':n(.72,.4,1)}),
 'decorations':obj({'glow':n(.3,0,1),'rings':b(True),'fade':n(.9,0,1),'signature':b(True)}),
 'capture':obj({'background':color('#1b141e'),'card':color('#2b1b28'),'fontSize':n(14,12,18),'compact':b(False)})}
schema={'$schema':'https://json-schema.org/draft/2020-12/schema','title':'Songdesk Theme v1','type':'object','additionalProperties':False,'required':['schemaVersion','id','name','template'],'properties':props}
def defaults(p):
 if p.get('type')=='object':return {k:defaults(v) for k,v in p['properties'].items() if 'default'in v or 'const'in v}
 return p.get('const',p.get('default'))
template=defaults(schema);template.update(id='rose-nocturne-template',name='我的主题 · 制作草稿')
template['text'].update(vertical='这里是竖排文案',sceneNumber='01',sceneTitle='这里是主题名',sectionNumber='01')
Path('web/themes').mkdir(parents=True,exist_ok=True)
Path('web/theme.schema.json').write_text(json.dumps(schema,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
Path('web/themes/rose-nocturne.json').write_text(json.dumps(template,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
Path('docs/themes/examples/minimal').mkdir(parents=True,exist_ok=True)
Path('docs/themes/examples/minimal/theme.json').write_text(json.dumps({'schemaVersion':1,'id':'my-first-theme','name':'我的点歌室','template':'rose-nocturne'},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
Path('docs/themes/examples/rose-nocturne').mkdir(parents=True,exist_ok=True)
template['character']['image']='assets/character.png'
Path('docs/themes/examples/rose-nocturne/theme.json').write_text(json.dumps(template,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
