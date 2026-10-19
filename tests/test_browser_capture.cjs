const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const root=path.join(__dirname,'../browser'),events={},session={},native=[];
const event=name=>({addListener(fn){events[name]=fn;}});
const chrome={
  runtime:{id:'kora-test',lastError:null,onInstalled:event('installed'),onMessage:event('message'),sendNativeMessage(host,data,cb){native.push({host,data});cb({ok:true,job_id:1});}},
  contextMenus:{onClicked:event('menu'),removeAll(cb){cb();},create(){}},
  webRequest:{onHeadersReceived:event('headers')},
  storage:{session:{async get(){return session;},async set(data){Object.assign(session,data);}},local:{async set(){}}},
  action:{setBadgeText(){}},tabs:{async query(){return [{id:7,url:'https://example.test/watch'}];}},
  scripting:{async executeScript(){return [{result:['blob:https://example.test/a','https://cdn.example.test/video.mp4']}];}}
};
const context=vm.createContext({chrome,navigator:{userAgent:'Kora test browser'},URL,Date,Promise,console});
context.importScripts=name=>vm.runInContext(fs.readFileSync(path.join(root,name),'utf8'),context);
vm.runInContext(fs.readFileSync(path.join(root,'background.js'),'utf8'),context);
const send=data=>new Promise(resolve=>events.message(data,{id:'kora-test'},resolve));
(async()=>{
  assert.equal((await send({action:'start'})).ok,true);
  let result=await send({action:'list'});assert.equal(result.capture.items.length,1);
  events.headers({tabId:8,url:'https://other.test/no.mp4',type:'media',responseHeaders:[]});
  events.headers({tabId:7,url:'https://r1.googlevideo.com/no.mp4',type:'media',responseHeaders:[]});
  events.headers({tabId:7,url:'https://cdn.example.test/master.m3u8',type:'xmlhttprequest',responseHeaders:[{name:'Content-Type',value:'application/vnd.apple.mpegurl'}]});
  await new Promise(resolve=>setImmediate(resolve));
  result=await send({action:'list'});assert.equal(result.capture.items.length,2);
  assert.equal((await send({action:'download',url:'https://other.test/no.mp4'})).ok,false);
  assert.equal((await send({action:'download',url:'https://cdn.example.test/master.m3u8'})).ok,true);
  assert.equal(native.length,1);assert.equal(native[0].data.kind,'video');assert.equal(native[0].data.referer,'https://example.test/watch');
  await send({action:'stop'});assert.equal((await send({action:'list'})).capture,null);
  console.log('Browser capture simulation passed: tab isolation, YouTube exclusion, stream detection, explicit selection, native message and clear.');
})().catch(error=>{console.error(error);process.exitCode=1;});
