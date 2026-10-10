"""Terminal checkpoints are the unit of resume; a sample cannot kill the queue."""
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from runner.run_agent import isolated_run_one, TERMINAL_STATUSES, write_json

def remaining(rows, logs):
    ids={r['id'] for r in rows}
    seen=set()
    for record in logs:
        if record['id'] not in ids or record['id'] in seen or record['status'] not in TERMINAL_STATUSES:
            raise ValueError('Invalid terminal checkpoint')
        seen.add(record['id'])
    return [row for row in rows if row['id'] not in seen]

def run_queue(rows, logs, out, args, cfg, key, checkpoint, worker=isolated_run_one):
    pending=iter(remaining(rows,logs))
    with ThreadPoolExecutor(max_workers=cfg['runtime']['concurrency']) as pool:
        futures={}
        def submit():
            row=next(pending,None)
            if row is not None:futures[pool.submit(worker,row,args,cfg,key)]=row
        for _ in range(cfg['runtime']['concurrency']):submit()
        while futures:
            completed,_=wait(futures,return_when=FIRST_COMPLETED)
            for future in completed:
                row=futures.pop(future)
                try:item=future.result()
                except Exception as exc:
                    # Defense in depth even when a replacement worker raises.
                    from runner.adapter import prompt_hash
                    item={'id':row['id'],'dataset':row['dataset'],'task_type':row['task_type'],
                          'prompt_hash':prompt_hash(row['messages']),'profile':'A',
                          'status':'infra_failure','failure':'worker_'+type(exc).__name__,
                          'final_answer':None,'model_response':None,'tool_calls':[],
                          'token_usage':{'input':0,'output':0,'reasoning':0,'cache_read':0,'cache_write':0},
                          'latency_seconds':0,'transport_checks':[],'usage_incomplete':True}
                if item.get('id')!=row['id'] or item.get('status') not in TERMINAL_STATUSES:
                    raise ValueError('Worker broke terminal record contract')
                dest=out/'logs'/row['id'];dest.mkdir(parents=True,exist_ok=True)
                write_json(dest/'trajectory.json',item)
                logs.append(item)
                checkpoint()
                submit()
