"""The same time contract applies to all provider adapters."""
import json,math,pathlib,sys,tempfile,types,unittest
from scibench.cli import ROOT,model_config

class RuntimeTimeoutTests(unittest.TestCase):
    def test_uniform_extended_policy_and_reject_provider_override(self):
        policy=json.loads((ROOT/'configs/runtime_policy.json').read_text())
        self.assertEqual([policy[k] for k in ('request_timeout_seconds','sample_timeout_seconds','tool_timeout_seconds')],[1800,7200,180])
        self.assertEqual([policy[k] for k in ('max_model_calls','max_tool_calls','api_max_attempts')],[24,32,3])
        for name in ('chat','responses','local'):
            path=ROOT/'configs'/f'{name}.json'
            cfg=model_config(types.SimpleNamespace(config=str(path),model='test-model',concurrency=1))
            self.assertEqual(cfg['model']['max_tokens'],32768)
            for field,value in policy.items():self.assertEqual(cfg['runtime'][field],value)
            for field in ('request_timeout_seconds','sample_timeout_seconds','tool_timeout_seconds'):
                changed=json.loads(path.read_text());changed['runtime'][field]-=1
                with tempfile.TemporaryDirectory() as tmp:
                    override=pathlib.Path(tmp)/'model.json';override.write_text(json.dumps(changed))
                    with self.assertRaisesRegex(ValueError,'runtime mismatch'):
                        model_config(types.SimpleNamespace(config=str(override),model='test-model',concurrency=1))

    @unittest.skipUnless(sys.platform=='linux','Linux scientific sandbox')
    def test_invalid_tool_deadline_rejected(self):
        from runner.sandbox import execute
        for value in (0,-1,math.inf,math.nan):
            with self.assertRaisesRegex(ValueError,'positive and finite'):
                execute('/unused','/unused','unused',value)

    def test_mcp_cleanup_grace_does_not_extend_execution(self):
        from runner.run_agent import make_config
        cfg=make_config(types.SimpleNamespace(url='http://localhost/v1'),'A',{'name':'test-model','max_tokens':32768},
            {'python':'python','harness':'harness','workspace':'workspace','venv':'venv','tool_timeout_seconds':180,'max_tool_calls':32})
        mcp=cfg['mcp']['scientific']
        self.assertEqual(mcp['environment']['SCIBENCH_TOOL_TIMEOUT'],'180')
        self.assertEqual(mcp['timeout'],190000)

if __name__=='__main__':unittest.main()
