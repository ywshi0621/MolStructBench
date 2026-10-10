import unittest
from runner.thinking_memory import ThinkingMemory,ThinkingAccumulator

class ThinkingMemoryTests(unittest.TestCase):
    def test_multiple_delta_fragments_and_calls(self):
        m=ThinkingMemory();a=ThinkingAccumulator(m)
        for d in ({'reasoning_content':'fixture '},{'reasoning_content':'history'},
                  {'tool_calls':[{'index':0,'id':'call_a'},{'index':1,'id':'call_b'}]}):
            a.accept({'choices':[{'index':0,'delta':d,'finish_reason':None}]})
        a.accept({'choices':[{'index':0,'delta':{},'finish_reason':'tool_calls'}]})
        messages=[{'role':'assistant','tool_calls':[{'id':'call_a'},{'id':'call_b'}]}]
        self.assertEqual(m.restore(messages),1)
        self.assertEqual(messages[0]['reasoning_content'],'fixture history')
        m.clear()
        self.assertEqual(m.restore([{'role':'assistant','tool_calls':[{'id':'call_a'}]}]),0)
    def test_do_not_invent_missing_history(self):
        m=ThinkingMemory();messages=[{'role':'assistant','tool_calls':[{'id':'unknown'}]}]
        self.assertEqual(m.restore(messages),0)
        self.assertNotIn('reasoning_content',messages[0])
if __name__=='__main__':unittest.main()
