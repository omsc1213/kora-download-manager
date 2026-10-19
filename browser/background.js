importScripts("policy.js");
let capture = null;
const loaded = chrome.storage.session.get("capture").then(data => { capture = data.capture || null; });
const saveCapture = () => chrome.storage.session.set({capture});
function remember(url, contentType = "", type = "") {
  if (!capture || Date.now() > capture.expires || !koraMedia(url, contentType, type)) return;
  if (capture.items.some(item => item.url === url)) return;
  capture.items.push({url,contentType,found:Date.now()});
  capture.items=capture.items.slice(-80);saveCapture();
}
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.removeAll(() => {
    for (const [id,title] of [["kora-file","Download file with Kora"],["kora-video","Download video link with Kora"]])
      chrome.contextMenus.create({id,title,contexts:["link"],targetUrlPatterns:["http://*/*","https://*/*"]});
  });
});
function sendToKora(url,kind,referer,reply) {
  if (!koraAllowed(url) || (referer && !koraAllowed(referer))) {reply({ok:false,error:"YouTube links are excluded."});return;}
  chrome.runtime.sendNativeMessage("com.kora.downloads",{action:"queue",kind,url,referer,user_agent:navigator.userAgent},response=>{
    const error=chrome.runtime.lastError;
    const value=error?{ok:false,error:"Kora host unavailable. Complete browser setup first."}:(response||{ok:false,error:"No response from Kora."});
    chrome.storage.local.set({lastResult:value.ok?"Queued. Open Kora to manage the download.":value.error});
    chrome.action.setBadgeText({text:value.ok?"Q":"!"});reply(value);
  });
}
chrome.contextMenus.onClicked.addListener((info,tab)=>{
  if (!["kora-file","kora-video"].includes(info.menuItemId)||!info.linkUrl)return;
  sendToKora(info.linkUrl,info.menuItemId==="kora-video"?"video":"file",info.menuItemId==="kora-video"?tab?.url:undefined,()=>{});
});
chrome.webRequest.onHeadersReceived.addListener(details=>{
  loaded.then(()=>{
    if (!capture||details.tabId!==capture.tabId||Date.now()>capture.expires)return;
    const ct=(details.responseHeaders||[]).find(h=>h.name.toLowerCase()==="content-type")?.value||"";
    remember(details.url,ct,details.type);
  });
},{urls:["http://*/*","https://*/*"]},["responseHeaders"]);
chrome.runtime.onMessage.addListener((message,sender,reply)=>{
  if(sender.id!==chrome.runtime.id)return false;
  loaded.then(async()=>{
    if(message.action==="start"){
      const [tab]=await chrome.tabs.query({active:true,currentWindow:true});
      if(!tab?.id||!koraAllowed(tab.url)){reply({ok:false,error:"Open a non-YouTube video page first."});return;}
      capture={tabId:tab.id,page:tab.url,expires:Date.now()+60000,items:[]};await saveCapture();
      try{
        const result=await chrome.scripting.executeScript({target:{tabId:tab.id,allFrames:true},func:()=>[...document.querySelectorAll("video, video source")].map(el=>el.currentSrc||el.src).filter(Boolean)});
        for(const frame of result)for(const url of frame.result||[])remember(url,"video/direct");
      }catch{}
      reply({ok:true,capture});
    }else if(message.action==="list"){
      if(capture&&Date.now()>capture.expires){capture.expires=0;await saveCapture();}
      reply({ok:true,capture});
    }else if(message.action==="stop"){
      capture=null;await saveCapture();reply({ok:true});
    }else if(message.action==="download"){
      const item=capture?.items.find(value=>value.url===message.url);
      if(!item){reply({ok:false,error:"Choose a detected stream first."});return;}
      sendToKora(item.url,"video",capture.page,reply);
    }else reply({ok:false,error:"Unknown action."});
  }).catch(error=>reply({ok:false,error:String(error)}));
  return true;
});
