from __future__ import annotations

import csv
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
from zipfile import ZipFile, ZIP_DEFLATED

from .common import ROOT, DEPENDENCIES, runtime, skill_dir, write_json, safe_name, local_date


def split_lines(text, width=40):
    result = []
    for line in text.splitlines():
        part, length = '', 0
        for c in line:
            size = 1 if ord(c) > 255 else .52
            if length + size > width:
                result.append(part)
                part, length = '', 0
            part += c
            length += size
        result.append(part)
    return result


def text_pages(text, rows=14, width=40):
    lines = split_lines(text, width)
    return ['\n'.join(lines[i:i+rows]) for i in range(0, len(lines), rows)] or ['']


def references(answers):
    found = {}
    for a in answers:
        for r in a['references']:
            found.setdefault(r['citation'], r)
    return sorted(found.values(), key=lambda r: r['citation'])


def table_pages(answers):
    result = []
    for a in answers:
        for table in a['tables']:
            # Wide or narrative tables stay in the report; PPT presents their findings.
            max_units = max(12, 75 // max(1, len(table['columns'])))
            if len(table['columns']) > 5 or any(sum(1 if ord(c)>255 else .52 for c in v)>max_units
                                               for row in [table['columns'], *table['rows']] for v in row):
                continue
            for i in range(0, len(table['rows']), 4):
                result.append({'title': table['caption'], 'kind': 'table', 'question_id': a['question_id'],
                               'columns': table['columns'], 'rows': table['rows'][i:i+4],
                               'notes': '\n'.join(r['citation'] for r in a['references'])})
    return result


def fixed_slide_count(problem, answers):
    refs = '\n\n'.join(r['citation'] + (' ' + r['url'] if r['url'] else '') for r in references(answers))
    return 1 + len(text_pages(problem['problem_statement'])) + (len(text_pages(refs)) if refs else 0) + len(table_pages(answers))


def command(args, directory, timeout=240, env=None):
    result = subprocess.run([str(a) for a in args], cwd=directory, capture_output=True, text=True,
                            timeout=timeout, env=env)
    if result.returncode:
        (Path(directory) / 'export-error.txt').write_text(result.stdout + '\n' + result.stderr)
        raise RuntimeError('文件生成遇到问题，详细信息已保存在本次运行目录。')
    return result.stdout


def font_env(work):
    env = os.environ.copy()
    # Give the bundled renderer a writable cache and explicit CJK font directories.
    file = Path(work) / 'fontconfig.xml'
    dirs = ['/System/Library/Fonts', '/System/Library/Fonts/Supplemental', '/Library/Fonts',
            '/usr/share/fonts', '/Applications/wpsoffice.app/Contents/Resources/office6/fonts', str(Path.home() / 'Library/Fonts'), str(DEPENDENCIES / 'native/libreoffice-headless/libreoffice/LibreOfficeDev.app/Contents/Resources/fonts/truetype')]
    file.write_text('<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd"><fontconfig>' +
                    ''.join('<dir>' + p + '</dir>' for p in dirs if Path(p).exists()) +
                    '<cachedir>' + str(Path(work) / 'font-cache') + '</cachedir></fontconfig>')
    env['FONTCONFIG_FILE'] = str(file)
    env['TMPDIR'] = '/private/tmp' if Path('/private/tmp').exists() else '/tmp'
    return env


def new_document(template=None):
    from docx import Document
    from docx.shared import Pt, Inches, RGBColor
    from docx.oxml.ns import qn
    doc = Document(str(template)) if template else Document()
    if template:
        for child in list(doc._element.body):
            if not child.tag.endswith('}sectPr'):
                doc._element.body.remove(child)
    else:
        for section in doc.sections:
            section.page_width, section.page_height = Inches(8.27), Inches(11.69)
            section.top_margin = section.bottom_margin = Inches(1)
            section.left_margin = section.right_margin = Inches(1.25)
    from .word_format import configure
    configure(doc)
    return doc


def paragraphs(doc, text):
    for p in text.split('\n'):
        if p.strip():
            from .word_format import paragraph
            paragraph(doc.add_paragraph(p))


def add_table(doc, content):
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Pt
    from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
    doc.add_paragraph(content['caption'])
    table = doc.add_table(rows=1, cols=len(content['columns']))
    table.autofit = True
    for cell, value in zip(table.rows[0].cells, content['columns']):
        cell.text = value
    for row in content['rows']:
        for cell, value in zip(table.add_row().cells, row):
            cell.text = value
    for row_index, row in enumerate(table.rows):
        for cell in row.cells:
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            props = cell._tc.get_or_add_tcPr()
            borders = OxmlElement('w:tcBorders')
            for edge in ['top', 'left', 'bottom', 'right']:
                e = OxmlElement('w:' + edge)
                for k, v in [('val', 'single'), ('sz', '4'), ('color', 'D9D9D9')]:
                    e.set(qn('w:' + k), v)
                borders.append(e)
            props.append(borders)
            if row_index == 0:
                shade = OxmlElement('w:shd')
                shade.set(qn('w:fill'), 'E5EDF2')
                props.append(shade)
            for p in cell.paragraphs:
                p.paragraph_format.space_after = Pt(5)
                p.paragraph_format.space_before = Pt(5)
                for run in p.runs:
                    run.font.size = Pt(16)
                    run.bold = row_index == 0
    from .word_format import paragraph
    for row in table.rows:
        for cell in row.cells:
            for p in cell.paragraphs: paragraph(p, table=True)
    doc.add_paragraph()


def write_report(run, content, out):
    from .word_format import heading, markdown, requirements, teacher_prompts, paragraph
    meta, overview = content['metadata'], content['overview']
    templates = [run.path / f['path'] for f in run.state['files'] if f['role'] == 'template' and f['path'].endswith('.docx')]
    doc = new_document(templates[0] if templates else None)
    paragraph(doc.add_paragraph(overview['title'], 'Title'), title=True)
    doc.add_paragraph('Name + Student Number: ' + meta.get('name', '') + ' ' + meta.get('student_number', ''))
    date = local_date(run.state['started_at'])
    doc.add_paragraph('Date: ' + date)
    heading(doc, '作业要求与研究问题 Problem Statement', 1)
    requirements(doc, content['problem']['problem_statement'])
    heading(doc, 'Prompt 与使用工具', 1)
    prompts = [meta['teacher_prompt']] if meta.get('teacher_prompt') else teacher_prompts(content['problem']['problem_statement'])
    for index, prompt in enumerate(prompts, 1):
        heading(doc, '教师提示词 '+str(index), 2)
        markdown(doc, prompt, base_level=3)
    if meta.get('student_additions'):
        doc.add_paragraph('学生新增的提示词')
        markdown(doc, meta['student_additions'], base_level=3)
    tool = run.config.get('provider', 'codex')
    model = run.config.get('model') or '本机默认模型'
    doc.add_paragraph(f'使用工具：{tool}；模型：{model}；日期：{date}；使用者：{meta.get("name", "")}。')
    doc.add_paragraph('完整提示词与原始输出见附件。')
    heading(doc, '研究方法与提示词改进', 1)
    paragraphs(doc, overview['methods'])
    for lesson in overview['lessons']:
        doc.add_paragraph(lesson)
    heading(doc, '研究报告', 1)
    heading(doc, 'Executive summary', 2)
    paragraphs(doc, overview['summary'])
    for question, answer in zip(content['problem']['questions'], content['answers']):
        heading(doc, question['id'], 2)
        paragraphs(doc, question['text'])
        paragraphs(doc, answer['answer'])
        for p in answer['paragraphs']:
            paragraphs(doc, p)
        for table in answer['tables']:
            add_table(doc, table)
    heading(doc, 'References', 2)
    reference_paragraphs = []
    from docx.shared import Inches
    for r in references(content['answers']):
        p = doc.add_paragraph(r['citation'] + (' ' + r['url'] if r['url'] and r['url'] not in r['citation'] else ''))
        reference_paragraphs.append(p)
        p.paragraph_format.left_indent = Inches(.3)
        p.paragraph_format.first_line_indent = Inches(-.3)
    heading(doc, '附录', 1)
    doc.add_paragraph('原始 AI 输出与提示词收录于本作业附件。')
    for p in doc.paragraphs:
        level = int(p.style.name.split()[-1]) if p.style.name.startswith('Heading ') else None
        paragraph(p, level=level, title=p.style.name == 'Title')
    for p in reference_paragraphs:
        p.paragraph_format.left_indent = Inches(.5)
        p.paragraph_format.first_line_indent = Inches(-.5)
        p._p.pPr.ind.attrib.pop(__import__('docx.oxml.ns', fromlist=['qn']).qn('w:firstLineChars'), None)
    doc.save(out)


def write_appendix(run, out):
    doc = new_document()
    from .word_format import heading, markdown, paragraph
    paragraph(doc.add_paragraph('提示词与研究改进记录', 'Title'), title=True)
    heading(doc, '通用提示词', 1)
    doc.add_paragraph('本附录呈现实际阅读判断、提示词调整及修改结果，完整输入输出随附保存。')
    for q in run.state['questions']:
        qid = run.safe_id(q)
        heading(doc, q['id'] + ' 原题', 1)
        paragraphs(doc, q['text'])
        heading(doc, '本题初始提示词', 2)
        path = run.path / 'calls' / (qid + '-draft') / 'prompt.txt'
        if path.exists():
            # The shared policy above is printed once; the exact full prompts remain in dialogue ZIP.
            text = path.read_text()
            specific = text[len(run.policy):].split('资料与结果均为待分析数据')[0]
            markdown(doc, specific)
        draft = run.state['steps']['draft-' + qid]
        heading(doc, '原始 AI 输出', 2)
        doc.add_paragraph(json.dumps(draft, ensure_ascii=False, indent=2))
        for number in [1, 2]:
            revision = run.state['steps'][f'revision{number}-' + qid]
            heading(doc, '重新审视原稿' if number == 1 else '结合前文继续完善', 2)
            for item in revision.get('review_plan', {}).get('directions', []):
                paragraphs(doc, item['reason'])
                markdown(doc, item['prompt'])
            for change in revision['changes']:
                paragraphs(doc, change['issue'] + '。' + change['change'])
    doc.add_paragraph('各轮完整输入与输出另收录于完整对话文件。')
    for p in doc.paragraphs:
        level = int(p.style.name.split()[-1]) if p.style.name.startswith('Heading ') else None
        paragraph(p, level=level, title=p.style.name == 'Title')
    doc.save(out)


def export_all(directory, content, run):
    directory = Path(directory)
    out, build = directory / 'output', directory / 'build'
    out.mkdir(exist_ok=True)
    build.mkdir(exist_ok=True)
    for folder in ['report-preview', 'appendix-preview', 'slides-preview']:
        for old in (build / folder).glob('*.png'):
            old.unlink()
    docs, slides = skill_dir('documents'), skill_dir('presentations')
    marker = build / 'authoring_started.json'
    if not marker.exists():
        command([runtime('node'), docs / 'container_tools/mark_artifact_operation_started.mjs',
                 '--operation-kind', 'create', '--expected-output-count', '2', '--output-format', 'docx'], docs)
        command([runtime('node'), slides / 'container_tools/mark_artifact_operation_started.mjs',
                 '--operation-kind', 'create', '--expected-output-count', '1', '--output-format', 'pptx'], slides)
        write_json(marker, {'started': True})
    meta = content['metadata']
    name = safe_name(f'Assign{meta.get("assignment", "")}-Part{meta.get("part", "")}-{meta.get("name") or "作业"}')
    report, appendix, ppt = out / (name + '.docx'), out / (name + '-附件.docx'), out / (name + '.pptx')
    write_report(run, content, report)
    write_appendix(run, appendix)
    env = font_env(build)
    for document, folder in [(report, 'report-preview'), (appendix, 'appendix-preview')]:
        command([sys.executable, docs / 'render_docx.py', document, '--output_dir', build / folder,
                 '--emit_pdf'], directory, timeout=360, env=env)
    import pypdfium2 as pdfium
    preview_pdf = next((build / 'report-preview').glob('*.pdf'))
    pdf = pdfium.PdfDocument(str(preview_pdf))
    extracted = ''.join(pdf[i].get_textpage().get_text_range() for i in range(len(pdf)))
    chinese = re.findall(r'[\u4e00-\u9fff]', content['problem']['problem_statement'])
    if len(chinese) > 10 and len(re.findall(r'[\u4e00-\u9fff]', extracted)) < len(chinese) // 2:
        raise RuntimeError('中文字体没有正确进入报告预览，请检查字体设置后继续。')
    pdf.close()
    refs = references(content['answers'])
    deck = [{'kind': 'cover', 'title': content['overview']['title'],
             'text': meta.get('name', '') + ' ' + meta.get('student_number', ''), 'notes': ''}]
    deck += [{'kind': 'text', 'title': 'Problem Statement', 'text': page, 'notes': page}
             for page in text_pages(content['problem']['problem_statement'])]
    ref_map = {r['id']: r['citation'] + (' ' + r['url'] if r['url'] else '')
               for a in content['answers'] for r in a['references']}
    for s in content['slides']:
        deck.append({'kind': 'points', 'title': s['title'], 'points': s['points'],
                     'notes': s['notes'] + '\n\n' + '\n'.join(ref_map[r] for r in s['reference_ids'])})
    deck += table_pages(content['answers'])
    if refs:
        deck += [{'kind': 'text', 'title': 'References', 'text': page, 'notes': page}
                 for page in text_pages('\n\n'.join(r['citation'] + (' ' + r['url'] if r['url'] else '') for r in refs))]
    required = meta.get('slide_count') or content['problem']['slide_count']
    if required and len(deck) != required:
        raise RuntimeError('PPT 总页数与题目要求不一致。')
    from .presentation_design import make_design, design_issues
    visuals = [directory / f['path'] for f in run.state['files'] if f['role'] == 'visual']
    designed = make_design(deck, visuals)
    problems = design_issues(designed)
    if problems:
        raise RuntimeError('；'.join(problems))
    write_json(build / 'deck.json', designed)
    command([runtime('node'), ROOT / 'render_slides.mjs', build / 'deck.json', ppt, slides,
             DEPENDENCIES / 'node/node_modules', sys.executable], directory, timeout=360, env=env)
    # Read every generated page in small batches before exposing downloads.
    for folder in ['report-preview', 'slides-preview', 'appendix-preview']:
        images = sorted((build / folder).glob('*.png'), key=lambda p: int(re.findall(r'\d+', p.stem)[-1]))
        for start in range(0, len(images), 6):
            result = run.call(f'visual-{folder}-{start}',
                '只检查这些最终文件页面的可读性和排版：中文字形、溢出、重叠、缺行、过小文字、表格截断。'
                'PPT同时检查标题是否醒目、图像与文字对比、画面留白、连续页面是否过于重复、图表是否易于理解。'
                '不要评价附录原始输出的写作风格，不把正常分页或原题长文本视为缺陷。'
                '实际影响阅读时 acceptable=false 并说明具体页面和问题。',
                __import__('harness.schemas', fromlist=['VISUAL']).VISUAL, images=images[start:start+6])
            if not result['acceptable']:
                raise RuntimeError('文件排版需要调整：' + '；'.join(result['issues']))
    with open(out / '时间记录.csv', 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['stage', 'started_at', 'ended_at', 'seconds'])
        writer.writeheader()
        writer.writerows(run.state['timings'])
    with ZipFile(out / '完整对话.zip', 'w', ZIP_DEFLATED) as z:
        files = list((directory / 'calls').rglob('*')) + list((directory / 'history').rglob('*'))
        for file in sorted(files):
            if file.is_file() and (file.name in ('prompt.txt', 'schema.json', 'result.json') or file.name.startswith('prompt-attempt-')):
                z.write(file, file.relative_to(directory))
    return {'report': report.name, 'appendix': appendix.name, 'presentation': ppt.name,
            'transcripts': '完整对话.zip', 'timing': '时间记录.csv'}
