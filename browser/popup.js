const status=document.getElementById("status"),streams=document.getElementById("streams");
let noticeUntil=0;
async function refresh(){
  const result=await chrome.runtime.sendMessage({action:"list"}),selected=streams.value;streams.replaceChildren();
  for(const item of result.capture?.items||[]){
    const option=document.createElement("option");option.value=item.url;
    try{const url=new URL(item.url);option.textContent=url.hostname+" "+url.pathname.slice(-65);}catch{option.textContent="Video stream";}
    streams.append(option);
  }
  if([...streams.options].some(o=>o.value===selected))streams.value=selected;
  if(Date.now()<noticeUntil)return;
  status.textContent=result.capture?streams.options.length+" stream(s). "+(result.capture.expires>Date.now()?"Detection active.":"Detection ended.")+" Prefer m3u8/mpd playlists for audio and quality options.":"No tab is being monitored.";
}
function notice(text){noticeUntil=Date.now()+6000;status.textContent=text;}
document.getElementById("start").onclick=async()=>{
  const granted=await chrome.permissions.request({origins:["http://*/*","https://*/*"]});
  if(!granted){notice("Site access was not granted. Detection is off.");return;}
  const result=await chrome.runtime.sendMessage({action:"start"});if(!result.ok)notice(result.error);else await refresh();
};
document.getElementById("stop").onclick=async()=>{await chrome.runtime.sendMessage({action:"stop"});noticeUntil=0;await refresh();};
document.getElementById("download").onclick=async()=>{
  if(!streams.value){notice("No media selected. Start detection and play the video.");return;}
  const result=await chrome.runtime.sendMessage({action:"download",url:streams.value});
  notice(result.ok?"Queued. Open Kora to see progress.":result.error);
};
refresh().catch(error=>notice(String(error)));
setInterval(()=>refresh().catch(()=>{}),2000);
