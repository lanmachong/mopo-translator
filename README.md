# PO/MO文件翻译器

一个基于Web的PO/MO文件翻译工具，支持批量翻译和在线编辑。

## 功能特点

- 支持.po和.mo文件的上传和翻译
- 批量翻译功能，自动处理大文件
- 实时翻译进度显示
- 在线编辑翻译结果
- 自动保存编辑内容
- 文件临时存储（1天后自动清理）

## 技术栈

- 后端：Python + Flask
- 前端：HTML + JavaScript
- 翻译：Google Translate API
- 文件处理：polib

## 安装说明

1. 克隆仓库：
```bash
git clone https://github.com/yourusername/mopo-translator.git
cd mopo-translator
```

2. 安装依赖：
```bash
pip install -r requirements.txt
```

3. 运行应用：
```bash
python app.py
```

4. 访问应用：
打开浏览器访问 `http://localhost:5000`

## 使用说明

1. 点击"选择文件"按钮上传.po或.mo文件
2. 点击"开始翻译"按钮开始翻译
3. 等待翻译完成，可以在表格中查看和编辑翻译结果
4. 编辑后点击"保存修改"保存更改
5. 点击"下载翻译文件"下载最终结果

## 注意事项

- 上传文件大小限制为16MB
- 翻译结果保存24小时后自动删除
- 建议定期下载已翻译的文件

## 许可证

MIT License

## 贡献指南

欢迎提交Issue和Pull Request！

1. Fork本仓库
2. 创建特性分支：`git checkout -b my-new-feature`
3. 提交更改：`git commit -am 'Add some feature'`
4. 推送分支：`git push origin my-new-feature`
5. 提交Pull Request
