import json

"""Non-scored live tool diagnostic; does not alter graded benchmark tasks."""
def build_non_scored_tool_probe(task):
    """An isolated diagnostic conversation; never included in benchmark predictions or scoring."""
    return {
        **task,
        'id': 'scibench_000000',
        'messages': [dict(task['messages'][0]), {
            'role': 'user',
            'content': (
                'NON-SCORED ENVIRONMENT CONNECTIVITY TEST. '
                'Use the available scientific_shell tool to execute this exact command: '
                'python -c "import numpy, scipy, pandas, networkx, rdkit; '
                'from openbabel import openbabel; print(\'SCIBENCH_TOOL_READY\')". '
                'Check the actual tool result and reply with only SCIBENCH_TOOL_READY. '
                'Do not simulate a tool result or answer without calling the tool.'
            ),
        }],
    }



def verified_scientific_tool_call(call):
    """Verify marker came from successful isolated shell stdout, not from assistant text."""
    if call.get('tool')!='scientific_shell':
        return False
    try:
        obj=json.loads(call.get('output') or '')
    except (ValueError, TypeError):
        return False
    return (isinstance(obj,dict) and obj.get('status')=='ok' and obj.get('exit_code')==0
            and 'SCIBENCH_TOOL_READY' in obj.get('output',''))
