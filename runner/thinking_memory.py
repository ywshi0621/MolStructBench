"""Provider continuation state in RAM only; never serialize this object or its values."""
import threading

class ThinkingMemory:
    def __init__(self):
        self._by_call={}
        self._lock=threading.Lock()
    def remember(self,call_ids,text):
        with self._lock:
            for call_id in call_ids:
                if call_id:self._by_call[call_id]=text
    def restore(self,messages):
        restored=0
        with self._lock:
            for message in messages:
                if message.get('role')!='assistant':continue
                ids=[c.get('id') for c in message.get('tool_calls',[])]
                found=next((self._by_call[c] for c in ids if c in self._by_call),None)
                if found is not None:
                    message['reasoning_content']=found
                    restored+=1
        return restored
    def clear(self):
        with self._lock:self._by_call.clear()

class ThinkingAccumulator:
    def __init__(self,memory):
        self.memory=memory
        self._pieces=[]
        self._ids={}
    def accept(self,event):
        for choice in event.get('choices',[]):
            if choice.get('index',0)!=0:continue
            delta=choice.get('delta',{})
            if isinstance(delta.get('reasoning_content'),str):self._pieces.append(delta['reasoning_content'])
            for call in delta.get('tool_calls',[]):
                if call.get('id'):self._ids[call.get('index',0)]=call['id']
            if choice.get('finish_reason'):
                self.memory.remember(self._ids.values(),''.join(self._pieces))
