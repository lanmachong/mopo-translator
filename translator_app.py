import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import polib
from googletrans import Translator
import os
import threading
import json
import time
import ssl
import urllib3
from requests.exceptions import SSLError, ConnectionError

class TranslatorApp:
    def __init__(self, root):
        """初始化翻译器应用程序"""
        self.root = root
        self.root.title("PO/MO文件翻译器")
        self.root.geometry("1200x800")
        
        # 初始化翻译器
        self.init_translator()
        
        # 初始化变量
        self.current_file = None
        self.translation_data = []
        self.progress_var = tk.DoubleVar()
        self.time_label = None
        self.translation_start_time = None
        self.processed_entries = 0
        self.total_entries = 0
        self.last_update_time = None
        self.speed_samples = []  # 用于存储速度样本
        self.initial_estimate = None  # 初始预估总时间
        
        # 创建主框架
        self.create_main_frame()
        
    def init_translator(self):
        """初始化翻译器，处理SSL问题"""
        try:
            # 禁用SSL验证警告
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            
            # 创建自定义SSL上下文
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            # 初始化翻译器
            self.translator = Translator()
            
        except Exception as e:
            self.log_message(f"初始化翻译器时出错: {str(e)}")
            raise

    def create_main_frame(self):
        """创建主界面布局"""
        # 创建左右分割面板
        self.paned = ttk.PanedWindow(self.root, orient="horizontal")
        self.paned.pack(fill="both", expand=True, padx=5, pady=5)
        
        # 左侧日志面板
        self.log_frame = ttk.LabelFrame(self.paned, text="日志信息")
        self.log_text = tk.Text(self.log_frame, width=40, height=40)
        self.log_text.pack(fill="both", expand=True, padx=5, pady=5)
        self.paned.add(self.log_frame)
        
        # 右侧主要内容
        self.right_frame = ttk.Frame(self.paned)
        self.paned.add(self.right_frame)
        
        # 顶部按钮区
        self.button_frame = ttk.Frame(self.right_frame)
        self.button_frame.pack(fill="x", padx=5, pady=5)
        
        ttk.Button(self.button_frame, text="选择文件", command=self.select_file).pack(side="left", padx=5)
        ttk.Button(self.button_frame, text="开始翻译", command=self.start_translation).pack(side="left", padx=5)
        
        # 添加倒计时标签
        self.time_label = ttk.Label(self.button_frame, text="预计剩余时间: --:--")
        self.time_label.pack(side="left", padx=20)
        
        ttk.Button(self.button_frame, text="保存文件", command=self.save_file).pack(side="right", padx=5)
        
        # 进度条
        self.progress_frame = ttk.Frame(self.right_frame)
        self.progress_frame.pack(fill="x", padx=5, pady=5)
        self.progress_bar = ttk.Progressbar(
            self.progress_frame,
            variable=self.progress_var,
            maximum=100,
            mode='determinate'
        )
        self.progress_bar.pack(fill="x", padx=5)
        
        # 翻译内容表格
        self.create_translation_table()
        
        # 底部保存按钮
        ttk.Button(self.right_frame, text="保存文件", command=self.save_file).pack(side="bottom", pady=5)
        
    def create_translation_table(self):
        """创建翻译内容表格"""
        # 创建表格框架
        self.table_frame = ttk.Frame(self.right_frame)
        self.table_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        # 创建Treeview
        self.tree = ttk.Treeview(self.table_frame, columns=("source", "translation"), show="headings")
        self.tree.heading("source", text="原文")
        self.tree.heading("translation", text="译文")
        
        # 添加滚动条
        scrollbar = ttk.Scrollbar(self.table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        # 布局
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # 绑定双击事件用于编辑
        self.tree.bind("<Double-1>", self.edit_cell)
        
    def log_message(self, message):
        """添加日志信息"""
        self.log_text.insert("end", f"{message}\n")
        self.log_text.see("end")
        
    def select_file(self):
        """选择要翻译的文件"""
        file_path = filedialog.askopenfilename(
            filetypes=[("PO files", "*.po"), ("MO files", "*.mo")]
        )
        if file_path:
            self.current_file = file_path
            self.log_message(f"已选择文件: {file_path}")
            self.load_file()
            
    def load_file(self):
        """加载PO/MO文件内容"""
        try:
            # 判断文件类型并加载
            is_mo = self.current_file.endswith('.mo')
            if is_mo:
                self.po_file = polib.mofile(self.current_file)
                self.log_message("已加载MO文件，将在保存时自动转换为对应格式")
            else:
                self.po_file = polib.pofile(self.current_file)
                self.log_message("已加载PO文件")
                
            # 清空现有表格内容
            for item in self.tree.get_children():
                self.tree.delete(item)
                
            # 加载内容到表格
            for entry in self.po_file:
                if entry.msgid:
                    self.tree.insert("", "end", values=(entry.msgid, entry.msgstr))
                    
            self.log_message(f"成功加载了 {len(self.po_file)} 个翻译条目")
        except Exception as e:
            self.log_message(f"加载文件时出错: {str(e)}")
            messagebox.showerror("错误", f"加载文件时出错: {str(e)}")
            
    def start_translation(self):
        """开始翻译过程"""
        if not self.current_file:
            messagebox.showwarning("警告", "请先选择要翻译的文件")
            return
            
        # 重置计数器和开始时间
        self.processed_entries = 0
        self.translation_start_time = time.time()
        self.last_update_time = self.translation_start_time
        self.speed_samples = []
        self.total_entries = len([entry for entry in self.po_file if entry.msgid])
        self.initial_estimate = None
        self.time_label.config(text="预计剩余时间: 计算中...")
        
        # 开始定时更新时间估计
        self.update_time_estimate()
        
        # 在新线程中执行翻译
        threading.Thread(target=self.translate_content, daemon=True).start()

    def update_time_estimate(self):
        """更新预计完成时间"""
        if not self.translation_start_time:
            return
            
        try:
            current_time = time.time()
            elapsed_time = current_time - self.translation_start_time
            
            if self.processed_entries > 0:
                progress_percent = (self.processed_entries / self.total_entries)
                
                # 计算当前速度（每秒处理的条目数）
                current_speed = self.processed_entries / elapsed_time if elapsed_time > 0 else 0
                
                # 添加新的速度样本
                self.speed_samples.append(current_speed)
                # 只保留最近的5个样本
                if len(self.speed_samples) > 5:
                    self.speed_samples = self.speed_samples[-5:]
                
                # 使用加权移动平均速度，最近的样本权重更大
                weights = [0.1, 0.15, 0.2, 0.25, 0.3][-len(self.speed_samples):]
                avg_speed = sum(s * w for s, w in zip(self.speed_samples, weights))
                
                if avg_speed > 0:
                    # 如果还没有初始预估，计算初始预估
                    if self.initial_estimate is None and progress_percent > 0.1:
                        # 使用当前进度估算总时间
                        self.initial_estimate = elapsed_time / progress_percent
                    
                    # 结合初始预估和实时速度计算剩余时间
                    if self.initial_estimate is not None:
                        remaining_entries = self.total_entries - self.processed_entries
                        
                        # 使用加权平均，随着进度增加，实时速度的权重增加
                        weight_realtime = min(0.8, progress_percent + 0.2)
                        weight_initial = 1 - weight_realtime
                        
                        # 基于初始预估的剩余时间
                        initial_remaining = (self.initial_estimate * (1 - progress_percent))
                        # 基于当前速度的剩余时间
                        realtime_remaining = remaining_entries / avg_speed
                        
                        # 加权平均
                        estimated_seconds = (
                            initial_remaining * weight_initial +
                            realtime_remaining * weight_realtime
                        )
                        
                        # 添加缓冲时间（根据进度调整缓冲比例）
                        buffer_factor = 1.2 - (progress_percent * 0.2)  # 从1.2逐渐减少到1.0
                        estimated_seconds *= buffer_factor
                        
                        # 转换为分钟和秒
                        minutes = int(estimated_seconds // 60)
                        seconds = int(estimated_seconds % 60)
                        
                        # 更新标签
                        if progress_percent < 0.95:  # 进度小于95%时显示时间
                            self.time_label.config(
                                text=f"预计剩余时间: {minutes:02d}:{seconds:02d} ({progress_percent*100:.1f}%)"
                            )
                        else:
                            self.time_label.config(text=f"翻译即将完成... ({progress_percent*100:.1f}%)")
                else:
                    self.time_label.config(text=f"计算中... ({progress_percent*100:.1f}%)")
            else:
                self.time_label.config(text="预计剩余时间: 计算中...")
            
            # 如果还在翻译，继续更新
            if self.translation_start_time:
                self.root.after(1000, self.update_time_estimate)
                
        except Exception as e:
            self.log_message(f"更新时间估计时出错: {str(e)}")
            if self.translation_start_time:
                self.root.after(1000, self.update_time_estimate)

    def translate_content(self):
        """执行翻译过程"""
        try:
            entries = [entry for entry in self.po_file if entry.msgid]
            total = len(entries)
            batch_size = 2000  # 每批翻译的字符数限制
            current_batch = []
            current_batch_chars = 0
            
            for i, entry in enumerate(entries):
                # 更新进度条
                self.progress_var.set((i / total) * 100)
                self.root.update_idletasks()
                
                if not entry.msgid.strip():
                    continue
                    
                # 检查当前批次的字符数
                if current_batch_chars + len(entry.msgid) > batch_size:
                    # 翻译当前批次
                    self.translate_batch(current_batch)
                    current_batch = []
                    current_batch_chars = 0
                    
                current_batch.append(entry)
                current_batch_chars += len(entry.msgid)
                
            # 翻译最后一批
            if current_batch:
                self.translate_batch(current_batch)
                
            self.progress_var.set(100)
            self.translation_start_time = None  # 停止时间更新
            self.time_label.config(text="翻译完成")
            self.log_message("翻译完成")
            messagebox.showinfo("完成", "翻译已完成")
            
        except Exception as e:
            self.log_message(f"翻译过程中出错: {str(e)}")
            messagebox.showerror("错误", f"翻译过程中出错: {str(e)}")
            
    def translate_with_retry(self, text, max_retries=3, delay=1):
        """带重试机制的翻译函数"""
        for attempt in range(max_retries):
            try:
                return self.translator.translate(text, dest='zh-cn')
            except (SSLError, ConnectionError, Exception) as e:
                if attempt == max_retries - 1:  # 最后一次尝试
                    raise
                self.log_message(f"翻译出错 (尝试 {attempt + 1}/{max_retries}): {str(e)}")
                time.sleep(delay)  # 等待一段时间后重试
                # 重新初始化翻译器
                self.init_translator()
                
    def translate_batch(self, entries):
        """批量翻译条目"""
        try:
            # 使用不太可能出现在正常文本中的分隔符
            separator = "\n=+=+=+=+=\n"  # 使用多个特殊字符组合作为分隔符
            
            # 组合文本时添加索引标记
            combined_texts = []
            for i, entry in enumerate(entries):
                # 在每个文本前添加索引标记
                marked_text = f"[{i}]{entry.msgid}"
                combined_texts.append(marked_text)
            
            combined_text = separator.join(combined_texts)
            
            # 执行翻译（带重试机制）
            try:
                translation = self.translate_with_retry(combined_text)
                translated_text = translation.text
            except Exception as e:
                self.log_message(f"翻译失败，尝试减小批量大小重新翻译: {str(e)}")
                # 如果批量翻译失败，将批次分成两半重试
                if len(entries) > 1:
                    mid = len(entries) // 2
                    self.translate_batch(entries[:mid])
                    self.translate_batch(entries[mid:])
                    return
                else:
                    raise
            
            # 分割并处理翻译结果
            translated_parts = translated_text.split(separator)
            
            # 验证翻译结果数量
            if len(translated_parts) != len(entries):
                self.log_message(f"警告：翻译结果数量不匹配（原文：{len(entries)}，译文：{len(translated_parts)}）")
                # 如果数量不匹配，尝试减小批量重新翻译
                if len(entries) > 1:
                    mid = len(entries) // 2
                    self.translate_batch(entries[:mid])
                    self.translate_batch(entries[mid:])
                    return
            
            # 处理每个翻译结果
            for i, (entry, translated_part) in enumerate(zip(entries, translated_parts)):
                # 去除可能的索引标记和空白
                cleaned_text = translated_part.strip()
                if cleaned_text.startswith(f"[{i}]"):
                    cleaned_text = cleaned_text[len(f"[{i}]"):].strip()
                
                # 更新PO文件和表格
                entry.msgstr = cleaned_text
                
                # 更新表格显示
                for item in self.tree.get_children():
                    if self.tree.item(item)['values'][0] == entry.msgid:
                        self.tree.item(item, values=(entry.msgid, cleaned_text))
                        self.tree.see(item)  # 滚动到当前项
                        break
            
            # 更新已处理的条目数
            self.processed_entries += len(entries)
            
            self.log_message(f"成功翻译了 {len(entries)} 个条目")
            
        except Exception as e:
            self.log_message(f"批量翻译时出错: {str(e)}")
            raise
            
    def edit_cell(self, event):
        """处理单元格编辑"""
        item = self.tree.selection()[0]
        column = self.tree.identify_column(event.x)
        
        if column == "#2":  # 只允许编辑译文列
            value = self.tree.item(item)['values']
            x, y, w, h = self.tree.bbox(item, column)
            
            entry_edit = ttk.Entry(self.tree)
            entry_edit.place(x=x, y=y, width=w, height=h)
            entry_edit.insert(0, value[1])
            entry_edit.select_range(0, tk.END)
            
            def save_edit(event):
                new_text = entry_edit.get()
                self.tree.set(item, column="#2", value=new_text)
                # 更新PO文件中的译文
                for entry in self.po_file:
                    if entry.msgid == value[0]:
                        entry.msgstr = new_text
                        break
                entry_edit.destroy()
                
            entry_edit.bind('<Return>', save_edit)
            entry_edit.bind('<FocusOut>', save_edit)
            entry_edit.focus()
            
    def save_file(self):
        """保存翻译后的文件"""
        if not self.current_file:
            messagebox.showwarning("警告", "没有打开的文件")
            return
            
        try:
            # 获取原文件的目录和文件名
            directory = os.path.dirname(self.current_file)
            filename = os.path.basename(self.current_file)
            base, ext = os.path.splitext(filename)
            
            # 创建保存文件对话框
            file_types = [("PO 文件", "*.po"), ("MO 文件", "*.mo")]
            save_path = filedialog.asksaveasfilename(
                initialdir=directory,
                initialfile=f"{base}_zh{ext}",
                filetypes=file_types,
                defaultextension=ext
            )
            
            if not save_path:
                return
                
            # 根据选择的文件类型保存
            if save_path.endswith('.mo'):
                self.log_message("正在保存为MO格式...")
                self.po_file.save_as_mofile(save_path)
            else:
                self.log_message("正在保存为PO格式...")
                self.po_file.save(save_path)
            
            self.log_message(f"文件已保存至: {save_path}")
            messagebox.showinfo("成功", f"文件已保存至:\n{save_path}")
            
        except Exception as e:
            self.log_message(f"保存文件时出错: {str(e)}")
            messagebox.showerror("错误", f"保存文件时出错: {str(e)}")

if __name__ == "__main__":
    root = ttk.Window(themename="cosmo")
    app = TranslatorApp(root)
    root.mainloop()
