"""Opt-in real-model test; writes only to tests/work and uses current CLI login."""
from pathlib import Path
import argparse
import json
import sys
import uuid

from PIL import Image, ImageDraw, ImageFont
from harness.common import ROOT, now, write_json, read_json
from harness.engine import Runner
from harness.provider import Provider
from harness import schemas


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--full',action='store_true')
    parser.add_argument('--resume',default='')
    args=parser.parse_args()
    if args.resume and (len(args.resume)!=32 or any(c not in '0123456789abcdef' for c in args.resume)):
        raise ValueError('Invalid test run id')
    path=ROOT/'tests/work'/(args.resume or uuid.uuid4().hex)
    if args.resume:
        runner=Runner(path)
        runner.execute()
        state=read_json(path/'state.json')
        print(json.dumps({'status':state['status'],'stage':state['stage'],'error':state.get('error'),
                         'questions':state.get('questions_for_user'),'time':state.get('time')},ensure_ascii=False),flush=True)
        if state['status']!='completed':sys.exit(1)
        return
    path.mkdir(parents=True)
    if not args.full:
        provider=Provider({'provider':'codex','call_timeout':180},path/'calls')
        result=provider.call('connection','返回 status 为 ok，不运行任何工具或命令。',schemas.obj(status=schemas.S))
        print(json.dumps(result,ensure_ascii=False),flush=True)
        return
    image=Image.new('RGB',(1450,650),'white')
    draw=ImageDraw.Draw(image)
    font=ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial Unicode.ttf',38)
    lines=['运行测试','1. 某商品每件成本为20元，售价为30元。',
           '只考虑这两项，出售10件的毛利是多少？请写出计算。',
           '要求：报告使用中文。正文不设字数与PPT页数限制。']
    for n,line in enumerate(lines):draw.text((65,65+n*95),line,font=font,fill='black')
    image.save(path/'question.png')
    write_json(path/'state.json',{'id':path.name,'started_at':now(),'status':'queued',
        'config':{'provider':'codex','web_search':False,'call_timeout':600},
        'metadata':{'name':'运行测试','assignment':'TEST','part':'1'},
        'files':[{'name':'question.png','path':'question.png','role':'question'}],
        'steps':{},'events':[],'timings':[],'feedback':'','model_calls':[],'answers':[],'questions':[]})
    print('RUN_DIRECTORY='+str(path),flush=True)
    runner=Runner(path)
    runner.execute()
    state=read_json(path/'state.json')
    print(json.dumps({'status':state['status'],'stage':state['stage'],'error':state.get('error'),
                      'questions':state.get('questions_for_user'),'time':state.get('time')},ensure_ascii=False),flush=True)
    if state['status']!='completed':sys.exit(1)


if __name__=='__main__':main()
