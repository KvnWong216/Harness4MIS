from __future__ import annotations

import html
from html.parser import HTMLParser
import ipaddress
import math
import re
import socket
from urllib.request import Request, urlopen, build_opener, HTTPRedirectHandler
from urllib.parse import urlsplit

BANNED = ['证据', '验收', '尚未', '哈希', '交付物清单', '审计轨迹', '可追溯链', '版本指纹', '已通过全部检查']


def norm(text):
    return re.sub(r'\s+', '', html.unescape(text)).lower()


class Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.bits, self.ignore = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.ignore += 1

    def handle_endtag(self, tag):
        if tag in ('script', 'style') and self.ignore:
            self.ignore -= 1

    def handle_data(self, data):
        if not self.ignore:
            self.bits.append(data)


def public_url(url):
    parts = urlsplit(url)
    if parts.scheme not in ('https', 'http') or not parts.hostname or parts.username or parts.password:
        raise ValueError('来源地址无效')
    for item in socket.getaddrinfo(parts.hostname, parts.port or (443 if parts.scheme == 'https' else 80)):
        if not ipaddress.ip_address(item[4][0]).is_global:
            raise ValueError('来源地址不能指向本机或内网')


class SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url):
    public_url(url)
    req = Request(url, headers={'User-Agent': 'MIS303-Research/2.0'})
    with build_opener(SafeRedirect()).open(req, timeout=25) as response:
        data = response.read(5_000_001)
        if len(data) > 5_000_000:
            raise ValueError('网页过大，请作为材料上传')
        if 'pdf' in response.headers.get('Content-Type', '') or data.startswith(b'%PDF'):
            from pypdf import PdfReader
            import io
            return '\n'.join(p.extract_text() or '' for p in PdfReader(io.BytesIO(data)).pages)
        text = data.decode(response.headers.get_content_charset() or 'utf-8', errors='replace')
    parser = Text()
    parser.feed(text)
    return ' '.join(parser.bits)


def body(answer):
    return '\n'.join([answer['answer'], *answer['paragraphs']] +
                     [v for t in answer['tables'] for v in [t['caption'], *t['columns'],
                      *[x for row in t['rows'] for x in row]]])


def style_errors(text):
    return ['正文含需改写的措辞：' + word for word in BANNED if word in text]


def check_answer(answer, question, chunks, web_cache, external=True):
    errors = []
    if answer['question_id'] != question['id']:
        errors.append('题号发生变化')
    if not answer['answer'].strip() or not answer['paragraphs']:
        errors.append('缺少直接回答或分析')
    errors += style_errors(body(answer))
    refs = answer['references']
    if len({r['id'] for r in refs}) != len(refs):
        errors.append('引用编号重复')
    sources = {c['id']: c['text'] for c in chunks}
    good_refs = set()
    for r in refs:
        passage = ''
        if r['source_id']:
            passage = sources.get(r['source_id'], '')
        elif r['url'] and external:
            if r['url'] not in web_cache:
                try:
                    web_cache[r['url']] = {'text': fetch(r['url']), 'error': ''}
                except Exception:
                    web_cache[r['url']] = {'text': '', 'error': '网页未能读取'}
            passage = web_cache[r['url']]['text']
        quote = norm(r['excerpt'])
        if len(quote) < 12 or quote not in norm(passage):
            errors.append('引用 ' + r['id'] + ' 的原文片段无法在实际资料中找到；请重新读取、补充材料或删除对应论断')
        else:
            good_refs.add(r['id'])
        if not r['citation'].strip():
            errors.append('引用 ' + r['id'] + ' 缺少书目信息')
    for c in answer['claims']:
        if c['kind'] in ('fact', 'theory') and not c['reference_ids']:
            errors.append('事实或命名理论需要出处：' + c['text'][:90])
        if not set(c['reference_ids']).issubset(good_refs):
            errors.append('论断使用了无法核对的引用：' + c['text'][:90])
        if c['kind'] in ('inference', 'logic') and not c['rationale'].strip():
            errors.append('推导需要交代前提：' + c['text'][:90])
    if not answer['claims']:
        errors.append('请列明主要论断及其依据类别，供本轮内部核对')
    for table in answer['tables']:
        if not table['columns'] or any(len(row) != len(table['columns']) for row in table['rows']):
            errors.append('表格行列不一致')
    return errors


def numbers(text):
    return set(re.findall(r'(?<![\w])\d+(?:[.,]\d+)*(?:%|％)?', text))


def check_slides(slides, questions, answers):
    errors = []
    ids = {q['id'] for q in questions}
    covered = {qid for s in slides for qid in s['question_ids']}
    if covered != ids:
        errors.append('幻灯片没有逐项覆盖原题，或引入了其他题号')
    valid_refs = {r['id'] for a in answers for r in a['references']}
    available = numbers('\n'.join(body(a) + json_refs(a) for a in answers) + '\n'.join(q['text'] for q in questions))
    for s in slides:
        errors += style_errors(s['title'] + '\n' + '\n'.join(s['points']) + s['notes'])
        if not s['points'] or len(s['points']) > 6 or any(len(p) > 160 for p in s['points']):
            errors.append('页面文字过多或为空，请拆页或缩写')
        height = sum(max(54, math.ceil(sum(1 if ord(c)>255 else .52 for c in p)/38)*36+18)+10 for p in s['points'])
        if height > 494 or len(s['title']) > 48:
            errors.append('页面文字超过可读排版范围，请精简或拆页')
        if not set(s['reference_ids']).issubset(valid_refs):
            errors.append('幻灯片引入了报告外的引用')
        extra = numbers(' '.join([s['title'], *s['points'], s['notes']])) - available
        if extra:
            errors.append('幻灯片引入了报告外的数字：' + ', '.join(sorted(extra)))
    return errors


def json_refs(answer):
    return '\n'.join(r['citation'] for r in answer['references'])


def count_words(text, language='zh'):
    if language.lower().startswith(('en', '英')):
        return len(re.findall(r"\b[\w'-]+\b", text))
    return len(re.findall(r'[\u4e00-\u9fff]|[a-zA-Z0-9]+', text))


def time_classification(minutes):
    if minutes > 600:
        return 'failure，低于 60%'
    if minutes < 180:
        return '时间条件符合至少 above average+、90 分的文字规则；最终评分由老师确定'
    return '此时间区间的评分关系需按老师补充口径处理'
