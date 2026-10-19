"""Desktop preferences, batch queue, previews and maintenance controls."""
import base64
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
import urllib.request
from engine import Control,validate_url
import preferences
from save_paths import suggested_path
from video import inspect_video,tools

ROOT=Path(__file__).resolve().parent

def parse_links(text):
    result=[]
    for line in text.splitlines():
        url=line.strip()
        if not url or url in result:continue
        validate_url(url);result.append(url)
        if len(result)>100:raise ValueError('Add up to 100 links at a time')
    if not result:raise ValueError('Paste at least one video link')
    return result

class ProductFeatures:
    def build_features(self):
        self.batch_control=None;self.maintenance=False;self.batch_errors=[];self.batch_links=[]
        self.settings=preferences.load(self.settings_path)
        self.connections.set(self.settings['connections'])
        self.tree.bind('<Double-1>',lambda e:self.show_details())
        batch=ttk.Frame(self.tabs,padding=14);settings=ttk.Frame(self.tabs,padding=14)
        self.tabs.add(batch,text=' Batch links ');self.tabs.add(settings,text=' Settings & tools ')
        ttk.Label(batch,text='One video link per line. Each successful link is queued separately.').pack(anchor='w')
        self.batch_text=tk.Text(batch,height=10,wrap='word');self.batch_text.pack(fill='both',expand=True,pady=8)
        bar=ttk.Frame(batch);bar.pack(fill='x')
        ttk.Button(bar,text='Find & queue videos',command=self.queue_batch).pack(side='left')
        ttk.Button(bar,text='Stop batch',command=lambda:self.batch_control and self.batch_control.stop('Batch stopped')).pack(side='left',padx=8)
        ttk.Button(bar,text='Show failed links',command=lambda:messagebox.showinfo('Batch failures','\n\n'.join(self.batch_errors) or 'No failures recorded.',parent=self.root)).pack(side='left')
        self.batch_status=tk.StringVar(value='Uses your saved folder and quality.');ttk.Label(batch,textvariable=self.batch_status,wraplength=850).pack(anchor='w',pady=8)
        self.pref_video=tk.StringVar(value=self.settings['video_folder']);self.pref_files=tk.StringVar(value=self.settings['file_folder'])
        self.pref_quality=tk.StringVar(value=self.settings['quality']);self.pref_adaptive=tk.BooleanVar(value=self.settings['adaptive'])
        for label,var in (('Video folder',self.pref_video),('File folder',self.pref_files)):
            ttk.Label(settings,text=label).pack(anchor='w');row=ttk.Frame(settings);row.pack(fill='x',pady=(4,8))
            ttk.Entry(row,textvariable=var).pack(side='left',fill='x',expand=True)
            ttk.Button(row,text='Browse',command=lambda v=var:self.pick_folder(v)).pack(side='left',padx=8)
        ttk.Label(settings,text='Default video quality').pack(anchor='w')
        ttk.Combobox(settings,textvariable=self.pref_quality,state='readonly',values=['best','2160','1440','1080','720','480','360']).pack(anchor='w',pady=6)
        ttk.Checkbutton(settings,text='Reduce concurrency when the server rejects requests',variable=self.pref_adaptive).pack(anchor='w')
        ttk.Button(settings,text='Save preferences',command=self.save_preferences).pack(anchor='w',pady=8)
        row=ttk.Frame(settings);row.pack(fill='x',pady=8)
        ttk.Button(row,text='Update video tools',command=lambda:self.maintain_tools(False)).pack(side='left')
        ttk.Button(row,text='Roll back tools',command=lambda:self.maintain_tools(True)).pack(side='left',padx=8)
        ttk.Button(row,text='Set up browser extension',command=self.browser_setup).pack(side='left')
        self.tool_status=tk.StringVar(value='Updates verify published checksums and retain one rollback copy.')
        ttk.Label(settings,textvariable=self.tool_status,wraplength=850).pack(anchor='w',pady=8)
    def pick_folder(self,var):
        value=filedialog.askdirectory(parent=self.root,initialdir=var.get(),mustexist=False)
        if value:var.set(value)
    def save_preferences(self):
        try:
            self.settings=preferences.save({'video_folder':self.pref_video.get(),'file_folder':self.pref_files.get(),'connections':self.connections.get(),'quality':self.pref_quality.get(),'adaptive':self.pref_adaptive.get()},self.settings_path)
            self.suggest_file();self.suggest_video(title=(self.video_info or {}).get('title'));self.tool_status.set('Preferences saved.')
        except Exception as exc:messagebox.showerror('Cannot save preferences',str(exc),parent=self.root)
    def selected_row(self):
        identity=self.selected();return next((r for r in self.store.rows() if r[0]==identity),None)
    def open_selected(self,folder=False):
        row=self.selected_row()
        if not row:return
        path=Path(row[2]);path=path.parent if folder else path
        if not path.exists():self.message.set('The file or folder does not exist yet.');return
        if not folder and path.suffix.lower() in ('.exe','.cmd','.bat','.ps1','.msi','.com','.vbs','.js','.scr'):
            if not messagebox.askyesno('Open downloaded program?','This file can run software. Open it?',parent=self.root):return
        try:os.startfile(str(path))
        except OSError as exc:self.message.set(str(exc))
    def clear_completed(self):
        self.store.remove_completed()
        for identity in self.tree.get_children():
            if not any(str(r[0])==identity for r in self.store.rows()):self.tree.delete(identity)
        self.message.set('Completed entries removed. Downloaded files were kept.')
    def show_details(self):
        row=self.selected_row()
        if row:messagebox.showinfo('Download details',f'{row[4]}\n\n{row[2]}\n\n{row[7] or "No errors recorded."}',parent=self.root)
    def queue_batch(self):
        if self.batch_control or self.maintenance:return
        try:links=parse_links(self.batch_text.get('1.0','end'));count=self.connections.get();preferences.validate({**self.settings,'connections':count})
        except Exception as exc:messagebox.showerror('Cannot add batch',str(exc),parent=self.root);return
        settings=dict(self.settings);control=Control();self.batch_control=control;self.batch_errors=[];self.batch_links=links;self.batch_status.set(f'Inspecting {len(links)} links…')
        def work():
            for index,url in enumerate(links,1):
                if control.event.is_set():break
                try:info=inspect_video(url,control);self.events.put(('batch-item',url,info,settings,count,index,len(links)))
                except Exception as exc:self.events.put(('batch-error',index,len(links),str(exc)))
            self.events.put(('batch-done',control.reason if control.event.is_set() else 'Batch inspection finished.'))
        threading.Thread(target=work,name='kora-batch',daemon=False).start()
    def preview_video(self):
        if not self.video_info:return
        info=dict(self.video_info);win=tk.Toplevel(self.root);win.title('Video preview');win.geometry('500x400')
        ttk.Label(win,text=info['title'],wraplength=460,font=('Segoe UI',14,'bold')).pack(padx=16,pady=12)
        duration=info.get('duration');sizes=[f['size'] for f in info['formats'] if isinstance(f.get('size'),(int,float))]
        ttk.Label(win,text=f'Duration: {duration if duration is not None else "Unknown"} seconds\nFormats: {len(info["formats"])}\nEstimated sizes: '+(f'{min(sizes)/1048576:.1f}–{max(sizes)/1048576:.1f} MB' if sizes else 'Unavailable'),wraplength=460).pack(padx=16)
        label=ttk.Label(win,text='Loading thumbnail…');label.pack(pady=12)
        url=info.get('thumbnail')
        if not url:label.configure(text='No thumbnail available.');return
        def fetch():
            try:
                validate_url(url)
                from engine import SafeRedirect
                with urllib.request.build_opener(SafeRedirect()).open(url,timeout=10) as response:data=response.read(4*1024*1024+1)
                if len(data)>4*1024*1024:raise ValueError('Thumbnail too large')
                _,ff=tools()
                result=subprocess.run([ff,'-v','error','-i','pipe:0','-vf','scale=420:230:force_original_aspect_ratio=decrease','-frames:v','1','-f','image2pipe','-vcodec','png','pipe:1'],input=data,capture_output=True,timeout=15,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                if result.returncode:raise ValueError('Thumbnail unavailable')
                self.events.put(('thumbnail',label,result.stdout))
            except Exception:self.events.put(('thumbnail',label,None))
        threading.Thread(target=fetch,daemon=True).start()
    def maintain_tools(self,rollback):
        if self.active or self.video_inspection or self.batch_control or self.maintenance:
            self.tool_status.set('Pause active downloads and finish video searches before maintaining tools.');return
        self.maintenance=True;self.tool_status.set('Restoring previous tools…' if rollback else 'Downloading and verifying tools…')
        def work():
            try:
                if rollback:
                    from tool_updates import rollback_tools
                    rollback_tools(ROOT)
                else:
                    from setup_video_tools import install
                    install(lock_app=False)
                self.events.put(('tools-done','Previous tools restored.' if rollback else 'Tools updated and checksums verified.'))
            except Exception as exc:self.events.put(('tools-done','Tool maintenance failed: '+str(exc)))
        threading.Thread(target=work,daemon=False).start()
    def browser_setup(self):
        win=tk.Toplevel(self.root);win.title('Browser setup');win.geometry('620x300')
        ttk.Label(win,text='1. Open your browser extensions page and enable Developer mode.\n2. Load unpacked and select the browser folder below.\n3. Copy the extension ID and register it here.\n4. In the extension, choose Detect, play your video, then Send to Kora.',wraplength=570).pack(padx=16,pady=16)
        ttk.Button(win,text='Open extension folder',command=lambda:os.startfile(str(ROOT/'browser'))).pack()
        identity=tk.StringVar();browser=tk.StringVar(value='Chrome')
        ttk.Entry(win,textvariable=identity,width=40).pack(pady=8);ttk.Combobox(win,textvariable=browser,values=['Chrome','Edge'],state='readonly').pack()
        def register():
            if not re.fullmatch('[a-p]{32}',identity.get()):messagebox.showerror('Invalid ID','Paste the 32-character extension ID.',parent=win);return
            result=subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'Install-Browser-Host.ps1'),'-ExtensionId',identity.get(),'-Browser',browser.get()],capture_output=True,text=True,timeout=20,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            messagebox.showinfo('Browser registration',result.stdout if result.returncode==0 else result.stderr,parent=win)
        ttk.Button(win,text='Register extension',command=register).pack(pady=8)
    def feature_event(self,event):
        kind=event[0]
        if kind=='batch-item':
            _,url,info,settings,count,index,total=event
            path=suggested_path(url,info['title'],self.reserved_paths(),folder=settings['video_folder'])
            params={'mode':'best','connections':count,'adaptive':settings['adaptive']}
            if settings['quality']!='best':params['height']=int(settings['quality'])
            self.store.add(url,str(path),count,'video',params);self.batch_status.set(f'{index}/{total}: queued {info["title"]}')
        elif kind=='batch-error':
            self.batch_errors.append(f'Link {event[1]}: {self.batch_links[event[1]-1]}\n{event[3]}')
            self.batch_status.set(f'{event[1]}/{event[2]} failed: {event[3]}')
        elif kind=='batch-done':self.batch_control=None;self.batch_status.set(event[1]+f' {len(self.batch_errors)} failed. See the queue for successful jobs.')
        elif kind=='tools-done':self.maintenance=False;self.tool_status.set(event[1])
        elif kind=='thumbnail':
            label,data=event[1:]
            if label.winfo_exists():
                if data:label.image=tk.PhotoImage(data=base64.b64encode(data));label.configure(image=label.image,text='')
                else:label.configure(text='Thumbnail unavailable.')
