function koraAllowed(value) {
  try {
    const url = new URL(value), host = url.hostname.toLowerCase().replace(/\.$/, "");
    return ["http:", "https:"].includes(url.protocol) && !["youtube.com", "youtu.be", "youtube-nocookie.com", "youtubeeducation.com", "googlevideo.com", "youtube.googleapis.com", "youtubei.googleapis.com"].some(domain => host === domain || host.endsWith("." + domain));
  } catch { return false; }
}
function koraMedia(url, contentType = "", type = "") {
  return koraAllowed(url) && (type === "media" || /video\/|application\/(?:vnd\.apple\.mpegurl|x-mpegurl|dash\+xml)/i.test(contentType) || /\.(?:m3u8|mpd|mp4|webm|mov|m4v)(?:\?|$)/i.test(url));
}
if (typeof module !== "undefined") module.exports = {koraAllowed, koraMedia};
