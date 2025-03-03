import os
import re
import subprocess
import logging
from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = '/tmp/print_uploads'
app.config['MAX_CONTENT_LENGTH'] = 1600 * 1024 * 1024
app.config['ALLOWED_EXTENSIONS'] = {'pdf', 'ps', 'txt', 'docx'}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('CloudPrint')

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def get_printers():
    try:
        output = subprocess.check_output(['lpstat', '-a'], timeout=5).decode()
        printers = [line.split()[0] for line in output.split('\n') if line]
        return printers if printers else ["默认打印机"]
    except Exception as e:
        logger.error(f"获取打印机列表失败: {str(e)}")
        return ["默认打印机"]

def validate_pages(pages):
    if not pages:
        return True
    return re.match(r'^\d+(-\d+)?(,\d+(-\d+)?)*$', pages) is not None

def parse_printer_options(output):
    options = {
        'media_sizes': [],
        'input_slots': [],
        'quality_options': [],
        'quality_option_name': 'Resolution',  # 默认值
        'advanced_options': [],
        'duplex_options': []
    }
    
    option_patterns = [
        (r'(?i)(PageSize|Media Size)\s*[:=]\s*(.*)', 'media_sizes'),
        (r'(?i)(InputSlot|Media Source)\s*[:=]\s*(.*)', 'input_slots'),
        (r'(?i)(Resolution|Output Resolution|MediaType|Print Quality|PrintMode)\s*[:=]\s*(.*)', 'quality_options'),
        (r'(?i)(Brightness|Contrast)\s*[:=]\s*(.*)', 'advanced_options'),
        (r'(?i)(sides|Duplex)\s*[:=]\s*(.*)', 'duplex_options')
    ]

    for line in output.split('\n'):
        line = line.strip()
        for pattern, key in option_patterns:
            match = re.search(pattern, line)
            if match:
                # 增强质量参数名称处理
                if key == 'quality_options':
                    raw_name = match.group(1).strip()
                    logger.debug(f"原始质量参数名称: {raw_name}")
                    
                    # 分割备选名称并清理
                    candidates = [x.strip() for x in re.split(r'\/+', raw_name)]
                    
                    # 选择策略：优先无空格 -> 首字母大写的 -> 第一个候选
                    selected = None
                    for c in candidates:
                        if ' ' not in c:
                            selected = c
                            break
                    if not selected:
                        selected = next((c for c in candidates if c.istitle()), candidates[0])
                    
                    # 提取有效参数名称
                    clean_name = re.sub(r'[^a-zA-Z0-9_-]', ' ', selected).strip()
                    parts = [p for p in re.split(r'\s+', clean_name) if p]
                    
                    # 智能选择参数名称部分
                    if len(parts) > 1:
                        # 优先包含"quality"或"resolution"的部分
                        key_part = next((p for p in parts if p.lower() in ['quality', 'resolution']), parts[-1])
                    else:
                        key_part = parts[-1] if parts else 'Resolution'
                    
                    options['quality_option_name'] = key_part
                    logger.info(f"解析后的质量参数名称: {key_part} (原始: {raw_name})")

                # 处理参数值
                raw_values = re.split(r'\s+', match.group(2).strip())
                clean_values = []
                default_found = False

                for val in raw_values:
                    # 处理带星号的默认值
                    if '*' in val:
                        clean_val = val.replace('*', '')
                        if not default_found:
                            clean_values.insert(0, clean_val)  # 默认值放首位
                            default_found = True
                        continue
                    
                    # 去重处理
                    if val not in clean_values:
                        clean_values.append(val)

                # 特殊处理media sizes的排序
                if key == 'media_sizes':
                    size_order = ['A4', 'Letter', 'Legal', 'A3', 'B4']
                    clean_values = sorted(
                        clean_values,
                        key=lambda x: size_order.index(x) if x in size_order else len(size_order)
                    )

                options[key] = clean_values
                break

    return options

def get_printer_options(printer_name):
    try:
        result = subprocess.run(
            ['lpoptions', '-p', printer_name, '-l'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10
        )
        if result.returncode != 0:
            raise Exception(result.stderr.decode().strip())
        return parse_printer_options(result.stdout.decode())
    except Exception as e:
        logger.error(f"获取打印机选项失败: {str(e)}")
        return {}

@app.route('/')
def index():
    printers = get_printers()
    return render_template('index.html', printers=printers)

@app.route('/api/printer_options/<printer_name>')
def get_printer_options_route(printer_name):
    options = get_printer_options(printer_name)
    return jsonify({
        'media_sizes': options.get('media_sizes', []),
        'input_slots': options.get('input_slots', []),
        'quality_options': options.get('quality_options', []),
        'quality_option_name': options.get('quality_option_name', 'Resolution'),
        'advanced_options': options.get('advanced_options', []),
        'duplex_options': options.get('duplex_options', [])
    })

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file selected', 'command': ''}), 400
    
    file = request.files['file']
    if not file or file.filename == '':
        return jsonify({'error': 'No file selected', 'command': ''}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': 'Unsupported file type', 'command': ''}), 400

    try:
        filename = secure_filename(file.filename)
        upload_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        os.makedirs(os.path.dirname(upload_path), exist_ok=True)
        file.save(upload_path)

        params = {
            'printer': request.form.get('printer', ''),
            'copies': request.form.get('copies', '1'),
            'duplex': request.form.get('duplex', 'false'),
            'media': request.form.get('media', ''),
            'pages': request.form.get('pages', ''),
            'page_set': request.form.get('page_set', 'all'),
            'quality': request.form.get('quality', ''),
            'input_slot': request.form.get('input_slot', ''),
            'brightness': request.form.get('brightness', ''),
            'contrast': request.form.get('contrast', '')
        }

        if not params['media']:
            return jsonify({'error': '必须选择纸张尺寸', 'command': ''}), 400

        cmd = ['lp', '-n', params['copies']]
        if params['printer']:
            cmd.extend(['-d', params['printer']])

        printer_opts = get_printer_options(params['printer'])
        quality_opt = printer_opts.get('quality_option_name', 'Resolution')

        options = []
        if params['pages']:
            if validate_pages(params['pages']):
                options.append(f'page-ranges={params["pages"]}')
            else:
                return jsonify({'error': '无效的页码范围格式', 'command': ''}), 400

        if params['page_set'] != 'all':
            options.append(f'page-set={params["page_set"]}')
        
        if params['quality']:
            options.append(f'{quality_opt}={params["quality"]}')
        
        if params['input_slot']:
            options.append(f'media-source={params["input_slot"]}')
        
        if params['brightness']:
            options.append(f'Brightness={params["brightness"]}')
        
        if params['contrast']:
            options.append(f'Contrast={params["contrast"]}')

        # 处理双面打印
        duplex_mapping = {
            'long-edge': 'two-sided-long-edge',
            'short-edge': 'two-sided-short-edge',
            'tumble': 'DuplexTumble',
            'no-tumble': 'DuplexNoTumble'
        }
        if params['duplex'] in duplex_mapping:
            options.append(f'sides={duplex_mapping[params["duplex"]]}')
        else:
            options.append('sides=one-sided')

        options.append(f'media={params["media"]}')

        # 构建最终命令
        for opt in options:
            cmd.extend(['-o', opt])
        cmd.append(upload_path)
        
        readable_cmd = ' '.join(cmd).replace(upload_path, f'{filename}')
        logger.info(f"执行打印命令: {cmd}")

        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30
        )

        if result.returncode == 0:
            return jsonify({
                'message': '打印任务已提交',
                'job_id': result.stdout.decode().strip(),
                'command': readable_cmd
            })
        else:
            error_msg = result.stderr.decode().strip() or '未知错误'
            logger.error(f"打印失败: {error_msg}\n命令: {readable_cmd}")
            return jsonify({
                'error': f'打印失败: {error_msg}',
                'command': readable_cmd
            }), 500

    except Exception as e:
        error_msg = f'系统错误: {str(e)}'
        logger.error(error_msg, exc_info=True)
        return jsonify({'error': error_msg, 'command': ''}), 500
    finally:
        if os.path.exists(upload_path):
            try: os.remove(upload_path)
            except: pass

if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    app.run(host='0.0.0.0', port=5000)
