"""Small desktop controller for the local connector. Does not load Unity."""
from __future__ import annotations
import json
import secrets
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE = Path(__file__).resolve().parent
RUNTIME = BASE / 'runtime'
RUNTIME.mkdir(exist_ok=True)
PAIR = RUNTIME / 'pairing.json'
if not PAIR.exists():
    PAIR.write_text(json.dumps({'token': secrets.token_urlsafe(24)}), encoding='utf-8')
TOKEN = json.loads(PAIR.read_text(encoding='utf-8'))['token']
URL = 'http://127.0.0.1:43127'
(BASE / 'connection.txt').write_text(f'URL: {URL}\nMã kết nối: {TOKEN}\n', encoding='utf-8')

class App:
    def __init__(self):
        self.window = tk.Tk()
        self.window.title('Game UI Reskin · Local')
        self.window.geometry('800x500')
        self.window.minsize(640, 400)
        self.process = None
        self.starting = False
        self.generation = 0
        self.log = None
        saved_path = RUNTIME / 'settings.json'
        saved = json.loads(saved_path.read_text(encoding='utf-8')) if saved_path.exists() else {}
        self.project = tk.StringVar(value=saved.get('project', ''))
        self.output = tk.StringVar(value=saved.get('output', str(RUNTIME / 'ReskinOutput')))
        self.status = tk.StringVar(value='Chưa khởi động')
        container = ttk.Frame(self.window, padding=20)
        container.pack(fill='both', expand=True)
        ttk.Label(container, text='Game UI Reskin', font=('Segoe UI', 17, 'bold')).pack(anchor='w')
        ttk.Label(container, text='Đọc Unity · Nhập Figma · Xuất reskin ra folder ngoài project').pack(anchor='w', pady=(0, 15))
        self.folder_row(container, 'Project Unity', self.project)
        ttk.Label(container, text='Nguồn UI: tự tìm trong Addressables và các prefab UI liên quan').pack(anchor='w', pady=(0, 8))
        self.folder_row(container, 'Folder xuất reskin', self.output)
        controls = ttk.Frame(container)
        controls.pack(fill='x', pady=10)
        ttk.Button(controls, text='Khởi động / Lưu nguồn', command=self.start).pack(side='left')
        ttk.Button(controls, text='Khởi động lại local', command=self.restart).pack(side='left', padx=8)
        ttk.Button(controls, text='Copy mã kết nối', command=self.copy_token).pack(side='left')
        ttk.Button(controls, text='Dừng local', command=self.stop).pack(side='right')
        setup = ttk.Frame(container)
        setup.pack(fill='x')
        ttk.Button(setup, text='Mở folder plugin để import vào Figma', command=self.open_plugin).pack(side='left')
        ttk.Label(setup, text='Dùng sẵn manifest.json — không cần New plugin').pack(side='left', padx=8)
        ttk.Label(container, textvariable=self.status, foreground='#65418d', wraplength=690).pack(anchor='w', pady=8)
        ttk.Label(container, text='Sau khi khởi động: mở plugin Figma → dán mã kết nối → Kết nối.\n'
                  'Đổi dữ liệu Unity: Refresh nguồn Unity trong plugin. Đổi code local: Khởi động lại local.\n'
                  'Không sửa code, prefab, ảnh hoặc .meta trong game. Đóng cửa sổ này sẽ dừng local.',
                  wraplength=690).pack(anchor='w')
        self.window.protocol('WM_DELETE_WINDOW', self.close)

    def open_plugin(self):
        import os
        os.startfile(str(BASE / 'plugin'))

    def folder_row(self, parent, label, value):
        ttk.Label(parent, text=label).pack(anchor='w')
        row = ttk.Frame(parent)
        row.pack(fill='x', pady=(0, 8))
        ttk.Entry(row, textvariable=value).pack(side='left', fill='x', expand=True)
        def choose():
            selected = filedialog.askdirectory(parent=self.window, title=label)
            if selected:
                value.set(selected)
        ttk.Button(row, text='Chọn folder…', command=choose).pack(side='right', padx=(8, 0))

    def request(self, route, body=None):
        headers = {'X-Reskin-Token': TOKEN, 'Content-Type': 'application/json'}
        request = Request(URL + route, data=json.dumps(body).encode() if body is not None else None, headers=headers)
        try:
            with urlopen(request, timeout=8) as response:
                return json.loads(response.read())
        except HTTPError as error:
            try:
                text = json.loads(error.read()).get('error', str(error))
            except Exception:
                text = str(error)
            raise RuntimeError(text) from error

    def start(self):
        if self.starting:
            return
        try:
            try:
                self.request('/api/status')
                self.configure()
                return
            except (URLError, ConnectionError, TimeoutError, OSError):
                pass
            if not Path(self.project.get()).joinpath('Assets').is_dir():
                raise ValueError('Chọn thư mục project Unity trước.')
            self.log = (RUNTIME / 'local.log').open('a', encoding='utf-8')
            args = [sys.executable, '-X', 'utf8', str(BASE / 'server.py'), '--project', self.project.get(),
                    '--output', self.output.get()]
            self.process = subprocess.Popen(args, cwd=str(BASE), stdout=self.log, stderr=self.log,
                                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            self.starting = True
            self.generation += 1
            generation = self.generation
            self.status.set('Đang khởi động…')
            self.window.after(500, lambda: self.poll(0, generation))
        except Exception as error:
            self.starting = False
            self.status.set(str(error))
            messagebox.showerror('Không khởi động được', str(error), parent=self.window)

    def poll(self, attempt, generation=None):
        if generation is not None and generation != self.generation:
            return
        if self.process and self.process.poll() is not None:
            self.starting = False
            self.status.set('Local không khởi động được. Xem runtime/local.log.')
            return
        try:
            self.request('/api/status')
            self.configure()
            self.starting = False
        except Exception as error:
            if attempt < 30:
                self.window.after(500, lambda: self.poll(attempt + 1, generation))
            else:
                self.starting = False
                self.status.set('Không kết nối được local: ' + str(error))

    def restart(self):
        if self.starting:
            return
        if not self.process or self.process.poll() is not None:
            try:
                self.request('/api/status')
            except (URLError, ConnectionError, TimeoutError, OSError):
                pass
            except Exception as error:
                self.status.set('Không kiểm tra được local: ' + str(error))
                return
            else:
                self.status.set('Local đang chạy từ cửa sổ khác. '
                                'Bấm Khởi động lại local tại cửa sổ đã bật tiến trình đó.')
                return
        try:
            self.stop()
            self.start()
        except Exception as error:
            self.status.set('Không khởi động lại được local: ' + str(error))

    def configure(self):
        result = self.request('/api/config', {'project': self.project.get(), 'output': self.output.get()})
        self.status.set('Đang chạy tại ' + URL + '\nFolder xuất: ' + result['output'])

    def copy_token(self):
        self.window.clipboard_clear()
        self.window.clipboard_append(TOKEN)
        self.window.update()
        self.status.set('Đã copy mã. Dán vào field Mã kết nối trong plugin Figma.')

    def stop(self):
        self.generation += 1
        self.starting = False
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)
        if self.log:
            self.log.close()
            self.log = None
        self.status.set('Local đã dừng.')

    def close(self):
        self.stop()
        self.window.destroy()

if __name__ == '__main__':
    App().window.mainloop()
