const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

// Test routing decisions without replacing native wheel behavior with a fake UI.
function fixture() {
  class Element {
    constructor({parent=null, overflow='visible', top=0, height=100, content=100, matches=[]}={}) {
      this.parentElement=parent; this.overflow=overflow; this.scrollTop=top;
      this.clientHeight=height; this.scrollHeight=content; this.matches=matches;
    }
    closest(selector) { return this.matches.includes(selector) ? this : this.parentElement?.closest(selector) || null; }
  }
  const listeners={}, history=new Element({overflow:'auto',top:200,height:400,content:1200});
  let modal=null;
  const document={querySelector:selector=>selector==='#messages'?history:selector==='dialog[open]'?modal:null,
    addEventListener:(type,handler)=>{listeners[type]=handler;}};
  const context=vm.createContext({Element,document,window:{},getComputedStyle:e=>({overflowY:e.overflow})});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../app/static/js/api.js'),'utf8'),context);
  const workspace=new Element({matches:['.workspace']}), header=new Element({parent:workspace});
  return {Element,context,listeners,history,workspace,header,setModal:value=>{modal=value;}};
}

test('wheel over fixed header scrolls chat, normal wheel units stay intact',()=>{
  const f=fixture();let prevented=false;
  f.listeners.wheel({target:f.header,deltaY:80,deltaX:0,deltaMode:0,preventDefault:()=>{prevented=true;}});
  assert.equal(f.history.scrollTop,280);assert.ok(prevented);
});
test('scrollable textarea keeps native behavior, at its edge chat receives wheel',()=>{
  const f=fixture(), field=new f.Element({parent:f.workspace,overflow:'auto',top:20,height:50,content:100});
  assert.equal(f.context.scrollDestination(field,20),null);
  field.scrollTop=50;assert.equal(f.context.scrollDestination(field,20),f.history);
});
test('dialogs, sidebar, select and zoom gestures do not scroll the chat',()=>{
  const f=fixture();
  for(const matches of [['.sidebar'],['select, input, [contenteditable=true]']]) {
    assert.equal(f.context.scrollDestination(new f.Element({parent:f.workspace,matches}),20),null);
  }
  f.listeners.wheel({target:f.header,deltaY:80,deltaX:0,ctrlKey:true});assert.equal(f.history.scrollTop,200);
  f.setModal(new f.Element());assert.equal(f.context.scrollDestination(f.header,20),null);
  const dialog=new f.Element({matches:['dialog[open]']});f.setModal(dialog);
  assert.equal(f.context.scrollDestination(dialog,20),null);
});
test('native message scrolling and horizontal gestures are untouched',()=>{
  const f=fixture();assert.equal(f.context.scrollDestination(f.history,20),null);
  f.listeners.wheel({target:f.header,deltaY:20,deltaX:100});assert.equal(f.history.scrollTop,200);
});
test('PageUp navigates chat without intercepting text editing',()=>{
  const f=fixture();let prevented=false;
  f.listeners.keydown({target:f.header,key:'PageDown',preventDefault:()=>{prevented=true;}});
  assert.equal(f.history.scrollTop,540);assert.ok(prevented);
  const input=new f.Element({matches:['input,textarea,select,[contenteditable=true],dialog[open]']});
  f.listeners.keydown({target:input,key:'Home'});assert.equal(f.history.scrollTop,540);
});
