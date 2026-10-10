"""Provider-reported accounting; absent usage is unknown, never zero cost."""
from collections import Counter
import json

def summarize(logs, pricing=None):
    totals=Counter();failures=Counter();tools=Counter()
    for row in logs:
        totals['samples']+=1;totals['latency_seconds']+=row['latency_seconds']
        totals['successful_samples']+=int(row['status'] in ('success','forced_finalization'))
        totals['normal_success']+=int(row['status']=='success')
        totals['soft_budget_triggered_count']+=int(row.get('soft_budget_triggered',False))
        totals['forced_finalization_count']+=int(row.get('forced_finalization_triggered',False))
        totals['forced_finalization_success_count']+=int(row['status']=='forced_finalization')
        totals['forced_finalization_calls']+=row.get('forced_finalization_calls',0)
        totals['agent_model_calls']+=row.get('agent_model_calls',0)
        totals['true_budget_failures']+=int(row.get('failure')=='budget_failure')
        totals['sample_timeouts']+=int(row['status']=='timeout')
        totals['infrastructure_failures']+=int(row['status']=='infra_failure')
        totals['usage_incomplete_samples']+=int(row.get('usage_incomplete',False))
        if row.get('failure'):
            failure=row['failure']
            category='timeout' if row['status']=='timeout' else ('budget' if 'budget' in failure else ('infrastructure' if row['status']=='infra_failure' else 'model'))
            failures[category]+=1
        for tool in row['tool_calls']:
            totals['tool_calls']+=1;tools[tool['tool']]+=1
            try: error=tool.get('status')=='error' or json.loads(tool.get('output','{}')).get('status')!='ok'
            except (ValueError,TypeError):error=True
            totals['tool_errors']+=int(error)
        for request in row['transport_checks']:
            if request.get('rejected'):continue
            totals['model_calls']+=1
            attempts=request.get('attempts') or [{'usage':request.get('provider_usage')}]
            totals['api_attempts']+=len(attempts);totals['api_retries']+=max(0,len(attempts)-1)
            for attempt in attempts:
                usage=attempt.get('usage')
                if not usage:
                    totals['attempts_without_usage']+=1;continue
                inp=usage.get('prompt_tokens',0)
                cached=usage.get('prompt_tokens_details',{}).get('cached_tokens',usage.get('prompt_cache_hit_tokens',0))
                output=usage.get('completion_tokens',0)
                reasoning=usage.get('completion_tokens_details',{}).get('reasoning_tokens',0)
                totals['cached_input_tokens']+=cached;totals['uncached_input_tokens']+=inp-cached
                totals['output_tokens_including_reasoning']+=output
                totals['reasoning_tokens_subset']+=reasoning
                totals['total_tokens']+=usage.get('total_tokens',inp+output)
    cost=None
    if pricing:
        cost=(totals['uncached_input_tokens']*pricing['input_per_million']+totals['cached_input_tokens']*pricing['cached_input_per_million']+totals['output_tokens_including_reasoning']*pricing['output_per_million'])/1e6
    return {'totals':dict(totals),'terminal_status_counts':dict(Counter(r['status'] for r in logs)),
        'forced_finalization_success_rate':totals['forced_finalization_success_count']/totals['forced_finalization_count'] if totals['forced_finalization_count'] else None,
        'failure_categories':dict(failures),'calls_by_tool':dict(tools),
        'estimated_cost':cost,'currency':pricing.get('currency') if pricing else None,
        'cost_note':'Estimate for reported usage only; missing usage may incur additional charges.' if pricing else 'No verified account-specific prices configured.',
        'reasoning_note':'Reasoning tokens are included in output tokens; do not add twice.'}
