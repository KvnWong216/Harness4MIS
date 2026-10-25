"""Select a concise, task-specific business writing guide from the shared policy."""
from __future__ import annotations
import re
from .common import ROOT,read_json

BUSINESS = re.compile(r'商业模式|business model|(?<![A-Za-z0-9_])BMC(?![A-Za-z0-9_])|经营|管理实践|企业概况|公司简介|痛点|价值主张|战略.*(?:弱点|建议)|(?:公司|企业).*(?:分析|问题|解决)', re.I)
COMPREHENSIVE = re.compile(r'综合报告|分析报告|professional.*report|business model.*report|公司简介|企业概况', re.I)

def case_guidance(question_text):
    """This is a writing heuristic; the question still determines theory and content."""
    if not BUSINESS.search(question_text):
        return {}
    policy = read_json(ROOT / 'policies/case_writing.json')
    full = bool(COMPREHENSIVE.search(question_text))
    if full:
        route = policy['body_organization']
    else:
        route = [
            {'part':'直接回应本题','purpose':'先说明判断与当前问题的关系'},
            {'part':'经营机制与具体情景','purpose':'解释原因、后果及相关环节的相互影响'},
            {'part':'相配的管理选择','purpose':'根据本题需要说明行动、代价与经营含义'}]
    named = []
    if re.search(r'(?<![A-Za-z0-9_])BMC(?![A-Za-z0-9_])|商业模式画布', question_text, re.I): named.append('BMC')
    if re.search(r'(?<![A-Za-z0-9_])PIS(?![A-Za-z0-9_])', question_text, re.I): named.append('PIS')
    return {
        'kind':'comprehensive_business_case' if full else 'focused_business_answer',
        'body_route':route,
        'question_named_frameworks':named,
        'argument_focus':policy['argument_constraints'],
        'paragraph_focus':policy['paragraph_constraints'],
        'visual_focus':policy['visual_constraints'],
        'application':'以下是经营分析的组织建议，按本题重点调整。原题、资料和引用要求继续优先。'}
