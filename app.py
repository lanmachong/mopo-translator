from flask import Flask, request, jsonify, render_template, send_file, Response, stream_with_context
import os
import polib
from googletrans import Translator
import tempfile
import time
from werkzeug.utils import secure_filename
import json
from datetime import datetime, timedelta

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['UPLOAD_FOLDER'] = tempfile.gettempdir()

def allowed_file(filename):
    """检查文件是否允许上传"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'po', 'mo'}

def translate_batch(entries, start_idx, batch_size):
    """批量翻译条目"""
    translator = None
    max_retries = 3
    retry_delay = 2  # 重试延迟秒数
    
    # 收集这个批次的所有条目
    batch = entries[start_idx:start_idx + batch_size]
    
    for retry in range(max_retries):
        try:
            if translator is None:
                translator = Translator()
            
            # 使用特殊分隔符
            separator = "\n=+=+=+=+=\n"
            
            # 组合文本时添加索引标记
            combined_texts = []
            for i, entry in enumerate(batch):
                if entry.msgid and entry.msgid.strip():
                    # 在每个文本前添加索引标记
                    marked_text = f"[{i}]{entry.msgid}"
                    combined_texts.append(marked_text)
            
            if not combined_texts:
                return True
            
            combined_text = separator.join(combined_texts)
            
            # 执行翻译
            translation = translator.translate(combined_text, dest='zh-cn')
            
            if translation and translation.text:
                # 分割并处理翻译结果
                translated_parts = translation.text.split(separator)
                
                # 验证翻译结果数量
                if len(translated_parts) == len(combined_texts):
                    # 处理每个翻译结果
                    for i, (entry, translated_part) in enumerate(zip(batch, translated_parts)):
                        if entry.msgid and entry.msgid.strip():
                            # 去除可能的索引标记和空白
                            cleaned_text = translated_part.strip()
                            if cleaned_text.startswith(f"[{i}]"):
                                cleaned_text = cleaned_text[len(f"[{i}]"):].strip()
                            entry.msgstr = cleaned_text
                    return True
                else:
                    print(f"警告：翻译结果数量不匹配（原文：{len(combined_texts)}，译文：{len(translated_parts)}）")
                    # 如果数量不匹配，单独翻译每个条目
                    for entry in batch:
                        if entry.msgid and entry.msgid.strip():
                            single_translation = translator.translate(entry.msgid, dest='zh-cn')
                            if single_translation and single_translation.text:
                                entry.msgstr = single_translation.text.strip()
                    return True
            
            time.sleep(0.5)  # 批次间延迟
            
        except Exception as e:
            print(f"批次翻译出错 (重试 {retry + 1}/{max_retries}): {str(e)}")
            translator = None  # 重置翻译器
            if retry < max_retries - 1:
                time.sleep(retry_delay)
            continue
    
    print("达到最大重试次数，跳过当前批次")
    return False

def cleanup_old_files():
    """清理超过1天的临时文件"""
    now = datetime.now()
    upload_dir = os.path.join(os.path.dirname(__file__), 'uploads')
    if not os.path.exists(upload_dir):
        return
        
    for filename in os.listdir(upload_dir):
        file_path = os.path.join(upload_dir, filename)
        file_modified = datetime.fromtimestamp(os.path.getmtime(file_path))
        if now - file_modified > timedelta(days=1):
            try:
                os.remove(file_path)
            except:
                pass

@app.route('/')
def index():
    """渲染主页"""
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    """处理文件上传"""
    if 'file' not in request.files:
        return jsonify({'error': '没有上传文件'}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': '没有选择文件'}), 400
        
    if not allowed_file(file.filename):
        return jsonify({'error': '不支持的文件类型'}), 400
        
    try:
        # 保存上传的文件
        filename = secure_filename(file.filename)
        temp_input = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(temp_input)
        
        # 返回文件路径和名称
        return jsonify({
            'status': 'success',
            'filepath': temp_input,
            'filename': filename
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/translate', methods=['POST'])
def translate():
    """处理翻译请求"""
    data = request.get_json()
    filepath = data.get('filepath')
    filename = data.get('filename')
    
    if not filepath or not os.path.exists(filepath):
        return jsonify({'error': '文件不存在'}), 400
        
    def generate():
        try:
            # 加载PO/MO文件
            is_mo = filename.endswith('.mo')
            po_file = polib.mofile(filepath) if is_mo else polib.pofile(filepath)
            
            entries = [entry for entry in po_file if entry.msgid and entry.msgid.strip()]
            total_entries = len(entries)
            processed_entries = 0
            batch_size = 50  # 每批处理的条目数
            failed_entries = []
            
            if total_entries == 0:
                yield f"data: {json.dumps({'error': '文件中没有需要翻译的内容'})}\n\n"
                return
                
            # 开始时间
            start_time = time.time()
            last_progress_time = start_time
            speed_samples = []
            initial_estimate = None
            
            # 分批翻译
            for i in range(0, total_entries, batch_size):
                current_batch_size = min(batch_size, total_entries - i)
                success = translate_batch(entries, i, current_batch_size)
                
                if success:
                    processed_entries += current_batch_size
                else:
                    # 记录失败的条目
                    failed_entries.extend(range(i, i + current_batch_size))
                
                # 每秒最多更新一次进度
                current_time = time.time()
                if current_time - last_progress_time >= 1.0:
                    # 计算进度和预计剩余时间
                    progress = (processed_entries / total_entries) * 100
                    elapsed_time = current_time - start_time
                    
                    if processed_entries > 0 and elapsed_time > 0:
                        # 计算当前速度（每秒处理的条目数）
                        current_speed = processed_entries / elapsed_time
                        
                        # 添加新的速度样本
                        speed_samples.append(current_speed)
                        # 只保留最近的5个样本
                        if len(speed_samples) > 5:
                            speed_samples = speed_samples[-5:]
                        
                        # 使用加权移动平均速度，最近的样本权重更大
                        weights = [0.1, 0.15, 0.2, 0.25, 0.3][-len(speed_samples):]
                        avg_speed = sum(s * w for s, w in zip(speed_samples, weights))
                        
                        if avg_speed > 0:
                            # 如果还没有初始预估，计算初始预估
                            if initial_estimate is None and progress > 10:
                                # 使用当前进度估算总时间
                                initial_estimate = elapsed_time / (progress / 100)
                            
                            # 结合初始预估和实时速度计算剩余时间
                            if initial_estimate is not None:
                                remaining_entries = total_entries - processed_entries
                                
                                # 使用加权平均，随着进度增加，实时速度的权重增加
                                weight_realtime = min(0.8, progress/100 + 0.2)
                                weight_initial = 1 - weight_realtime
                                
                                # 基于初始预估的剩余时间
                                initial_remaining = (initial_estimate * (1 - progress/100))
                                # 基于当前速度的剩余时间
                                realtime_remaining = remaining_entries / avg_speed if avg_speed > 0 else 0
                                
                                # 加权平均
                                estimated_seconds = (
                                    initial_remaining * weight_initial +
                                    realtime_remaining * weight_realtime
                                )
                                
                                # 添加缓冲时间（根据进度调整缓冲比例）
                                buffer_factor = 1.2 - ((progress/100) * 0.2)  # 从1.2逐渐减少到1.0
                                estimated_seconds *= buffer_factor
                                
                                # 转换为分钟和秒
                                minutes = int(estimated_seconds // 60)
                                seconds = int(estimated_seconds % 60)
                                
                                time_remaining = f"{minutes:02d}:{seconds:02d}"
                            else:
                                time_remaining = "计算中..."
                        else:
                            time_remaining = "计算中..."
                    else:
                        time_remaining = "计算中..."
                        
                    # 获取当前批次的预览数据
                    preview_entries = entries[max(0, i-5):i+current_batch_size]
                    preview_data = [
                        {
                            'msgid': entry.msgid,
                            'msgstr': entry.msgstr if entry.msgstr else ''
                        }
                        for entry in preview_entries
                    ]
                    
                    # 发送进度更新
                    yield f"data: {json.dumps({
                        'progress': progress,
                        'time_remaining': time_remaining,
                        'processed': processed_entries,
                        'total': total_entries,
                        'failed': len(failed_entries),
                        'preview': preview_data
                    })}\n\n"
                    
                    last_progress_time = current_time
                
            # 保存翻译后的文件
            base_name, ext = os.path.splitext(filename)
            output_filename = f"{base_name}_zh{ext}"
            temp_output = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)
            
            if is_mo:
                po_file.save_as_mofile(temp_output)
            else:
                po_file.save(temp_output)
                
            # 发送完成消息
            completion_message = {
                'status': 'complete',
                'output_file': temp_output,
                'output_filename': output_filename,
                'total_processed': processed_entries,
                'total_entries': total_entries,
                'failed_entries': len(failed_entries)
            }
            
            if failed_entries:
                completion_message['warning'] = f'有 {len(failed_entries)} 个条目翻译失败'
                
            yield f"data: {json.dumps(completion_message)}\n\n"
            
        except Exception as e:
            error_message = f"翻译过程中发生错误: {str(e)}"
            print(error_message)
            yield f"data: {json.dumps({'error': error_message})}\n\n"
            
        finally:
            # 清理临时文件
            try:
                if os.path.exists(filepath):
                    os.remove(filepath)
            except Exception as e:
                print(f"清理临时文件时出错: {str(e)}")
    
    return Response(stream_with_context(generate()), mimetype='text/event-stream')

@app.route('/save_edits', methods=['POST'])
def save_edits():
    """保存编辑后的翻译"""
    try:
        data = request.get_json()
        filename = data.get('filename')
        edits = data.get('edits', [])
        
        if not filename or not edits:
            return jsonify({"error": "Missing required data"}), 400
            
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if not os.path.exists(filepath):
            return jsonify({"error": "Original file not found"}), 404
            
        # 读取PO文件
        po = polib.pofile(filepath)
        
        # 应用编辑
        edit_map = {item['msgid']: item['msgstr'] for item in edits}
        for entry in po:
            if entry.msgid in edit_map:
                entry.msgstr = edit_map[entry.msgid]
        
        # 保存为新文件
        edited_filename = f"edited_{filename}"
        edited_filepath = os.path.join(app.config['UPLOAD_FOLDER'], edited_filename)
        po.save(edited_filepath)
        
        return jsonify({
            "message": "Changes saved successfully",
            "filename": edited_filename
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/download/<path:filename>')
def download_file(filename):
    """下载翻译文件"""
    try:
        # 清理旧文件
        cleanup_old_files()
        
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if not os.path.exists(filepath):
            return jsonify({"error": "File not found"}), 404
            
        return send_file(
            filepath,
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 400

if __name__ == '__main__':
    app.run(debug=True)
