# -*- coding: utf-8 -*-
<<<<<<< HEAD
from flask import Flask, render_template, request
from openai import OpenAI
import sys
import os
sys.stdout.reconfigure(encoding='utf-8')
app = Flask(__name__)

client = OpenAI(
    api_key="sk-4uKbsxhCgrcTxFea7N85Yvedx7Kql0RfvSOeujL0oqH9iEZK",  # ⚠️ 不要贴出来
    base_url="https://www.51api.org/v1"  # ⚠️ 用 51API 文档里的 base_url
)

@app.route('/')
def index():
    return render_template('index.html')
@app.route('/summarize', methods=['POST'])
def summarize():
    content = request.form['content']

    try:
        response = client.chat.completions.create(
            model="gpt-5",  # ⚠️ 例如 'gpt-4.1-mini-51'
            messages=[{"role": "user", "content": f"请用1句话总结以下内容：\n{content}"}],
            max_tokens=100
        )
        summary = response.choices[0].message.content.strip()
    except Exception as e:
        print("详细错误:", e)
        summary = "出错了，请检查服务器日志"

    return render_template("index.html", summary=summary, content=content)
=======
from flask import Flask, render_template, request, redirect, url_for
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from openai import OpenAI
import sys
import os
import re
import yt_dlp

sys.stdout.reconfigure(encoding='utf-8')
app = Flask(__name__)

# ==================== 配置区域 ====================
app.config['SECRET_KEY'] = 'your-secret-key-change-this-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

client = OpenAI(
    api_key="sk-4uKbsxhCgrcTxFea7N85Yvedx7Kql0RfvSOeujL0oqH9iEZK",
    base_url="https://www.51api.org/v1"
)

MODEL_NAME = "gpt-4o"

# 初始化扩展
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = '请先登录以访问此页面'

# ==================== 用户模型 ====================
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# 创建数据库表
with app.app_context():
    db.create_all()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# =================================================

def extract_video_info(url):
    """
    提取视频信息：优先获取字幕，无字幕则返回标题+描述
    返回: (内容文本, 信息类型)
    信息类型: 'subtitles' 或 'metadata'
    """
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'writesubtitles': True,
        'writeautomaticsub': True,
        'subtitleslangs': ['zh', 'zh-CN', 'zh-TW', 'en'],
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

            subtitles = info.get('subtitles', {})
            for lang in ['zh', 'zh-CN', 'zh-TW', 'en']:
                if lang in subtitles:
                    subtitle_url = subtitles[lang][0]['url']
                    import urllib.request
                    with urllib.request.urlopen(subtitle_url) as response:
                        subtitle_content = response.read().decode('utf-8')
                        clean_text = clean_subtitle(subtitle_content)
                        return clean_text, 'subtitles'

            automatic_captions = info.get('automatic_captions', {})
            for lang in ['zh', 'zh-CN', 'zh-TW', 'zh-CN-en', 'en', 'en-orig']:
                if lang in automatic_captions:
                    subtitle_url = automatic_captions[lang][0]['url']
                    import urllib.request
                    with urllib.request.urlopen(subtitle_url) as response:
                        subtitle_content = response.read().decode('utf-8')
                        clean_text = clean_subtitle(subtitle_content)
                        return f"[自动生成字幕]\n{clean_text}", 'subtitles'

            title = info.get('title', '未知标题')
            description = info.get('description', '')
            duration = info.get('duration', 0)
            duration_str = f"{duration // 60}分{duration % 60}秒" if duration else "未知"

            metadata = f"视频标题：{title}\n视频时长：{duration_str}\n视频描述：{description or '无描述'}"
            return metadata, 'metadata'

    except Exception as e:
        return None, f"提取失败：{str(e)}"


def clean_subtitle(subtitle_text):
    """清理字幕文件，去除时间戳、HTML标签等"""
    text = re.sub(r'\d{2}:\d{2}:\d{2}\.\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}\.\d{3}', '', subtitle_text)
    text = re.sub(r'^\d+\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'WEBVTT.*\n', '', text)
    text = '\n'.join(line.strip() for line in text.split('\n') if line.strip())
    return text


def is_video_url(text):
    """简单判断是否为视频URL"""
    video_patterns = [
        r'(youtube\.com|youtu\.be)',
        r'(bilibili\.com|b23\.tv)',
        r'(douyin\.com)',
        r'(tiktok\.com)',
        r'(ixigua\.com)',
        r'(weibo\.com)',
        r'(youku\.com)',
    ]
    return any(re.search(pattern, text) for pattern in video_patterns)


@app.route('/')
def index():
    if current_user.is_authenticated:
        return render_template('index.html')
    return redirect(url_for('login'))


@app.route('/summarize', methods=['POST'])
@login_required
def summarize():
    user_input = request.form['content'].strip()

    if not user_input:
        return render_template("index.html", error="请输入内容或视频链接")

    if is_video_url(user_input):
        video_content, info_type = extract_video_info(user_input)

        if video_content is None:
            return render_template("index.html",
                                   error=f"无法提取视频信息：{info_type}",
                                   content=user_input)

        if info_type == 'subtitles':
            prompt = f"请根据以下视频字幕内容，分点列出主要要点：\n\n{video_content[:8000]}"
        else:
            prompt = f"请根据以下视频标题和描述，推测视频可能的内容并分点列出要点：\n\n{video_content}"

        source_info = f"【视频】{info_type}"
    else:
        video_content = None
        prompt = f"请分点列出以下内容的要点：\n\n{user_input[:8000]}"
        source_info = "【文本】"

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500
        )
        summary = response.choices[0].message.content.strip()
    except Exception as e:
        print("API错误:", e)
        summary = f"分析出错：{str(e)}"

    return render_template("index.html",
                           summary=summary,
                           content=user_input,
                           source_info=source_info,
                           raw_content=video_content[:2000] if video_content else None)


# ==================== 认证路由 ====================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if not username or not password:
            return render_template('login.html', error='请输入用户名和密码')

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error='用户名或密码错误')

    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        if not username or not password:
            return render_template('register.html', error='请填写所有字段')

        if len(password) < 6:
            return render_template('register.html', error='密码长度至少为6位')

        if password != confirm_password:
            return render_template('register.html', error='两次输入的密码不一致')

        if User.query.filter_by(username=username).first():
            return render_template('register.html', error='用户名已被使用')

        new_user = User(username=username)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()

        return render_template('login.html', success='注册成功！请登录')

    return render_template('register.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))
>>>>>>> fc91ce0d4bd7d155949359319cde7a8c65598351


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
<<<<<<< HEAD
    app.run(host='0.0.0.0', port=port)
=======
    app.run(host='0.0.0.0', port=port, debug=True)
>>>>>>> fc91ce0d4bd7d155949359319cde7a8c65598351
