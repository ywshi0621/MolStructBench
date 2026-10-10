"""Never write raw event streams, reasoning parts, or intermediate assistant text."""
class Collector:
    def __init__(self):
        self.texts = {}
        self.finishes = {}
        self.tools = {}
        self.errors = 0
        self.tokens = {'input':0,'output':0,'reasoning':0,'cache_read':0,'cache_write':0}
        self.steps = set()
    def accept(self, event):
        typ, part = event.get('type'), event.get('part', {})
        mid = part.get('messageID')
        if typ == 'text':
            self.texts.setdefault(mid, {})[part.get('id')] = part.get('text', '')
        elif typ == 'step_finish':
            self.finishes[mid] = part.get('reason')
            if part.get('id') not in self.steps:
                self.steps.add(part.get('id'))
                tokens = part.get('tokens', {})
                for k in ('input','output','reasoning'): self.tokens[k] += tokens.get(k,0)
                for k in ('read','write'): self.tokens['cache_'+k] += tokens.get('cache',{}).get(k,0)
        elif typ == 'tool_use':
            state = part.get('state',{})
            self.tools[part.get('callID', part.get('id'))] = {
                'tool': part.get('tool'), 'arguments': state.get('input'),
                'status': state.get('status'), 'output': state.get('output'),
                'error': state.get('error')}
        elif typ == 'error': self.errors += 1
        # reasoning events are intentionally ignored.
    def final(self):
        terminal = [mid for mid, reason in self.finishes.items() if reason == 'stop']
        if self.errors or not terminal: return None
        return ''.join(self.texts.get(terminal[-1], {}).values()) or None
