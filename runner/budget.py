"""Uniform, trusted runtime controls; never part of the frozen task prompt."""
import copy

SOFT_NOTICE = 'You are approaching the execution budget. Stop further exploration unless essential and provide your best final answer as soon as possible.'
HARD_NOTICE = 'The execution budget has been reached. Do not call any more tools. Return your best final answer now.'

class Budget:
    def __init__(self, runtime):
        self.runtime = runtime
        self.agent_calls = 0
        self.finalization_calls = 0
        self.soft_anchor = None
        self.hard_anchor = None
        self.tool_calls = 0
        self.finalization_status = 'not_needed'

    def prepare(self, body):
        # Input has already been canonicalized to the frozen pair + valid continuation.
        continuation = body['messages'][2:]
        self.tool_calls = sum(len(m.get('tool_calls') or []) for m in continuation if m['role']=='assistant')
        hard = self.agent_calls >= self.runtime.get('hard_model_calls', self.runtime['max_model_calls']) or self.tool_calls >= self.runtime.get('hard_tool_calls', self.runtime['max_tool_calls'])
        if self.finalization_calls:
            raise ValueError('Forced finalization already executed')
        if self.soft_anchor is None and (self.agent_calls >= self.runtime.get('soft_model_calls',18) or self.tool_calls >= self.runtime.get('soft_tool_calls',20)):
            self.soft_anchor = len(continuation)
        result = copy.deepcopy(body)
        notices = []
        if self.soft_anchor is not None:
            notices.append((min(self.soft_anchor,len(continuation)), SOFT_NOTICE))
        if hard:
            self.hard_anchor = len(continuation)
            self.finalization_calls = 1
            self.finalization_status = 'pending'
            notices.append((self.hard_anchor, HARD_NOTICE))
            result['tools'] = []
            result['tool_choice'] = 'none'
            result.pop('parallel_tool_calls',None)
        else:
            self.agent_calls += 1
        tail = copy.deepcopy(continuation)
        # Historical notice appears once at its original boundary, never as an
        # additional fresh notice every round. All incoming user roles were removed.
        for anchor, text in reversed(notices):
            tail.insert(anchor, {'role':'user','content':text})
        result['messages'] = copy.deepcopy(body['messages'][:2]) + tail
        return result, hard

    def summary(self):
        return {'soft_budget_triggered':self.soft_anchor is not None,
                'forced_finalization_triggered':bool(self.finalization_calls),
                'agent_model_calls':self.agent_calls,
                'forced_finalization_calls':self.finalization_calls,
                'tool_calls':self.tool_calls, 'finalization_status':self.finalization_status}
