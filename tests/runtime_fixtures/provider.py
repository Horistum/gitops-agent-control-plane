"""TEST ONLY: protocol peer executed as a separate process, not an AI provider."""
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime_support import proposal
request=json.load(sys.stdin)
json.dump(proposal(request['input']),sys.stdout)
