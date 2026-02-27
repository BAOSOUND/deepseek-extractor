import streamlit as st
import requests
import pandas as pd
import json
import re
from urllib.parse import urlparse
from datetime import datetime
# ===== 新增品牌分析 =====
import openai
# ===== 结束新增 =====

st.set_page_config(page_title="DeepSeek引用提取器", page_icon="🔗", layout="wide")

# 自定义CSS，让表格自动换行
st.markdown("""
<style>
    /* 让表格单元格内容自动换行 */
    .stDataFrame div[data-testid="stDataFrameResizable"] div[data-testid="column-header-0"],
    .stDataFrame div[data-testid="stDataFrameResizable"] div[data-testid="column-header-1"],
    .stDataFrame div[data-testid="stDataFrameResizable"] div[data-testid="column-header-2"],
    .stDataFrame div[data-testid="stDataFrameResizable"] div[data-testid="column-header-3"],
    .stDataFrame div[data-testid="stDataFrameResizable"] div[data-testid="column-header-4"],
    .stDataFrame td {
        white-space: normal !important;
        word-wrap: break-word !important;
        max-width: none !important;
    }
    
    /* 调整列宽比例 */
    div[data-testid="stDataFrameResizable"] div[data-testid="column-header-0"] { width: 5% !important; }  /* 序号 */
    div[data-testid="stDataFrameResizable"] div[data-testid="column-header-1"] { width: 15% !important; } /* 网站 */
    div[data-testid="stDataFrameResizable"] div[data-testid="column-header-2"] { width: 40% !important; } /* 标题 */
    div[data-testid="stDataFrameResizable"] div[data-testid="column-header-3"] { width: 30% !important; } /* URL */
    div[data-testid="stDataFrameResizable"] div[data-testid="column-header-4"] { width: 10% !important; } /* 发布时间 */
    
    /* 确保表格容器没有滚动条 */
    div[data-testid="stDataFrameResizable"] {
        overflow-x: hidden !important;
    }
    
    /* 链接样式 */
    .citation-link {
        color: #0066cc;
        text-decoration: none;
        word-break: break-all;
    }
    .citation-link:hover {
        text-decoration: underline;
    }
    
    /* ===== 新增品牌分析样式 ===== */
    .brand-card {
        background-color: #f0f2f6;
        border-radius: 10px;
        padding: 20px;
        margin: 10px 0;
        border-left: 5px solid #0066cc;
    }
    .brand-name {
        font-size: 18px;
        font-weight: bold;
        color: #0066cc;
    }
    .brand-table {
        width: 100%;
        border-collapse: collapse;
        margin: 10px 0;
    }
    .brand-table th {
        background-color: #0066cc;
        color: white;
        padding: 10px;
        text-align: left;
    }
    .brand-table td {
        padding: 8px;
        border: 1px solid #ddd;
    }
    .brand-table tr:nth-child(even) {
        background-color: #f9f9f9;
    }
    /* ===== 结束新增 ===== */
</style>
""", unsafe_allow_html=True)

st.title("🔗 DeepSeek 分享链接引用提取器")
st.markdown("---")

st.markdown("""
### 📌 使用说明
1. 在 **DeepSeek 网页版** 完成搜索后，点击「分享」→「创建分享链接」
2. 复制生成的链接（格式：`https://chat.deepseek.com/share/xxxxx`）
3. 粘贴到下方输入框，点击「提取引用来源」
""")

link = st.text_input("🔗 粘贴 DeepSeek 分享链接", placeholder="https://chat.deepseek.com/share/...")

def extract_share_id(url):
    """从分享链接中提取ID"""
    match = re.search(r'share/([a-zA-Z0-9_]+)', url)
    return match.group(1) if match else None

def format_timestamp(timestamp):
    """将Unix时间戳转换为可读日期格式"""
    if not timestamp or timestamp == '未知' or timestamp == 0:
        return '未知'
    try:
        ts = int(timestamp)
        dt = datetime.fromtimestamp(ts)
        return dt.strftime('%Y-%m-%d')
    except:
        return '未知'

# ===== 新增：清理文件名的函数 =====
def clean_filename(text, max_length=50):
    """清理文件名中的特殊字符，并截取适当长度"""
    if not text:
        return "未知查询"
    
    # 替换特殊字符为下划线
    text = re.sub(r'[<>:"/\\|?*]', '_', text)
    # 去除首尾空格
    text = text.strip()
    # 限制长度
    if len(text) > max_length:
        text = text[:max_length]
    return text
# ===== 结束新增 =====

# ===== 新增品牌分析：品牌分析函数 =====
def analyze_brands(query, answer_text, citations_df):
    """调用DeepSeek API分析品牌能见度"""
    
    # 构建引用信息字符串
    citations_info = ""
    for _, row in citations_df.iterrows():
        citations_info += f"[{row['序号']}] {row['网站']} - {row['标题']}\n   URL: {row['URL']}\n\n"
    
    # 构建prompt，强调语义理解而非关键词匹配
    prompt = f"""
你是一个专业的品牌分析师。请仔细阅读用户问题和AI的回答，找出其中**真正作为讨论主体**的品牌。

【用户询问】
{query}

【AI回答】
{answer_text}

【引用来源】
{citations_info}

### 分析原则
1. **核心品牌**：是被介绍、对比、分析的产品/服务/公司实体（如"Smartly Brand Pulse"、"Dekuple BrandPulse"）
2. **排除对象**：平台名称（如Meta、Instagram）、案例客户（如三星）、技术术语，除非它们是分析主体
3. **表格优先**：如果回答中有表格，表格第一列通常是核心品牌

### 输出格式
请严格按以下Markdown表格格式输出：

| 品牌 | 出现位置 | 判断依据 | 关联引用 |
|------|---------|---------|---------|
| **品牌名称** | 具体位置描述 | 为什么它是核心品牌 | [citation标记] |

示例（基于你的分享链接）：
| 品牌 | 出现位置 | 判断依据 | 关联引用 |
|------|---------|---------|---------|
| **Smartly Brand Pulse** | 表格第1行 | 作为核心对比对象，有完整功能描述 | [1][2][6][9] |
| **Dekuple BrandPulse** | 表格第2行 | 同样作为核心对比对象，有完整功能描述 | [4] |

注意：
- 品牌名称加粗
- 只列出真正的品牌，不要列出平台名称或案例客户
- 如果没有找到品牌，输出"未发现核心品牌"
"""
    
    try:
        # 调用DeepSeek API
        client = openai.OpenAI(
            api_key=st.session_state.api_key,
            base_url="https://api.deepseek.com/v1"
        )
        
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "你是一个专业的品牌分析师，擅长从文本中识别真正的品牌实体，并能区分核心品牌和泛泛提及。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=4000
        )
        
        return response.choices[0].message.content
        
    except Exception as e:
        return f"品牌分析失败: {str(e)}"
# ===== 结束新增 =====

# 初始化session state来保存数据
if 'extracted_data' not in st.session_state:
    st.session_state.extracted_data = None
if 'citations' not in st.session_state:
    st.session_state.citations = []
if 'answer_text' not in st.session_state:
    st.session_state.answer_text = ""
if 'title' not in st.session_state:
    st.session_state.title = ""
# ===== 新增：保存询问词的session state =====
if 'query' not in st.session_state:
    st.session_state.query = ""
# ===== 结束新增 =====

# ===== 新增品牌分析：品牌分析相关session state =====
if 'brand_analysis' not in st.session_state:
    st.session_state.brand_analysis = None
if 'api_key' not in st.session_state:
    # 尝试从 Streamlit secrets 读取（云端）
    try:
        st.session_state.api_key = st.secrets.get("DEEPSEEK_API_KEY", "")
    except:
        # 如果失败（本地环境），就用空字符串，让用户在侧边栏输入
        st.session_state.api_key = ""
# ===== 结束新增 =====

# ===== 新增品牌分析：侧边栏API Key配置 + ICON =====
with st.sidebar:
    # ===== 修复图片显示 =====
    import os
    import base64
    
    icon_path = "blsicon.png"
    
    if os.path.exists(icon_path):
        # 读取图片并转换为 base64
        with open(icon_path, "rb") as f:
            img_data = base64.b64encode(f.read()).decode()
        
        # 使用 HTML img 标签，设置 alt 和 title（鼠标悬停显示）
        html_code = f'<img src="data:image/png;base64,{img_data}" width="120" alt="宝宝爆是俺拉" title="宝宝爆是俺拉">'
        st.markdown(html_code, unsafe_allow_html=True)

    else:
        # 如果路径不对，显示备选
        st.markdown("#### 🔍")
        st.caption(f"图片路径错误: {icon_path}")
    # ===== 结束修复 =====
    
    st.header("⚙️ 品牌分析配置")
    
    st.session_state.api_key = st.text_input(
        "DeepSeek API Key",
        type="password",
        value=st.session_state.api_key,
        help="需要调用DeepSeek API进行品牌分析，输入你充值的API Key"
    )
    st.markdown("---")
# ===== 结束新增 =====

if st.button("🚀 提取引用来源", type="primary", use_container_width=True):
    if not link:
        st.warning("请输入分享链接")
    else:
        share_id = extract_share_id(link)
        if not share_id:
            st.error("❌ 无法识别分享ID，请确认链接格式")
        else:
            with st.spinner("正在获取数据..."):
                try:
                    api_url = f"https://chat.deepseek.com/api/v0/share/content?share_id={share_id}"
                    
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                        'Accept': 'application/json',
                        'Referer': link
                    }
                    
                    response = requests.get(api_url, headers=headers, timeout=15)
                    
                    if response.status_code == 200:
                        data = response.json()
                        
                        with st.expander("📦 查看原始API返回数据"):
                            st.json(data)
                        
                        if data.get('code') == 0:
                            biz_data = data['data']['biz_data']
                            
                            # 保存到session state
                            st.session_state.title = biz_data.get('title', '')
                            st.session_state.answer_text = ""
                            st.session_state.citations = []
                            # ===== 新增：重置询问词 =====
                            st.session_state.query = ""
                            # ===== 结束新增 =====
                            # ===== 新增品牌分析：重置分析结果 =====
                            st.session_state.brand_analysis = None
                            # ===== 结束新增 =====
                            
                            for msg in biz_data['messages']:
                                # ===== 新增：提取用户询问词 =====
                                if msg['role'] == 'USER':
                                    for fragment in msg.get('fragments', []):
                                        if fragment.get('type') == 'REQUEST':
                                            st.session_state.query = fragment.get('content', '')
                                            break
                                # ===== 结束新增 =====
                                
                                if msg['role'] == 'ASSISTANT':
                                    for fragment in msg['fragments']:
                                        if fragment['type'] == 'RESPONSE':
                                            st.session_state.answer_text = fragment['content']
                                        elif fragment['type'] == 'SEARCH':
                                            for idx, result in enumerate(fragment.get('results', [])):
                                                raw_timestamp = result.get('published_at', '')
                                                st.session_state.citations.append({
                                                    '序号': idx + 1,
                                                    '网站': result.get('site_name', '未知'),
                                                    '标题': result.get('title', '无标题'),
                                                    'URL': result.get('url', '#'),
                                                    '发布时间': format_timestamp(raw_timestamp),
                                                    # ===== 新增：添加询问词到每条引用 =====
                                                    '询问词': st.session_state.query
                                                    # ===== 结束新增 =====
                                                })
                            
                            st.session_state.extracted_data = True
                            st.success("✅ 提取成功！")
                            
                        else:
                            st.error(f"API返回错误: {data.get('msg', '未知错误')}")
                    else:
                        st.error(f"API请求失败，状态码: {response.status_code}")
                        
                except Exception as e:
                    st.error(f"请求出错: {str(e)}")
                    st.exception(e)

# ========== 显示保存的数据（如果有）==========
if st.session_state.extracted_data:
    
    # ===== 删除：不显示 📌 Shared Conversation =====
    # st.subheader(f"📌 {st.session_state.title}")
    # ===== 结束删除 =====
    
    # ===== 新增：显示询问词 =====
    if st.session_state.query:
        st.markdown(f"**🔍 询问词**: {st.session_state.query}")
    # ===== 结束新增 =====
    
    # 第1部分：显示引用来源
    st.markdown("---")
    st.subheader(f"🔗 引用来源 (共找到 {len(st.session_state.citations)} 条详情)")
    
    if st.session_state.citations:
        # 创建HTML表格，完全避免滚动条
        html_table = "<table style='width:100%; border-collapse: collapse; margin-bottom: 20px;'>"
        html_table += "<tr style='background-color: #f0f2f6;'>"
        html_table += "<th style='padding: 12px; text-align: left; border: 1px solid #ddd; width:5%'>序号</th>"
        html_table += "<th style='padding: 12px; text-align: left; border: 1px solid #ddd; width:15%'>网站</th>"
        html_table += "<th style='padding: 12px; text-align: left; border: 1px solid #ddd; width:40%'>标题</th>"
        html_table += "<th style='padding: 12px; text-align: left; border: 1px solid #ddd; width:30%'>URL</th>"
        html_table += "<th style='padding: 12px; text-align: left; border: 1px solid #ddd; width:10%'>发布时间</th>"
        # ===== 新增：添加询问词列表头 =====
        html_table += "<th style='padding: 12px; text-align: left; border: 1px solid #ddd; width:10%'>询问词</th>"
        # ===== 结束新增 =====
        html_table += "</tr>"
        
        for item in st.session_state.citations:
            html_table += "<tr>"
            html_table += f"<td style='padding: 8px; border: 1px solid #ddd;'>{item['序号']}</td>"
            html_table += f"<td style='padding: 8px; border: 1px solid #ddd;'>{item['网站']}</td>"
            html_table += f"<td style='padding: 8px; border: 1px solid #ddd;'>{item['标题']}</td>"
            html_table += f"<td style='padding: 8px; border: 1px solid #ddd;'><a href='{item['URL']}' target='_blank' class='citation-link'>{item['URL'][:50]}{'...' if len(item['URL']) > 50 else ''}</a></td>"
            html_table += f"<td style='padding: 8px; border: 1px solid #ddd;'>{item['发布时间']}</td>"
            # ===== 新增：添加询问词单元格 =====
            html_table += f"<td style='padding: 8px; border: 1px solid #ddd;'>{item.get('询问词', '')}</td>"
            # ===== 结束新增 =====
            html_table += "</tr>"
        
        html_table += "</table>"
        
        st.markdown(html_table, unsafe_allow_html=True)
        
        # 下载按钮
        display_df = pd.DataFrame(st.session_state.citations)
        csv = display_df.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
        
        # ===== 新增：生成智能文件名 =====
        clean_query = clean_filename(st.session_state.query)
        filename = f"DeepSeek_{clean_query}.csv"
        # ===== 结束新增 =====
        
        col1, col2 = st.columns([1, 3])
        with col1:
            st.download_button(
                "📥 下载引用来源 CSV",
                csv,
                # ===== 修改：使用动态生成的文件名 =====
                filename,
                # ===== 结束修改 =====
                "text/csv",
                key="download_citations"
            )
        with col2:
            # ===== 修改：显示实际文件名 =====
            st.caption(f"文件名: {filename}")
            # ===== 结束修改 =====
            
    else:
        st.info("未找到引用来源详情")
    
    # 第2部分：显示AI回答
    st.markdown("---")
    st.subheader("📄 AI 回答")
    
    if st.session_state.answer_text:
        st.markdown(st.session_state.answer_text)
        refs = re.findall(r'\[citation:(\d+)\]', st.session_state.answer_text)
        if refs:
            st.caption(f"引用标记: {', '.join(set(refs))}")
        
        # ===== 新增品牌分析：分析按钮和结果显示 =====
        st.markdown("---")
        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            if st.button("🔍 分析品牌", type="primary", use_container_width=True):
                if not st.session_state.api_key:
                    st.error("请在左侧边栏配置DeepSeek API Key")
                else:
                    with st.spinner("AI正在分析品牌能见度..."):
                        # 创建DataFrame用于分析
                        analysis_df = pd.DataFrame(st.session_state.citations)
                        st.session_state.brand_analysis = analyze_brands(
                            st.session_state.query,
                            st.session_state.answer_text,
                            analysis_df
                        )
        
        # 显示分析结果
        if st.session_state.brand_analysis:
            st.markdown("---")
            st.subheader("📊 品牌分析报告")
            
            # 显示分析结果
            st.markdown(st.session_state.brand_analysis)
            
            # ===== 删除：不需要下载分析报告按钮 =====
            # ===== 结束删除 =====
        # ===== 结束新增 =====
        
    else:
        st.warning("未能提取回答内容")

# 底部说明
st.markdown("---")
# ===== 修改：更新底部说明 =====
st.caption("""
💡 **提示**：
1. 发布时间已自动转换为 `YYYY-MM-DD` 格式
2. 表格已设置为自动行，无需横向滚动
3. 新增「询问词」字段，显示用户的原始查询
4. CSV文件名自动生成为 `DeepSeek_询问词.csv`，已去除特殊字符
5. **新增品牌分析**：点击「🔍 分析品牌」按钮，AI会自动识别真正的品牌（排除平台名称和案例客户），分析出现位置、判断依据和关联引用
6. 品牌分析需要使用DeepSeep API（需在左侧边栏配置有效API Key）
7. 点击下载按钮后，页面数据会保留，可以继续浏览
8. 如需提取新的链接，重新输入并点击「提取引用来源」即可
""")

# ===== 结束修改 =====

