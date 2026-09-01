from __future__ import annotations
import argparse,json,sys
from pathlib import Path
import httpx
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
from common import V03,dump_json
sys.path.insert(0,str(V03/'src'))
from memory_handoff_bench.config import load_config

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument('--output',required=True);a=ap.parse_args();config=load_config(V03/'configs/counterfactual-v0.3.yaml')
    base=config.qdrant_url.rstrip('/');out={}
    with httpx.Client(timeout=60) as client:
        r=client.get(base+'/collections');r.raise_for_status();payload=r.json(); cols=payload.get('result',{}).get('collections',[])
        for x in cols:
            name=x.get('name');
            if not name:continue
            d=client.get(base+'/collections/'+name);d.raise_for_status();info=d.json().get('result',{})
            out[name]={'points_count':info.get('points_count'),'vectors_count':info.get('vectors_count'),'status':info.get('status')}
    dump_json(Path(a.output),out);return 0
if __name__=='__main__':raise SystemExit(main())
