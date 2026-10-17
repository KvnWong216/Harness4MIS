S = {'type': 'string'}
B = {'type': 'boolean'}
I = {'type': 'integer'}


def array(item):
    return {'type': 'array', 'items': item}


def obj(**fields):
    return {'type': 'object', 'properties': fields, 'required': list(fields), 'additionalProperties': False}


QUESTION = obj(id=S, text=S)
OCR = obj(title=S, problem_statement=S, questions=array(QUESTION), unclear=array(S),
          language=S, word_min=I, word_max=I, slide_count=I)
SOURCE_OCR = obj(transcript=S, unclear=array(S))
TABLE = obj(caption=S, columns=array(S), rows=array(array(S)))
REFERENCE = obj(id=S, citation=S, url=S, source_id=S, locator=S, excerpt=S)
CLAIM = obj(text=S, kind={'type': 'string', 'enum': ['fact', 'theory', 'inference', 'logic']},
            reference_ids=array(S), rationale=S)
ANSWER = obj(question_id=S, answer=S, paragraphs=array(S), tables=array(TABLE),
             references=array(REFERENCE), claims=array(CLAIM))
REVISION = obj(answer=ANSWER, changes=array(obj(issue=S, change=S)), blockers=array(S))
OVERVIEW = obj(title=S, summary=S, methods=S, lessons=array(S))
SLIDE = obj(title=S, points=array(S), notes=S, question_ids=array(S), reference_ids=array(S))
SLIDES = obj(slides=array(SLIDE))
VISUAL = obj(acceptable=B, issues=array(S))


def check(value, schema, at='$'):
    """Strict validation of the schema subset used by both model providers."""
    t = schema['type']
    valid = {'object': isinstance(value, dict), 'array': isinstance(value, list),
             'string': isinstance(value, str), 'integer': type(value) is int,
             'boolean': type(value) is bool}[t]
    if not valid:
        raise ValueError(f'{at}: expected {t}')
    if 'enum' in schema and value not in schema['enum']:
        raise ValueError(f'{at}: value outside allowed choices')
    if t == 'object':
        if set(value) != set(schema['required']):
            raise ValueError(f'{at}: 字段不完整或包含多余字段')
        for key, spec in schema['properties'].items():
            check(value[key], spec, at + '.' + key)
    if t == 'array':
        for n, item in enumerate(value):
            check(item, schema['items'], f'{at}[{n}]')
