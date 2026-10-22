"""Replay the fixed experiment into a fresh directory; never overwrite saved runs."""
import argparse
from datetime import datetime
from pathlib import Path
import run_local as r

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output-name',default='rerun_'+datetime.now().strftime('%Y%m%d_%H%M%S'))
args=parser.parse_args()
if Path(args.output_name).name!=args.output_name or args.output_name in ('.','..'):
    parser.error('Use one folder name, not a path')
output=r.BASE/args.output_name
output.mkdir(exist_ok=False)
r.RESULTS=output
r.main()
