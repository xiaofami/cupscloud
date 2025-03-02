import os
import re
import subprocess
import logging
from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = '/tmp/print_uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
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
        'advanced_options': []
    }
    
    option_patterns = [
        (r'(?i)(PageSize|Media Size)\s*[:=]\s*(.*)', 'media_sizes'),
        (r'(?i)(InputSlot|Media Source)\s*[:=]\s*(.*)', 'input_slots'),
        (r'(?i)(Resolution|Output Resolution|MediaType|Print Quality)\s*[:=]\s*(.*)', 'quality_options'),
        (r'(?i)(Brightness|Contrast)\s*[:=]\s*(.*)', 'advanced_options'),
        # 新增双面打印选项检测
        (r'(?i)(sides|Duplex)\s*[:=]\s*(.*)', 'duplex_options')
    ]

    for line in output.split('\n'):
        line = line.strip()
        for pattern, key in option_patterns:
            match = re.search(pattern, line)
            if match:
                raw_values = match.group(2).split()
                
                # 处理默认值
                clean_values = []
                default_value = None
                
                # 提取带*号的默认值
                for v in raw_values:
                    if '*' in v:
                        default_value = v.replace('*', '')
                
                # 去重并排序
                seen = set()
                deduped = []
                
                if default_value:
                    deduped.append(default_value)
                    seen.add(default_value)
                
                others = sorted(
                    [v.replace('*', '') for v in raw_values if v != default_value],
                    key=lambda x: x.lower()
                )
                for v in others:
                    if v not in seen:
                        deduped.append(v)
                        seen.add(v)
                
                options[key] = deduped
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
            raise Exception(result.stderr.decode())
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
        'advanced_options': options.get('advanced_options', []),
        'duplex_options': options.get('duplex_options', [])  # 新增双面打印选项
    })

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file selected'}), 400
    
    file = request.files['file']
    if not file or file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': 'Unsupported file type'}), 400

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

        # 参数验证
        if not params['media']:
            return jsonify({'error': '必须选择纸张尺寸'}), 400

        cmd = ['lp', '-n', params['copies']]
        if params['printer']:
            cmd.extend(['-d', params['printer']])

        # 构建打印选项
        options = []
        if params['pages']:
            options.append(f'page-ranges={params["pages"]}')
        if params['page_set'] != 'all':
            options.append(f'page-set={params["page_set"]}')
        if params['quality']:
            options.append(params["quality"])
        if params['input_slot']:
            options.append(f'media-source={params["input_slot"]}')
        if params['brightness']:
            options.append(f'Brightness={params["brightness"]}')
        if params['contrast']:
            options.append(f'Contrast={params["contrast"]}')
        
        # 修复双面打印逻辑
        duplex_mode = 'two-sided-long-edge'  # 默认双面模式
        if params['duplex'] == 'true':
            # 检查打印机支持的双面模式
            printer_opts = get_printer_options(params['printer'])
            if 'duplex_options' in printer_opts:
                if 'DuplexTumble' in printer_opts['duplex_options']:
                    duplex_mode = 'DuplexTumble'
                elif 'DuplexNoTumble' in printer_opts['duplex_options']:
                    duplex_mode = 'DuplexNoTumble'
            options.append(f'sides={duplex_mode}')
        else:
            options.append('sides=one-sided')

        options.extend([
            f'media={params["media"]}'
        ])

        for opt in options:
            cmd.extend(['-o', opt])
        cmd.append(upload_path)

        # 记录最终打印命令
        logger.info(f"执行打印命令: {' '.join(cmd)}")

        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30
        )

        if result.returncode == 0:
            return jsonify({
                'message': 'Print job submitted',
                'job_id': result.stdout.decode().strip()
            })
        else:
            error_msg = result.stderr.decode() or 'Unknown error'
            logger.error(f"打印失败: {error_msg}")
            return jsonify({'error': f'Print failed: {error_msg}'}), 500

    except Exception as e:
        logger.error(f"System error: {str(e)}")
        return jsonify({'error': f'System error: {str(e)}'}), 500
    finally:
        if os.path.exists(upload_path):
            try: os.remove(upload_path)
            except: pass

if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    app.run(host='0.0.0.0', port=5000)
