"""Roadshow composition shared by all exports, with optional case visuals."""
from collections import Counter
from pathlib import Path
from .common import ROOT

THEME = {'paper': '#F3F0E8', 'ink': '#142C3C', 'dark': '#102B3B',
         'accent': '#BE8C60', 'muted': '#536871', 'pale': '#E0E6E4'}
REFERENCE = 'https://pitch.com/templates/10-Slide-Pitch-Deck-0dh4WE6siodH4gWAjk0og4tB'

def make_design(slides, visuals=()):
    """Add visual pacing without replacing the final report's claims or numbers."""
    background = str(ROOT / 'assets/research.png')
    visuals = [str(Path(p).resolve()) for p in visuals]
    result = []
    content_index = 0
    for i, raw in enumerate(slides):
        c = dict(raw)
        if c.get('kind') == 'cover':
            c.update(layout='hero', image=visuals[0] if visuals else background,
                     kicker='MIS303', byline=c.get('text', ''), subtitle='研究问题、分析与管理建议')
        elif c.get('kind') == 'table':
            c['layout'] = 'table'
        elif c.get('kind') == 'text':
            c['layout'] = 'text'
        else:
            # Keep points as native editable text, with varied compositions.
            layout = ['points', 'dark-points', 'split'][content_index % 3]
            content_index += 1
            if layout == 'split' and len(c.get('points', [])) >= 2:
                middle = (len(c['points']) + 1) // 2
                c.update(layout='split', before='\n'.join(c['points'][:middle]),
                         after='\n'.join(c['points'][middle:]), takeaway='')
            else:
                c['layout'] = layout if layout != 'split' else 'points'
        result.append(c)
    return {'theme': dict(THEME), 'reference': REFERENCE, 'slides': result,
            'assetDescriptions': {background: 'AI生成的研究桌面插图，作为通用背景'}}


def design_issues(spec):
    """Check structural design, not a subjective claim that a deck is beautiful."""
    slides = spec['slides']
    layouts = [s.get('layout', '') for s in slides]
    issues = []
    if len(slides) >= 6 and len(set(layouts)) < 3:
        issues.append('至少使用三种适合内容的版式。')
    for i in range(len(slides)-2):
        if layouts[i] == layouts[i+1] == layouts[i+2] and layouts[i] not in ('text',):
            issues.append('连续三页采用相同版式，请调整叙事节奏。')
            break
    if len(slides) >= 6 and not any(s.get('image') for s in slides):
        issues.append('需要适合作业主题的插图或背景。')
    for i, slide in enumerate(slides):
        if slide.get('layout') in ('points', 'dark-points'):
            visible = sum(len(x) for x in slide.get('points', []))
            if visible > 200:
                issues.append(f'第{i+1}页的屏幕文字过多，请将解释放入备注或拆页。')
        if slide.get('columns') and any(len(row) != len(slide['columns']) for row in slide['rows']):
            issues.append(f'第{i+1}页表格列数不一致。')
    return issues
