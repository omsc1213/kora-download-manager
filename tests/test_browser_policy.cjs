const assert=require('node:assert/strict');
const {koraAllowed,koraMedia}=require('../browser/policy.js');
for(const u of ['https://youtube.com/watch?v=x','https://youtu.be/x','https://r1.googlevideo.com/x','https://www.youtube-nocookie.com/embed/x','blob:https://example.test/x'])assert.equal(koraAllowed(u),false,u);
assert.equal(koraAllowed('https://notyoutube.com/video'),true);
assert.equal(koraMedia('https://cdn.example.test/stream.m3u8?token=x'),true);
assert.equal(koraMedia('https://cdn.example.test/api/file','video/mp4'),true);
assert.equal(koraMedia('https://cdn.example.test/key','application/octet-stream'),false);
assert.equal(koraMedia('https://youtube.com/x.mp4','video/mp4'),false);
console.log('Browser URL/media policy checks passed');
