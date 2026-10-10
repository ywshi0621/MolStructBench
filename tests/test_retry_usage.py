import json
import threading
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from unittest.mock import patch
from runner.gateway import Gateway
from runner.usage import summarize

class RetryUsageTests(unittest.TestCase):
    def test_forced_provider_call_disables_tools_and_refuses_tool_response(self):
        for illegal in (False,True):
            seen=[]
            class Handler(BaseHTTPRequestHandler):
                def log_message(self,*args):pass
                def do_POST(self):
                    seen.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                    self.send_response(200);self.end_headers()
                    delta={'tool_calls':[{'index':0,'id':'forbidden','function':{'name':'scientific_shell','arguments':'{}'}}]} if illegal else {'content':'FINAL'}
                    event={'choices':[{'delta':delta,'finish_reason':'tool_calls' if illegal else 'stop'}]}
                    self.wfile.write(('data: '+json.dumps(event)+'\n\ndata: [DONE]\n\n').encode())
            server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
            threading.Thread(target=server.serve_forever,daemon=True).start()
            task={'messages':[{'role':'system','content':'frozen'},{'role':'user','content':'question'}]}
            model={'name':'test','base_url':f'http://127.0.0.1:{server.server_port}','max_tokens':32}
            runtime={'request_timeout_seconds':5,'max_model_calls':24,'max_tool_calls':32,'hard_model_calls':0}
            try:
                with Gateway(model,runtime,task,'A','test') as gateway:
                    req=urllib.request.Request(gateway.url+'/chat/completions',json.dumps({'messages':task['messages'],'tools':[{'type':'function','function':{'name':'scientific_shell'}}]}).encode(),{'Authorization':'Bearer '+gateway.token})
                    try:
                        with urllib.request.urlopen(req,timeout=5) as response:response.read()
                    except urllib.error.HTTPError:
                        if not illegal:raise
                    self.assertEqual(seen[0]['tools'],[])
                    self.assertEqual(seen[0]['tool_choice'],'none')
                    self.assertEqual(gateway.budget.finalization_calls,1)
                    self.assertEqual(gateway.finalization_answer,None if illegal else 'FINAL')
                    self.assertEqual(gateway.status,'budget_failure' if illegal else None)
                    with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(req,timeout=5)
                    self.assertEqual(len(seen),1)
            finally:server.shutdown();server.server_close()

    def test_transient_provider_error_retries_without_duplicate_agent_content(self):
        calls=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                calls.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                if len(calls)==1:
                    self.send_response(429);self.end_headers();return
                self.send_response(200);self.end_headers()
                event={'model':'test','choices':[{'delta':{'content':'FINAL'},'finish_reason':'stop'}],
                       'usage':{'prompt_tokens':10,'completion_tokens':2,'total_tokens':12}}
                self.wfile.write(('data: '+json.dumps(event)+'\n\ndata: [DONE]\n\n').encode())
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        task={'messages':[{'role':'system','content':'exact system'},{'role':'user','content':'exact question'}]}
        model={'name':'test','base_url':f'http://127.0.0.1:{server.server_port}','temperature':1,'max_tokens':32}
        runtime={'request_timeout_seconds':5,'max_model_calls':3,'max_tool_calls':3,'api_max_attempts':2}
        try:
            with patch('runner.gateway.time.sleep'),Gateway(model,runtime,task,'A','test') as gateway:
                req=urllib.request.Request(gateway.url+'/chat/completions',json.dumps({'messages':task['messages']}).encode(),
                    {'Authorization':'Bearer '+gateway.token})
                with urllib.request.urlopen(req,timeout=5) as r:body=r.read()
                self.assertEqual(body.count(b'FINAL'),1)
                self.assertEqual(len(gateway.records),1)
                self.assertEqual(len(gateway.records[0]['attempts']),2)
                self.assertIsNone(gateway.status)
                self.assertNotIn('reasoning_effort',calls[0])
                self.assertEqual(calls[1]['messages'],task['messages'])
        finally:server.shutdown();server.server_close()

    def test_cached_and_reasoning_tokens_not_double_counted(self):
        row={'latency_seconds':1,'status':'success','failure':None,'tool_calls':[],
             'transport_checks':[{'attempts':[{'http_status':429},{'usage':{'prompt_tokens':100,'prompt_tokens_details':{'cached_tokens':70},
                 'completion_tokens':20,'completion_tokens_details':{'reasoning_tokens':12},'total_tokens':120}}]}]}
        got=summarize([row])['totals']
        self.assertEqual(got['total_tokens'],120)
        self.assertEqual(got['uncached_input_tokens'],30)
        self.assertEqual(got['reasoning_tokens_subset'],12)
        self.assertEqual(got['api_retries'],1)
        self.assertEqual(got['attempts_without_usage'],1)
