"""Kora desktop interface; workers never call Tk or SQLite UI connections."""
import json
from pathlib import Path
import queue
import threading
import time
import tkinter as tk
from tkinter import filedialog,messagebox,ttk

from engine import Control,Interrupted,download,validate_url,job_lock
from queue_store import Store
from rea_bridge import workflow
from video import inspect_video,download_video
from save_paths import suggested_path,video_folder
from product_features import ProductFeatures
import preferences

ROOT=Path(__file__).resolve().parent

def readable(value):
    if value is None:return 'Unknown'
    for unit in ('B','KB','MB','GB','TB'):
        if value<1024 or unit=='TB': return f'{value:.1f} {unit}'
        value/=1024

class App(ProductFeatures):
    def __init__(self,root,db_path=None,auto_start=True):
        self.root=root;self.auto_start=auto_start;root.title('Kora Download Manager');root.geometry('1050x680');root.minsize(850,520)
        self.events=queue.Queue();self.active=None;self.analysis=None;self.video_inspection=None;self.video_info=None;self.video_source=None;self.closing=False;self.last_progress={}
        path=Path(db_path) if db_path else preferences.data_dir()/'jobs.db';path.parent.mkdir(parents=True,exist_ok=True)
        self.settings_path=path.parent/'settings.json'
        self.store=Store(path)
        style=ttk.Style(root);style.theme_use('clam')
        style.configure('Treeview',rowheight=32,font=('Segoe UI',10));style.configure('Treeview.Heading',font=('Segoe UI',10,'bold'))
        style.configure('TButton',padding=(12,8));style.configure('TLabel',font=('Segoe UI',10))
        outer=ttk.Frame(root,padding=20);outer.pack(fill='both',expand=True)
        ttk.Label(outer,text='KORA',font=('Segoe UI',25,'bold')).pack(anchor='w')
        ttk.Label(outer,text='Your downloads, ready to pick up where you left off.',foreground='#526070').pack(anchor='w',pady=(0,16))
        tabs=ttk.Notebook(outer);tabs.pack(fill='both',expand=True)
        downloads=ttk.Frame(tabs,padding=14);videos=ttk.Frame(tabs,padding=14);advanced=ttk.Frame(tabs,padding=14)
        tabs.add(downloads,text=' Queue & files ');tabs.add(videos,text=' Video links ');tabs.add(advanced,text=' REA investigation ')
        self.tabs=tabs;self.downloads_tab=downloads
        downloads.columnconfigure(0,weight=1);downloads.rowconfigure(2,weight=1)
        form=ttk.Frame(downloads);form.grid(row=0,column=0,sticky='ew')
        self.url=tk.StringVar();self.destination=tk.StringVar();self.connections=tk.IntVar(value=8)
        ttk.Label(form,text='Download link').grid(row=0,column=0,sticky='w')
        ttk.Entry(form,textvariable=self.url).grid(row=1,column=0,columnspan=3,sticky='ew',pady=(4,10))
        ttk.Label(form,text='Save file as').grid(row=2,column=0,sticky='w')
        ttk.Entry(form,textvariable=self.destination).grid(row=3,column=0,columnspan=2,sticky='ew',pady=(4,10))
        ttk.Button(form,text='Browse…',command=self.browse).grid(row=3,column=2,padx=(8,0))
        form.columnconfigure(0,weight=1)
        actions=ttk.Frame(downloads);actions.grid(row=1,column=0,sticky='ew',pady=(0,14))
        ttk.Button(actions,text='Add download',command=self.add).pack(side='left')
        ttk.Label(actions,text=' Connections ').pack(side='left',padx=(12,0))
        ttk.Spinbox(actions,from_=1,to=16,width=4,textvariable=self.connections).pack(side='left')
        ttk.Button(actions,text='Resume / Retry',command=self.resume).pack(side='right')
        ttk.Button(actions,text='Pause',command=lambda:self.stop('Paused')).pack(side='right',padx=6)
        ttk.Button(actions,text='Cancel',command=lambda:self.stop('Cancelled')).pack(side='right')
        extra=ttk.Frame(downloads);extra.grid(row=5,column=0,sticky='ew',pady=(8,0))
        for title,command in [('Open file',self.open_selected),('Open folder',lambda:self.open_selected(True)),('Details / errors',self.show_details),('Clear completed',self.clear_completed)]:
            ttk.Button(extra,text=title,command=command).pack(side='left',padx=(0,5))
        list_frame=ttk.Frame(downloads);list_frame.grid(row=2,column=0,sticky='nsew')
        self.tree=ttk.Treeview(list_frame,columns=('name','status','progress','speed','eta'),show='headings',height=6,selectmode='browse')
        for name,title,width in [('name','File',310),('status','Status',110),('progress','Progress',180),('speed','Speed',110),('eta','Time left',100)]:
            self.tree.heading(name,text=title);self.tree.column(name,width=width,stretch=name in ('name','progress'))
        self.tree.pack(side='left',fill='both',expand=True)
        scrollbar=ttk.Scrollbar(list_frame,orient='vertical',command=self.tree.yview);scrollbar.pack(side='right',fill='y');self.tree.configure(yscrollcommand=scrollbar.set)
        self.progress=ttk.Progressbar(downloads,maximum=100);self.progress.grid(row=3,column=0,sticky='ew',pady=(12,6))
        self.message=tk.StringVar(value='Ready. Add a link and choose where to save it.')
        ttk.Label(downloads,textvariable=self.message,wraplength=900).grid(row=4,column=0,sticky='w')
        self.video_url=tk.StringVar();self.video_destination=tk.StringVar();self.video_quality=tk.StringVar(value='Best available')
        self._auto_video_path='';self._auto_file_path=''
        self.url.trace_add('write',self.suggest_file)
        self.video_url.trace_add('write',self.suggest_video)
        self.video_status=tk.StringVar(value='Paste a video page or direct stream link. YouTube is excluded.')
        ttk.Label(videos,text='Download a video',font=('Segoe UI',18,'bold')).pack(anchor='w')
        ttk.Label(videos,text='Find the available video quality before adding it to your queue.').pack(anchor='w',pady=(4,14))
        ttk.Label(videos,text='Video link').pack(anchor='w')
        ttk.Entry(videos,textvariable=self.video_url).pack(fill='x',pady=(4,10))
        find_bar=ttk.Frame(videos);find_bar.pack(fill='x')
        ttk.Button(find_bar,text='Find video',command=self.find_video).pack(side='left')
        ttk.Button(find_bar,text='Stop searching',command=self.stop_video_inspection).pack(side='left',padx=8)
        ttk.Button(find_bar,text='Preview',command=self.preview_video).pack(side='left')
        ttk.Label(videos,textvariable=self.video_status,wraplength=900).pack(anchor='w',pady=(12,14))
        ttk.Label(videos,text='Quality').pack(anchor='w')
        self.quality_box=ttk.Combobox(videos,textvariable=self.video_quality,state='readonly',values=['Best available'],width=65)
        self.quality_box.pack(fill='x',pady=(4,12));self.video_choices={'Best available':{'mode':'best'}}
        ttk.Label(videos,text='Save video as').pack(anchor='w')
        save=ttk.Frame(videos);save.pack(fill='x',pady=(4,12))
        ttk.Entry(save,textvariable=self.video_destination).pack(side='left',fill='x',expand=True)
        ttk.Button(save,text='Browse…',command=self.browse_video).pack(side='left',padx=(8,0))
        ttk.Button(videos,text='Add video to queue',command=self.add_video).pack(anchor='w')
        ttk.Label(videos,text='Default folder: set your preferred location in Settings & tools.',wraplength=900).pack(anchor='w',pady=(8,0))
        ttk.Label(videos,text='Speed: up to 8 stream fragments at once. Queue connections control video parallelism too.',wraplength=900).pack(anchor='w',pady=(4,0))
        ttk.Label(videos,text='If a page cannot be resolved, use the Kora browser extension to detect accessible video streams while playing it.',wraplength=900).pack(anchor='w',pady=(18,0))
        ttk.Label(advanced,text='Inspect a local application',font=('Segoe UI',16,'bold')).pack(anchor='w')
        ttk.Label(advanced,text='Read-only REA checks. Results include the input hash, provider, limitations and evidence records.',wraplength=880).pack(anchor='w',pady=(6,14))
        self.target=tk.StringVar(value=r'')
        ttk.Entry(advanced,textvariable=self.target).pack(fill='x')
        bar=ttk.Frame(advanced);bar.pack(fill='x',pady=10)
        ttk.Button(bar,text='Choose application',command=self.choose_target).pack(side='left')
        ttk.Button(bar,text='Start investigation',command=self.investigate).pack(side='left',padx=8)
        ttk.Button(bar,text='Stop investigation',command=self.stop_analysis).pack(side='left')
        self.rea_progress=ttk.Progressbar(advanced,maximum=3);self.rea_progress.pack(fill='x',pady=(0,8))
        self.rea_log=tk.Text(advanced,height=12,wrap='word',font=('Consolas',10),state='disabled');self.rea_log.pack(fill='both',expand=True)
        self.build_features()
        ttk.Label(outer,text='Kora 0.4 • Batch videos, saved preferences & tools',foreground='#687381').pack(anchor='w',pady=(12,0))
        root.protocol('WM_DELETE_WINDOW',self.close);self.refresh();root.after(100,self.pump)
    def reserved_paths(self):
        return [row[2] for row in self.store.rows() if row[4]!='Cancelled']
    def suggest_file(self,*_):
        current=self.destination.get()
        if not current or current==self._auto_file_path:
            url=self.url.get().strip()
            self._auto_file_path=str(suggested_path(url,reserved=self.reserved_paths(),video=False,folder=self.settings['file_folder'])) if url else ''
            self.destination.set(self._auto_file_path)
    def suggest_video(self,*_,title=None):
        current=self.video_destination.get()
        if not current or current==self._auto_video_path:
            url=self.video_url.get().strip()
            self._auto_video_path=str(suggested_path(url,title,reserved=self.reserved_paths(),folder=self.settings['video_folder'])) if url else ''
            self.video_destination.set(self._auto_video_path)
    def browse(self):
        path=filedialog.asksaveasfilename(parent=self.root,title='Save download as')
        if path:self.destination.set(path)
    def choose_target(self):
        path=filedialog.askopenfilename(parent=self.root,title='Choose application')
        if path:self.target.set(path)
    def browse_video(self):
        current=Path(self.video_destination.get()) if self.video_destination.get() else video_folder()/'Video.mp4'
        path=filedialog.asksaveasfilename(parent=self.root,title='Save video as',initialdir=str(current.parent),initialfile=current.name,defaultextension='.mp4',filetypes=[('MP4 video','*.mp4'),('Matroska video','*.mkv'),('WebM video','*.webm')])
        if path:self.video_destination.set(path)
    def find_video(self):
        if self.video_inspection or self.maintenance:return
        url=self.video_url.get().strip()
        try:validate_url(url)
        except Exception as exc:messagebox.showerror('Cannot inspect video',str(exc),parent=self.root);return
        control=Control();self.video_inspection=control;self.video_info=None;self.video_source=None
        self.video_status.set('Finding available video formats…')
        def find():
            try:self.events.put(('video-info',url,inspect_video(url,control)))
            except Exception as exc:self.events.put(('video-error',str(exc)))
        threading.Thread(target=find,name='kora-video-inspection',daemon=False).start()
    def stop_video_inspection(self):
        if self.video_inspection:self.video_inspection.stop('Search cancelled')
    def add_video(self):
        try:
            url=self.video_url.get().strip();validate_url(url)
            if not self.video_info or url!=self.video_source:raise ValueError('Select Find video for this link first')
            if not self.video_destination.get().strip():raise ValueError('Choose a video filename')
            path=Path(self.video_destination.get().strip()).absolute()
            if path.suffix.lower() not in ('.mp4','.mkv','.webm','.mov'):raise ValueError('Choose MP4, MKV, WebM or MOV')
            if path.exists():raise ValueError('That file already exists')
            if any(Path(row[2])==path and row[4] not in ('Completed','Cancelled') for row in self.store.rows()):raise ValueError('That destination is already in the queue')
            count=self.connections.get()
            if not 1<=count<=16:raise ValueError('Connections must be 1 to 16')
            selection={**self.video_choices[self.video_quality.get()],'connections':count,'adaptive':self.settings['adaptive']}
            self.store.add(url,str(path),count,kind='video',params=selection);self.refresh();self.tabs.select(self.downloads_tab)
            if str(path)==self._auto_video_path:self.suggest_video(title=self.video_info['title'])
            self.message.set('Video added to the download queue.')
        except Exception as exc:messagebox.showerror('Cannot add video',str(exc),parent=self.root)
    def add(self):
        try:
            url=self.url.get().strip();validate_url(url)
            if not self.destination.get().strip():raise ValueError('Choose a filename')
            path=Path(self.destination.get().strip()).absolute();count=self.connections.get()
            if not 1<=count<=16:raise ValueError('Connections must be 1 to 16')
            if path.exists():raise ValueError('That file already exists; choose another filename')
            if any(Path(row[2])==path and row[4] not in ('Completed','Cancelled') for row in self.store.rows()):raise ValueError('That destination is already in the queue')
            self.store.add(url,str(path),count);self.url.set('');self.destination.set('');self.refresh()
        except Exception as exc:messagebox.showerror('Cannot add download',str(exc),parent=self.root)
    def selected(self):
        values=self.tree.selection()
        return int(values[0]) if values else (self.active[0] if self.active else None)
    def resume(self):
        identity=self.selected()
        if identity is None:return
        row=next(r for r in self.store.rows() if r[0]==identity)
        if row[4] in ('Paused','Cancelled','Failed'):self.store.update(identity,status='Queued',note='');self.refresh()
    def stop(self,reason):
        identity=self.selected()
        if self.active and self.active[0]==identity:
            self.active[1].stop(reason);self.store.update(identity,status='Pausing' if reason=='Paused' else 'Cancelling')
        elif identity is not None:
            row=next(r for r in self.store.rows() if r[0]==identity)
            if row[4]!='Completed':self.store.update(identity,status=reason)
        self.refresh()
    def start_job(self,row):
        identity,url,path,count,*_=row;control=Control();self.active=(identity,control);self.store.update(identity,status='Downloading',note='')
        def work():
            last=0
            def report(value):
                nonlocal last
                if time.monotonic()-last>.15:last=time.monotonic();self.events.put(('progress',identity,value))
            try:
                if len(row)>8 and row[8]=='video':result=download_video(url,path,json.loads(row[9]),control,report)
                else:result=download(url,path,count,control,report,adaptive=self.settings['adaptive'])
                self.events.put(('done',identity,'Completed',result))
            except Interrupted as exc:self.events.put(('done',identity,control.reason,str(exc)))
            except Exception as exc:self.events.put(('done',identity,'Failed',str(exc)))
        threading.Thread(target=work,name=f'kora-download-{identity}',daemon=False).start()
    def refresh(self):
        selected=self.tree.selection()
        for row in self.store.rows():
            identity,url,path,count,state,done,total,note=row[:8];latest=self.last_progress.get(identity,{})
            amount=f'{readable(done)} / {readable(total)}'
            values=(Path(path).name,state,amount,readable(latest['speed'])+'/s' if latest.get('speed') else '—',f"{latest['eta']:.0f}s" if latest.get('eta') is not None else '—')
            if self.tree.exists(str(identity)):self.tree.item(str(identity),values=values)
            else:self.tree.insert('', 'end',iid=str(identity),values=values)
        if selected and self.tree.exists(selected[0]):self.tree.selection_set(selected)
    def log(self,text):
        self.rea_log.configure(state='normal');self.rea_log.insert('end',text+'\n');self.rea_log.see('end');self.rea_log.configure(state='disabled')
    def investigate(self):
        if self.analysis:return
        target=self.target.get().strip();control=Control();self.analysis=control;self.rea_progress['value']=0
        out=ROOT/'evidence'/f'investigation-{time.time_ns()}'
        self.log('Starting read-only inspection…')
        def run():
            try:
                result=workflow(target,out,control,lambda value:self.events.put(('rea-step',value)))
                self.events.put(('rea-done',f"{result['status'].capitalize()}. Evidence saved to {out}"))
            except Exception as exc:self.events.put(('rea-done',str(exc)))
        threading.Thread(target=run,name='kora-rea',daemon=False).start()
    def stop_analysis(self):
        if self.analysis:self.analysis.stop('Investigation cancelled')
    def pump(self):
        try:
            while True:
                event=self.events.get_nowait();kind=event[0]
                if kind=='progress':
                    _,identity,value=event;self.last_progress[identity]=value
                    self.store.update(identity,bytes=value['bytes'],total=value['total'])
                    self.progress['value']=value['bytes']/value['total']*100 if value['total'] else 0
                    self.message.set(f"Downloading: {readable(value['bytes'])} at {readable(value['speed'])}/s")
                elif kind=='done':
                    _,identity,status,result=event;self.active=None
                    if status=='Completed':self.store.update(identity,status=status,bytes=result['bytes'],total=result['bytes'],note='SHA-256: '+result['sha256']);self.progress['value']=100
                    else:self.store.update(identity,status=status,note=str(result))
                    self.last_progress.pop(identity,None);self.message.set(status if status!='Failed' else 'Download failed: '+str(result))
                elif kind=='video-info':
                    _,url,info=event;self.video_inspection=None;self.video_source=url;self.video_info=info
                    if url==self.video_url.get().strip():self.suggest_video(title=info['title'])
                    choices={'Best available':{'mode':'best'}}
                    heights={int(f['height']) for f in info['formats'] if isinstance(f.get('height'),(int,float)) and f['height']>0}
                    for height in (2160,1440,1080,720,480,360):
                        if any(h<=height for h in heights):choices[f'Up to {height}p']={'mode':'best','height':height}
                    import re
                    for item in info['formats'][:100]:
                        if re.fullmatch(r'[A-Za-z0-9_.-]+',item['id']):
                            label=f"{item.get('height') or 'Auto'}p • {item.get('ext') or 'video'} • {item['id']}"+(' (audio merged)' if not item['audio'] else '')
                            choices[label]={'mode':'format','id':item['id']}
                    self.video_choices=choices;self.quality_box.configure(values=list(choices));self.video_quality.set('Best available')
                    preferred=self.settings['quality']
                    if preferred!='best' and f'Up to {preferred}p' in choices:self.video_quality.set(f'Up to {preferred}p')
                    self.video_status.set(f"{info['title']} — {len(info['formats'])} available formats")
                elif kind=='video-error':self.video_inspection=None;self.video_status.set(event[1])
                elif kind=='rea-step':self.rea_progress['value']=event[1]['step']-1;self.log(f"Step {event[1]['step']}/3: {event[1]['command']}")
                elif kind=='rea-done':self.analysis=None;self.rea_progress['value']=3;self.log(event[1])
                else:self.feature_event(event)
        except queue.Empty:pass
        self.refresh()
        if self.closing and not self.active and not self.analysis and not self.video_inspection and not self.batch_control and not self.maintenance:self.store.close();self.root.destroy();return
        if not self.closing and not self.active and not self.maintenance and self.auto_start:
            row=next((r for r in self.store.rows() if r[4]=='Queued'),None)
            if row:self.start_job(row)
        self.root.after(150,self.pump)
    def close(self):
        self.closing=True;self.message.set('Saving progress and stopping active work…')
        if self.active:self.active[1].stop('Paused')
        self.stop_analysis()
        self.stop_video_inspection()
        if self.batch_control:self.batch_control.stop('Batch stopped')
        try:preferences.save({**self.settings,'connections':self.connections.get()},self.settings_path)
        except (OSError,ValueError,tk.TclError):pass

def launch():
    data=preferences.data_dir();data.mkdir(parents=True,exist_ok=True);guard=data/'app-lock';guard.mkdir(exist_ok=True)
    with job_lock(guard):
        root=tk.Tk();App(root);root.mainloop()

if __name__=='__main__':launch()
