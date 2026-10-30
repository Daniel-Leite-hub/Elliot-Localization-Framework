"""Interface Windows em português. Executável Studio, separado do aplicador."""
import argparse
import json
import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox, simpledialog
from core import Store, VERSION, atomic_write, validate
from provider import Provider, TranslationJob
from locres import import_locres, generate_locres


def home():
    return Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent.parent


class Studio(tk.Tk):
    def __init__(self, project=None):
        super().__init__()
        self.title(f'Estúdio de tradução PT-BR — {VERSION}')
        self.geometry('1320x880')
        self.minsize(1050, 720)
        self.store, self.current, self.job, self.thread = None, None, None, None
        self.messages = queue.Queue()
        self.page = 0
        self.page_size = 200
        self.dirty = False
        self.loading = False
        self.worker_kind = None
        self.key = tk.StringVar()
        self.search = tk.StringVar()
        self.filter_state = tk.StringVar(value='Todos')
        self.filter_resource = tk.StringVar(value='Todos')
        self.filter_category = tk.StringVar(value='Todos')
        self.plan = tk.StringVar(value='Free')
        self.before = tk.IntVar(value=2)
        self.after_count = tk.IntVar(value=0)
        self.glossary = tk.StringVar()
        self.glossary_revision = tk.StringVar()
        self.formality = tk.StringVar(value='default')
        self.cap = tk.StringVar(value='')
        self.status = tk.StringVar(value='Abra ou crie um projeto. A chave DeepL fica somente na memória.')
        self.progress_text = tk.StringVar(value='Tradução: aguardando início.')
        self.progress_value = tk.DoubleVar(value=0)
        self.identity = tk.StringVar(value=f'Studio {VERSION} | executável: {sys.executable} | nenhum projeto aberto')
        self.make_ui()
        self.protocol('WM_DELETE_WINDOW', self.quit_safe)
        self.after_poll()
        if project:
            self.open_project(project)

    def make_ui(self):
        style = ttk.Style(self)
        style.theme_use('vista' if 'vista' in style.theme_names() else 'clam')
        style.configure('Treeview', rowheight=26)
        style.configure('Title.TLabel', font=('Segoe UI', 14, 'bold'))
        top = ttk.Frame(self, padding=(14, 10))
        top.pack(fill='x')
        ttk.Label(top, text='Estúdio de tradução • Português brasileiro', style='Title.TLabel').pack(anchor='w')
        ttk.Label(top, textvariable=self.identity, wraplength=1280).pack(anchor='w', pady=(4, 0))
        menu = tk.Menu(self)
        self.config(menu=menu)
        project = tk.Menu(menu, tearoff=False)
        menu.add_cascade(label='Projeto', menu=project)
        for label, command in [('Novo…', self.new_project), ('Abrir…', self.choose_project), ('Importar catálogo JSON…', self.import_catalog),
                               ('Importar LocRes solto…', self.import_resource), ('Importar rascunhos…', self.import_reviews),
                               ('Exportar rascunhos…', self.export_reviews), ('Backup consistente…', self.backup),
                               ('Investigar pasta do jogo…', self.investigate), ('Relatório de cobertura…', self.report)]:
            project.add_command(label=label, command=lambda c=command: self.guard(c))
        generation = tk.Menu(menu, tearoff=False)
        menu.add_cascade(label='Exportar / Gerar', menu=generation)
        generation.add_command(label='Catálogo editorial (aprovada → automática → original)…', command=lambda: self.guard(lambda: self.export(False)))
        generation.add_command(label='Catálogo editorial (somente aprovadas)…', command=lambda: self.guard(lambda: self.export(True)))
        generation.add_command(label='Gerar LocRes soltos…', command=lambda: self.guard(self.generate))
        sharing = tk.Menu(menu, tearoff=False)
        menu.add_cascade(label='Compartilhar', menu=sharing)
        sharing.add_command(label='ZIP para copiar na pasta do jogo…', command=lambda: self.guard(lambda: self.share('manual')))
        sharing.add_command(label='Instalador EXE com restauração…', command=lambda: self.guard(lambda: self.share('installer')))
        sharing.add_separator()
        sharing.add_command(label='Sobre instalação, backup e fontes', command=self.sharing_help)
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill='both', expand=True, padx=12)
        self.catalog_tab = ttk.Frame(self.notebook, padding=8)
        self.settings_tab = ttk.Frame(self.notebook, padding=12)
        self.requests_tab = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(self.catalog_tab, text='Catálogo e revisão')
        self.notebook.add(self.settings_tab, text='DeepL e contexto')
        self.notebook.add(self.requests_tab, text='Requisições e retomada')
        filters = ttk.Frame(self.catalog_tab)
        filters.pack(fill='x', pady=(0, 8))
        ttk.Label(filters, text='Buscar').pack(side='left')
        entry = ttk.Entry(filters, textvariable=self.search, width=30)
        entry.pack(side='left', padx=6)
        entry.bind('<KeyRelease>', lambda e: self.reset_page())
        for label, variable, values in [('Estado', self.filter_state, ['Todos','Pendente','Automática','Aprovada','Origem alterada','Excluída']),
                                         ('Recurso', self.filter_resource, ['Todos']), ('Categoria', self.filter_category, ['Todos'])]:
            ttk.Label(filters, text=label).pack(side='left', padx=(8, 2))
            cb = ttk.Combobox(filters, textvariable=variable, values=values, state='readonly', width=19)
            cb.pack(side='left')
            cb.bind('<<ComboboxSelected>>', lambda e: self.reset_page())
            if label == 'Recurso': self.resources_cb = cb
            if label == 'Categoria': self.categories_cb = cb
        ttk.Button(filters, text='Atualizar', command=self.refresh).pack(side='left', padx=8)
        pages=ttk.Frame(self.catalog_tab);pages.pack(fill='x',pady=(0,6))
        ttk.Button(pages,text='Página anterior',command=lambda:self.change_page(-1)).pack(side='left')
        ttk.Button(pages,text='Próxima página',command=lambda:self.change_page(1)).pack(side='left',padx=6)
        self.operation_progress=ttk.Progressbar(pages,mode='indeterminate',length=220);self.operation_progress.pack(side='right')
        split = ttk.Panedwindow(self.catalog_tab, orient='horizontal')
        split.pack(fill='both', expand=True)
        left, right = ttk.Frame(split), ttk.Frame(split)
        split.add(left, weight=2)
        split.add(right, weight=3)
        self.tree = ttk.Treeview(left, columns=('id','state','category'), show='headings', selectmode='browse')
        for name, label, width in [('id','ID / chave',220), ('state','Estado',115), ('category','Categoria',100)]:
            self.tree.heading(name,text=label)
            self.tree.column(name,width=width)
        ys = ttk.Scrollbar(left, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=ys.set)
        ys.pack(side='right', fill='y')
        self.tree.pack(fill='both', expand=True)
        self.tree.bind('<<TreeviewSelect>>', self.on_select)
        self.count = tk.StringVar(value='0 entradas')
        ttk.Label(left, textvariable=self.count, wraplength=480).pack(fill='x', pady=5)
        self.detail = tk.StringVar(value='Selecione uma entrada.')
        ttk.Label(right,textvariable=self.detail,wraplength=720).pack(fill='x')
        self.original = self.text_box(right, 'Original preservado', 5, readonly=True)
        self.machine = self.text_box(right, 'Tradução automática validada', 4, readonly=True)
        self.draft = self.text_box(right, 'Rascunho de revisão — inclusão opcional em Compartilhar', 6)
        self.draft.bind('<<Modified>>', self.modified)
        self.approved = self.text_box(right, 'Revisão aprovada', 4, readonly=True)
        actions = ttk.Frame(right)
        actions.pack(fill='x', pady=6)
        for label, command in [('Salvar',self.save), ('Aprovar',self.approve), ('Revogar',self.revoke),
                               ('Usar automática',self.use_machine), ('Histórico',self.show_history), ('Auxiliares',self.show_auxiliary), ('Classificar',self.classify)]:
            ttk.Button(actions,text=label,command=lambda c=command:self.guard(c)).pack(side='left',padx=2)
        actions2 = ttk.Frame(right)
        actions2.pack(fill='x')
        for label,command in [('Prévia DeepL',self.preview), ('Traduzir atual',lambda:self.translate(True)),
                              ('Traduzir todos os pendentes',lambda:self.translate(False)), ('Pausar',self.pause)]:
            ttk.Button(actions2,text=label,command=lambda c=command:self.guard(c)).pack(side='left',padx=2)
        self.alerts = tk.StringVar(value='')
        ttk.Label(right,textvariable=self.alerts,wraplength=720,foreground='#8b3e16').pack(fill='x',pady=6)
        self.make_settings()
        self.requests_tree = ttk.Treeview(self.requests_tab, columns=('request','entry','state','error','seconds'), show='headings')
        for name,label,width in [('request','Requisição',85),('entry','ID',180),('state','Estado',140),('error','Erro',620),('seconds','Rede (s)',80)]:
            self.requests_tree.heading(name,text=label); self.requests_tree.column(name,width=width)
        self.requests_tree.pack(fill='both',expand=True)
        actions3 = ttk.Frame(self.requests_tab)
        actions3.pack(fill='x',pady=8)
        ttk.Button(actions3,text='Atualizar',command=self.refresh_requests).pack(side='left')
        ttk.Button(actions3,text='Ver resposta bruta / requisição',command=lambda:self.guard(self.raw_request)).pack(side='left',padx=8)
        ttk.Button(actions3,text='Autorizar tentativa posterior',command=lambda:self.guard(self.retry_request)).pack(side='left')
        ttk.Label(self.requests_tab,text='Incerta: pode ter sido cobrada. Recusada: resposta recebida inválida, preservada fora do cache.\nA autorização libera a operação; use “Traduzir” para executar uma nova tentativa.').pack(anchor='w')
        ttk.Label(self,textvariable=self.progress_text,padding=(14,2)).pack(fill='x')
        ttk.Progressbar(self,variable=self.progress_value,maximum=100).pack(fill='x',padx=14,pady=2)
        ttk.Label(self,textvariable=self.status,wraplength=1280,padding=(14,8)).pack(fill='x')

    def text_box(self, parent, label, height, readonly=False):
        ttk.Label(parent,text=label).pack(anchor='w',pady=(7,2))
        text = tk.Text(parent,height=height,wrap='word',font=('Segoe UI',10),undo=not readonly)
        text.pack(fill='both',expand=True)
        if readonly: text.configure(state='disabled',background='#f1f3f5')
        return text

    def make_settings(self):
        frame = self.settings_tab
        ttk.Label(frame,text='DeepL API — chave somente em memória. Não use a senha da conta.',style='Title.TLabel').grid(row=0,column=0,columnspan=4,sticky='w',pady=(0,12))
        fields = [('Chave API',self.key), ('Plano',self.plan), ('Glossário DeepL (ID opcional)',self.glossary),
                  ('Revisão do glossário (altere após editar o glossário)',self.glossary_revision), ('Formalidade',self.formality),
                  ('Teto de caracteres por execução (vazio = sem teto adicional)',self.cap)]
        for i,(label,var) in enumerate(fields,1):
            ttk.Label(frame,text=label).grid(row=i,column=0,sticky='w',pady=5)
            if var is self.plan or var is self.formality:
                values = ['Free','Pro'] if var is self.plan else ['default','prefer_less','prefer_more']
                widget = ttk.Combobox(frame,textvariable=var,values=values,state='readonly',width=45)
            else:
                widget = ttk.Entry(frame,textvariable=var,width=65,show='•' if var is self.key else '')
            widget.grid(row=i,column=1,columnspan=3,sticky='ew',padx=10)
        ttk.Button(frame,text='Consultar cota',command=lambda:self.guard(self.usage)).grid(row=7,column=1,sticky='w',pady=10)
        ttk.Label(frame,text='Vizinhos anteriores (0–10)').grid(row=8,column=0,sticky='w')
        ttk.Spinbox(frame,from_=0,to=10,textvariable=self.before,width=5).grid(row=8,column=1,sticky='w')
        ttk.Label(frame,text='Posteriores (0 = somente anteriores)').grid(row=9,column=0,sticky='w',pady=8)
        ttk.Spinbox(frame,from_=0,to=10,textvariable=self.after_count,width=5).grid(row=9,column=1,sticky='w')
        ttk.Label(frame,text='Contexto geral verificado — fatos, personagens e terminologia').grid(row=10,column=0,columnspan=4,sticky='w',pady=(12,3))
        self.general = tk.Text(frame,height=9,wrap='word',font=('Segoe UI',11))
        self.general.grid(row=11,column=0,columnspan=4,sticky='nsew')
        ttk.Button(frame,text='Salvar configurações (sem a chave)',command=lambda:self.guard(self.save_settings)).grid(row=12,column=0,sticky='w',pady=10)
        ttk.Label(frame,text='O contexto só usa sequência e procedência explícitas no catálogo. IDs próximos não provam continuidade.\nQuebras de linha e comandos são protegidos. Cada alvo é enviado separadamente.\nO teto acima é de caracteres estimados, não um teto monetário. Configure limite financeiro na conta DeepL.\nAlterações de contexto não retraduzem entradas concluídas. Glossários remotos são conferidos antes do envio; registre sua revisão ao alterá-los.').grid(row=13,column=0,columnspan=4,sticky='w')
        frame.columnconfigure(1,weight=1)
        frame.rowconfigure(11,weight=1)

    def guard(self, fn):
        try:
            if self.thread and self.thread.is_alive() and fn != self.pause:
                raise ValueError('Operação em andamento. Pause e aguarde o término antes de editar o projeto.')
            return fn()
        except Exception as exc:
            messagebox.showerror('Operação não concluída',str(exc),parent=self)

    def require(self):
        if not self.store: raise ValueError('Abra ou crie um projeto primeiro.')

    def new_project(self):
        path = filedialog.asksaveasfilename(title='Novo projeto persistente',defaultextension='.sqlite',filetypes=[('Projeto SQLite','*.sqlite')],initialdir=home()/'projetos')
        if path:
            if Path(path).exists(): raise ValueError('Para preservar o projeto existente, use Abrir ou escolha um nome novo.')
            self.open_project(path)

    def choose_project(self):
        path = filedialog.askopenfilename(title='Abrir projeto',filetypes=[('Projeto SQLite','*.sqlite')],initialdir=home()/'projetos')
        if path: self.open_project(path)

    def open_project(self,path):
        if self.thread and self.thread.is_alive(): raise ValueError('Aguarde a operação atual.')
        if self.dirty and self.current: self.save()
        candidate = Store(path)
        if self.store: self.store.close()
        self.store, self.current = candidate,None
        self.identity.set(f'Studio {VERSION} | executável: {sys.executable} | projeto: {self.store.path}')
        for var,key,default in [(self.plan,'plan','Free'),(self.before,'before',2),(self.after_count,'after',0),(self.glossary,'glossary_id',''),(self.glossary_revision,'glossary_revision',''),(self.formality,'formality','default')]:
            var.set(self.store.setting(key,default))
        self.general.delete('1.0','end'); self.general.insert('1.0',self.store.setting('general_context',''))
        self.filter_resource.set('Todos'); self.filter_category.set('Todos'); self.filter_state.set('Todos')
        for widget in [self.original,self.machine,self.draft,self.approved]: self.set_text(widget,'')
        self.dirty=False
        self.refresh(); self.refresh_requests()
        self.status.set('Projeto aberto. Revisões e traduções persistem; nenhuma chamada automática foi iniciada.')

    def save_settings(self):
        self.require()
        if not 0<=self.before.get()<=10 or not 0<=self.after_count.get()<=10: raise ValueError('Contexto deve estar entre 0 e 10 falas.')
        for key,value in [('plan',self.plan.get()),('before',self.before.get()),('after',self.after_count.get()),('glossary_id',self.glossary.get().strip()),
                          ('glossary_revision',self.glossary_revision.get()),('formality',self.formality.get()),('general_context',self.general.get('1.0','end-1c'))]:
            self.store.set_setting(key,value)
        self.status.set('Configurações salvas. A chave não foi armazenada.')

    @staticmethod
    def state(row):
        if row['kind']!='traduzivel': return 'Excluída'
        if row['stale']: return 'Origem alterada'
        if row['approved'] is not None: return 'Aprovada'
        if row['machine'] is not None: return 'Automática'
        return 'Pendente'

    def reset_page(self):
        self.page=0;self.refresh()

    def change_page(self,delta):
        self.page=max(0,self.page+delta);self.refresh()

    def refresh(self):
        if not self.store:return
        clauses=['active=1'];params=[]
        for column,value in [('resource',self.filter_resource.get()),('category',self.filter_category.get())]:
            if value!='Todos':clauses.append(column+'=?');params.append(value)
        states={'Excluída':"kind<>'traduzivel'",'Origem alterada':"kind='traduzivel' AND stale=1",'Aprovada':"kind='traduzivel' AND stale=0 AND approved IS NOT NULL",'Automática':"kind='traduzivel' AND stale=0 AND approved IS NULL AND machine IS NOT NULL",'Pendente':"kind='traduzivel' AND stale=0 AND approved IS NULL AND machine IS NULL"}
        if self.filter_state.get() in states:clauses.append(states[self.filter_state.get()])
        search=self.search.get().strip()
        if search:
            clauses.append("(original LIKE ? OR meta LIKE ? OR COALESCE(machine,'') LIKE ? OR COALESCE(draft,'') LIKE ? OR COALESCE(approved,'') LIKE ? OR resource LIKE ?)")
            params.extend(['%'+search+'%']*6)
        where=' AND '.join(clauses)
        with self.store.lock:
            db=self.store.db
            matched=db.execute('SELECT count(*) FROM entries WHERE '+where,params).fetchone()[0]
            self.page=min(self.page,max(0,(matched-1)//self.page_size))
            rows=[dict(r) for r in db.execute('SELECT * FROM entries WHERE '+where+' ORDER BY resource,position,id LIMIT ? OFFSET ?',params+[self.page_size,self.page*self.page_size])]
            resources=[r[0] for r in db.execute('SELECT DISTINCT resource FROM entries WHERE active=1 ORDER BY resource')]
            categories=[r[0] for r in db.execute('SELECT DISTINCT category FROM entries WHERE active=1 ORDER BY category')]
            total=db.execute('SELECT count(*) FROM entries WHERE active=1').fetchone()[0]
            source=self.store.setting('source_language',None)
            eligible=db.execute("SELECT count(*) FROM entries WHERE active=1 AND kind='traduzivel'"+(" AND language=?" if source else ''),[source] if source else []).fetchone()[0]
        self.resources_cb['values']=['Todos']+resources
        self.categories_cb['values']=['Todos']+categories
        self.tree.delete(*self.tree.get_children())
        for row in rows:self.tree.insert('','end',iid=row['id'],values=(json.loads(row['meta'])['external_id'],self.state(row),row['category']))
        self.count.set(f'Página {self.page+1} | {len(rows)} exibidas / {matched} no filtro / {total} no catálogo / {eligible} elegíveis.\nFonte: {source or "por entrada"}. Operações globais processam o catálogo completo.')
        if self.current and self.tree.exists(self.current):self.tree.selection_set(self.current)

    def modified(self,event=None):
        if self.draft.edit_modified():
            if not self.loading: self.dirty=True
            self.draft.edit_modified(False)

    def set_text(self,widget,text):
        state=widget.cget('state'); widget.configure(state='normal')
        widget.delete('1.0','end'); widget.insert('1.0',text or '')
        widget.configure(state=state); widget.edit_modified(False)

    def on_select(self,event=None):
        selected=self.tree.selection()
        if not selected or selected[0]==self.current: return
        if self.thread and self.thread.is_alive(): return
        if self.current and self.dirty: self.guard(self.save)
        self.current=selected[0]; self.load_current()

    def load_current(self):
        if not self.current: return
        row=self.store.entry(self.current); meta=json.loads(row['meta'])
        self.detail.set(f'{meta["external_id"]} | {row["language"]} | {row["category"]}\n{row["resource"]}\nFalante: {meta.get("speaker","não identificado")} | {row["exclusion"]}')
        self.loading=True
        for widget,value in [(self.original,row['original']),(self.machine,row['machine']),(self.draft,row['draft'] if row['draft'] is not None else (row['machine'] or row['original'])),(self.approved,row['approved'])]: self.set_text(widget,value)
        self.loading=False; self.dirty=False
        errors,warnings=validate(row['original'],self.draft.get('1.0','end-1c'),meta.get('restrictions'))
        if row['stale']: errors.insert(0,'Origem/contexto alterado; aprovação anterior exige revisão.')
        self.alerts.set('\n'.join(errors+warnings))

    def selected(self):
        self.require()
        if not self.current: raise ValueError('Selecione uma entrada.')
        return self.current

    def save(self):
        self.store.edit(self.selected(),self.draft.get('1.0','end-1c'))
        self.dirty=False; self.status.set('Rascunho salvo. Compartilhar permite incluí-lo explicitamente; nenhuma aprovação criada.')

    def approve(self):
        warnings=self.store.edit(self.selected(),self.draft.get('1.0','end-1c'),approve=True)
        self.dirty=False; self.refresh(); self.load_current(); self.status.set('Revisão aprovada. '+ ' '.join(warnings))

    def revoke(self):
        self.store.revoke(self.selected()); self.refresh(); self.load_current()

    def use_machine(self):
        row=self.store.entry(self.selected())
        if row['machine'] is None: raise ValueError('Não há automática válida.')
        self.set_text(self.draft,row['machine']); self.dirty=True

    def dialog_text(self,title,text):
        window=tk.Toplevel(self); window.title(title); window.geometry('960x620')
        widget=tk.Text(window,wrap='word',font=('Consolas',10)); widget.pack(fill='both',expand=True,padx=10,pady=10)
        widget.insert('1.0',text); widget.configure(state='disabled')

    def show_history(self):
        self.dialog_text('Histórico persistente',json.dumps(self.store.history(self.selected()),ensure_ascii=False,indent=2))

    def show_auxiliary(self):
        row=self.store.entry(self.selected());meta=json.loads(row['meta'])
        auxiliary=meta.get('auxiliary',{})
        self.dialog_text('Idiomas auxiliares alinhados por ID',json.dumps(dict(source_language=row['language'],original=row['original'],
            auxiliary=auxiliary,warning='Auxiliares esclarecem a revisão; não substituem a fonte principal nem entram automaticamente no envio DeepL.'),ensure_ascii=False,indent=2))

    def classify(self):
        entry_id=self.selected()
        choice=simpledialog.askstring('Classificação','Informe: traduzivel, tecnica ou vazia',initialvalue=self.store.entry(entry_id)['kind'],parent=self)
        if choice is None: return
        reason='' if choice=='traduzivel' else simpledialog.askstring('Motivo','Motivo explícito para excluir da fila:',parent=self)
        if reason is None: return
        self.store.classify_entry(entry_id,choice,reason); self.refresh(); self.load_current()

    def preview(self):
        self.save_settings()
        row=self.store.entry(self.selected()); payload,markers,key,evidence=self.store.payload(row)
        self.dialog_text('Prévia exata do envio (sem credencial)',json.dumps(dict(payload=payload,markers=markers,cache_key=key,evidence=evidence),ensure_ascii=False,indent=2))

    def background(self, fn, kind):
        self.worker_kind=kind
        self.operation_progress.start(15)
        def worker():
            try: fn()
            except Exception as exc: self.messages.put('Operação '+kind+' falhou: '+type(exc).__name__+'. '+str(exc) if kind in ('investigação','geração','importação','compartilhamento') else 'Consulta/preparação DeepL falhou; nenhum resultado foi presumido.')
        self.thread=threading.Thread(target=worker,daemon=False); self.thread.start()

    def usage(self):
        self.require(); self.save_settings()
        key,plan=self.key.get(),self.plan.get()
        def run():
            provider=Provider(key,plan)
            try:
                result=provider.usage(); self.messages.put(f'Cota DeepL: {result["used"]} usados / {result["limit"]}; disponíveis {result["remaining"]}.')
            finally: provider.close()
        self.background(run,'cota'); self.status.set('Consultando cota; nenhuma tradução enviada.')

    def translate(self,current=False):
        self.require(); self.save_settings()
        if self.dirty and self.current: self.save()
        only=self.selected() if current else None
        cap=None
        if self.cap.get().strip():
            cap=int(self.cap.get())
            if cap<0: raise ValueError('Teto deve ser não negativo.')
        key,plan=self.key.get(),self.plan.get()
        self.preparation_stop=threading.Event()
        def prepare_queue():
            worker=self.store.worker_connection()
            provider=None
            try:
                self.messages.put('Preparando catálogo completo e deduplicação…')
                estimate=worker.estimate(only,self.preparation_stop)
                if self.preparation_stop.is_set():
                    self.messages.put('Preparação pausada; nenhum envio realizado.'); return
                if not estimate['entries']:
                    self.messages.put('Sem pendentes elegíveis no idioma fonte. Referências japonesas e incertas/recusadas permanecem excluídas.');return
                provider=Provider(key,plan)
                glossary_error=None
                if worker.setting('glossary_id',''):
                    for language in {r['language'] for r,_ in estimate['groups'].values()}:
                        try:provider.check_glossary(worker.setting('glossary_id'),language)
                        except ValueError as exc:glossary_error=str(exc);break
                try: available=provider.usage()['remaining']
                except Exception: available=None
                if self.preparation_stop.is_set():
                    provider.close();self.messages.put('Preparação pausada; nenhum envio realizado.');return
                eligible=[r for r in worker.rows() if worker.eligibility(r)]
                baseline=sum(bool((r['approved'] and not r['stale']) or (r['machine'] is not None and r['machine_hash']==r['source_hash'] and not r['stale'])) for r in eligible)
                self.messages.put(('prepared',dict(estimate=estimate,provider=provider,available=available,cap=cap,baseline=baseline,total=len(eligible),glossary_error=glossary_error,current=current)))
            except Exception as exc:
                if provider:provider.close()
                self.messages.put('Preparação falhou: '+type(exc).__name__+'. Nenhum envio realizado.')
            finally:worker.db.close()
        self.background(prepare_queue,'preparação')
        self.status.set('Preparando a fila fora da interface. Pausa disponível.')

    def confirm_queue(self,data):
        provider=data['provider'];estimate=data['estimate'];available=data['available'];cap=data['cap']
        if self.preparation_stop.is_set():provider.close();return
        self.thread=None
        self.operation_progress.stop()
        if data['glossary_error']:
            provider.close()
            if messagebox.askyesno('Glossário inválido',data['glossary_error']+'\nContinuar sem glossário? Não permite corrigir a configuração.',parent=self):
                self.glossary.set('');self.save_settings();self.translate(data['current'])
            return
        if not estimate['entries']:
            provider.close();self.status.set('Sem pendentes elegíveis; confira incertas/recusadas.');return
        quota=f'Cota disponível: {available} caracteres.' if available is not None else 'Cota desconhecida: confirmação explícita para execução possivelmente parcial.'
        if available is not None and estimate['characters']>available:quota+=' Cota insuficiente; execução parcial.'
        text=f'{estimate["entries"]} entradas; {estimate["unique"]} unidades únicas; {estimate["network"]} chamadas estimadas.\n{estimate["characters"]} caracteres estimados; {estimate["avoided"]} reutilizações.\n{quota}\nTeto: {cap if cap is not None else "não definido"}.\nAutorizar envio ao DeepL?'
        if not messagebox.askyesno('Autorizar tradução DeepL',text,parent=self):provider.close();return
        effective_cap=cap if available is None else available if cap is None else min(cap,available)
        self.job=TranslationJob(self.store,provider,estimate['groups'],notify=self.messages.put,char_cap=effective_cap,members=estimate['members'],progress=lambda d:self.messages.put(('progress',d)),baseline=data['baseline'],total=data['total'])
        def run_job():
            worker=self.store.worker_connection()
            self.job.store=worker
            try:self.job.run()
            finally:worker.db.close()
        self.background(run_job,'tradução');self.status.set('Enviando e aguardando o provedor; resultados salvos a cada resposta.')

    def pause(self):
        if hasattr(self,'preparation_stop'): self.preparation_stop.set()
        if self.job and self.thread and self.thread.is_alive():
            self.job.pause(); self.status.set('Pausa solicitada; aguardando a requisição em andamento para salvar seu resultado.')

    def after_poll(self):
        while not self.messages.empty():
            item=self.messages.get_nowait()
            if isinstance(item,tuple) and item[0]=='prepared':
                self.confirm_queue(item[1])
            elif isinstance(item,tuple) and item[0]=='generated':
                self.status.set(f'{len(item[1]["resources"])} LocRes soltos gerados e relidos; não instalados.')
            elif isinstance(item,tuple) and item[0]=='progress':
                data=item[1]; self.progress_value.set(data['percent'])
                self.progress_text.set(f'Tradução total: {data["completed"]:,}/{data["total"]:,} — {data["percent"]:.2f}% | Nesta execução: {data["session_completed"]:,}/{data["session_total"]:,} | Incertas/recusadas nesta execução: {data["unresolved"]:,}')
            else: self.status.set(item)
        if self.thread and not self.thread.is_alive():
            self.operation_progress.stop()
            self.thread=None; self.job=None; self.refresh(); self.refresh_requests()
            if self.current: self.load_current()
        self.after(200,self.after_poll)

    def refresh_requests(self):
        if not self.store: return
        self.requests_tree.delete(*self.requests_tree.get_children())
        with self.store.lock: rows=self.store.db.execute('SELECT * FROM requests ORDER BY id DESC').fetchall()
        for row in rows:
            self.requests_tree.insert('','end',iid=str(row['id']),values=(row['id'],row['entry_id'][:20],row['state'],row['error'] or '',f'{row["elapsed"]:.2f}' if row['elapsed'] is not None else ''))

    def request_id(self):
        self.require(); selected=self.requests_tree.selection()
        if not selected: raise ValueError('Selecione uma requisição.')
        return int(selected[0])

    def raw_request(self):
        rid=self.request_id()
        with self.store.lock: row=dict(self.store.db.execute('SELECT * FROM requests WHERE id=?',(rid,)).fetchone())
        self.dialog_text('Resposta bruta preservada',json.dumps(row,ensure_ascii=False,indent=2))

    def retry_request(self):
        rid=self.request_id()
        with self.store.lock: row=self.store.db.execute('SELECT state FROM requests WHERE id=?',(rid,)).fetchone()
        warning='Esta requisição pode já ter sido cobrada. ' if row['state']=='incerta' else 'A resposta anterior fica preservada. '
        if messagebox.askyesno('Autorizar tentativa posterior',warning+'Uma nova tentativa poderá consumir cota novamente. Autorizar este reenvio?',parent=self):
            self.store.retry(rid,allow_uncertain=True); self.refresh_requests(); self.status.set('Reenvio autorizado; use Traduzir para iniciar.')

    def import_catalog(self):
        self.require()
        path=filedialog.askopenfilename(title='Catálogo com IDs estáveis',filetypes=[('Catálogo JSON','*.json')])
        if path:
            def run():
                worker=self.store.worker_connection()
                try:self.messages.put(f'{worker.import_catalog(path)} entradas importadas.')
                finally:worker.db.close()
            self.background(run,'importação')

    def import_resource(self):
        self.require()
        path=filedialog.askopenfilename(title='LocRes solto já extraído',filetypes=[('LocRes Unreal','*.locres')])
        if not path: return
        lang=simpledialog.askstring('Idioma de origem','Código explícito do idioma deste recurso (EN, JA, FR…):',parent=self)
        if not lang: return
        if not lang.isalpha() or len(lang) not in [2,3]: raise ValueError('Código de origem inválido.')
        count,version=import_locres(self.store,path,lang); self.refresh()
        self.status.set(f'{count} entradas LocRes v{version}; reconstrução sem alterações byte a byte aprovada. Reinserção no jogo ainda não comprovada.')

    def import_reviews(self):
        self.require(); path=filedialog.askopenfilename(title='Rascunhos studio-reviews-v1',filetypes=[('Revisões JSON','*.json')])
        if path: self.status.set(f'{self.store.import_reviews(path)} rascunhos importados sem aprovação.'); self.refresh()

    def export_reviews(self):
        self.require(); path=filedialog.asksaveasfilename(title='Exportar revisões para intercâmbio',defaultextension='.json')
        if path: self.store.export_reviews(path); self.status.set('Rascunhos exportados com IDs e hashes de origem.')

    def export(self,approved_only=False):
        self.require()
        if self.dirty and self.current: self.save()
        path=filedialog.asksaveasfilename(title='Exportação editorial — não é patch do jogo',defaultextension='.json')
        if path: self.status.set(f'{self.store.export(path,approved_only)} entradas exportadas e relidas. Catálogo editorial; não aplicado ao jogo.')

    def generate(self):
        self.require()
        if self.dirty and self.current: self.save()
        path=filedialog.askdirectory(title='Pasta nova para LocRes gerados (recursos soltos)')
        if not path: return
        mode=messagebox.askyesnocancel('Prioridade','Gerar somente revisões aprovadas?\nSim: aprovadas → original. Não: aprovadas → automática → original.',parent=self)
        if mode is None: return
        def run():
            worker=self.store.worker_connection()
            try:self.messages.put(('generated',generate_locres(worker,path,mode)))
            finally:worker.db.close()
        self.background(run,'geração');self.status.set('Gerando e validando recursos fora da interface…')

    def backup(self):
        self.require()
        if self.dirty and self.current: self.save()
        path=filedialog.asksaveasfilename(title='Backup SQLite consistente (novo arquivo)',defaultextension='.sqlite')
        if path: self.store.backup(path); self.status.set('Backup consistente criado e verificado, incluindo dados do WAL.')

    def share(self,form):
        self.require()
        if self.thread and self.thread.is_alive():raise ValueError('Aguarde a operação atual.')
        if self.dirty and self.current:self.save()
        mode=messagebox.askyesnocancel('Textos para compartilhar','Incluir os rascunhos revisados atuais?\nSim: rascunho → aprovada → original.\nNão: somente aprovada → original.\nCampos técnicos, None e japonês residual são preservados. Nenhuma aprovação é criada.',parent=self)
        if mode is None:return
        if form=='manual':
            path=filedialog.asksaveasfilename(title='ZIP novo para copiar na pasta do jogo (~3,7 GB)',defaultextension='.zip',filetypes=[('ZIP','*.zip')])
        else:
            parent=filedialog.askdirectory(title='Pasta onde criar o instalador para compartilhar')
            if not parent:return
            import time
            path=str(Path(parent)/('Elliot-Instalador-PTBR-'+str(time.time_ns())))
        if not path:return
        self.preparation_stop=threading.Event()
        def run():
            from sharing import export_manual,export_installer
            worker=self.store.worker_connection()
            try:
                export=export_manual if form=='manual' else export_installer
                result=export(worker,path,'reviewed' if mode else 'approved',self.messages.put,self.preparation_stop)
                self.messages.put('Compartilhamento gerado e conferido: '+result+'. Guia de instalação e backup incluído.')
            finally:worker.db.close()
        self.background(run,'compartilhamento');self.status.set('Preparando distribuição fora da interface; Pausar cancela. Nenhuma alteração no jogo.')

    def sharing_help(self):
        messagebox.showinfo('Compartilhar tradução','ZIP para copiar: contém o PAK traduzido completo (~3,7 GB), guia curto e instruções de backup manual.\n\nInstalador EXE: gera uma pasta menor com EXE, dependências e dados de reinserção. Compartilhe a pasta inteira. Verifica a base, mantém backup e permite restaurar.\n\nAmbos substituem o idioma Espanhol. As fontes originais do jogo são mantidas; não há fontes PT-BR personalizadas preparadas.\n\nO carregamento no menu foi confirmado para a versão v2. Mudanças posteriores de texto e o restante do jogo precisam de teste.',parent=self)

    def investigate(self):
        self.require(); path=filedialog.askdirectory(title='Pasta original do jogo — somente leitura')
        if not path: return
        from investigate import inventory
        def run():
            worker=self.store.worker_connection()
            try:
                report=inventory(path,worker,self.messages.put)
                self.messages.put(f'Inventário concluído: {len(report["files"])} arquivos com hashes integrais. Extração de pacotes bloqueada.')
            finally:worker.db.close()
        self.background(run,'investigação')

    def report(self):
        self.require(); report=self.store.report()
        self.dialog_text('Cobertura, validações e pendências',json.dumps(report,ensure_ascii=False,indent=2))
        path=filedialog.asksaveasfilename(title='Salvar relatório (opcional)',defaultextension='.json')
        if path: atomic_write(path,json.dumps(report,ensure_ascii=False,indent=2).encode('utf-8'))

    def blocked(self):
        messagebox.showinfo('Geração Elliot bloqueada','A extração está documentada em relatorios/RELATORIO.md.\nO EXE reconstrói LocRes soltos; a montagem do patch ainda depende de validação específica da base.\nNão há patch Elliot validado nem teste de fontes/layout no jogo.',parent=self)

    def quit_safe(self):
        if self.thread and self.thread.is_alive():
            self.pause(); messagebox.showinfo('Aguarde o checkpoint','Aguarde a operação atual terminar e feche novamente. A resposta em andamento precisa ser salva.',parent=self); return
        if self.dirty and self.current: self.guard(self.save)
        self.key.set('')
        if self.store: self.store.close()
        self.destroy()


def main():
    parser=argparse.ArgumentParser(description='Studio de tradução Windows PT-BR')
    parser.add_argument('--project')
    parser.add_argument('--self-test',action='store_true')
    parser.add_argument('--smoke-ui',action='store_true')
    parser.add_argument('--result')
    parser.add_argument('--share-format',choices=['manual','installer'])
    parser.add_argument('--share-output')
    parser.add_argument('--share-mode',choices=['reviewed','approved'],default='reviewed')
    args=parser.parse_args()
    if args.share_format:
        if not args.project or not args.share_output:parser.error('Compartilhar exige --project e --share-output.')
        from sharing import export_manual,export_installer
        store=Store(args.project)
        try:
            result=(export_manual if args.share_format=='manual' else export_installer)(store,args.share_output,args.share_mode)
            if args.result:atomic_write(args.result,json.dumps(dict(shared=True,form=args.share_format,path=result)).encode())
        finally:store.close()
        return
    if args.self_test:
        from selfcheck import run
        result=run()
        data=json.dumps(result,ensure_ascii=False,indent=2).encode('utf-8')
        if args.result: atomic_write(args.result,data)
        else: print(data.decode('utf-8'))
        return
    default=home()/'projetos'/'Elliot.sqlite'
    if not default.exists(): default=home().parent/'projetos'/'Elliot.sqlite'
    app=Studio(args.project or (default if default.exists() else None))
    if args.smoke_ui:
        def smoke():
            app.update_idletasks()
            menu=app.nametowidget(app.cget('menu'))
            result=dict(version=VERSION, widgets_created=True, project_open=bool(app.store), visual_validation=False,menu_labels=[menu.entrycget(i,'label') for i in range(menu.index('end')+1) if menu.type(i)=='cascade'])
            if args.result: atomic_write(args.result,json.dumps(result).encode())
            app.quit_safe()
        app.after(500,smoke)
    app.mainloop()


if __name__=='__main__': main()
