import logging
import os
from pathlib import Path
import runpy
import sys
from s200_config import PRIVATE, ROOT

endpoint = (PRIVATE / 'xiaozhi-mcp-endpoint.txt').read_text(encoding='utf-8-sig').strip()
if not endpoint.startswith('wss://'):
    sys.exit("Configure the device MCP WSS endpoint in xiaozhi-mcp-endpoint.txt")
os.environ['MCP_ENDPOINT'] = endpoint
old_factory = logging.getLogRecordFactory()
def redact(*args, **kwargs):
    record = old_factory(*args, **kwargs)
    record.msg = record.getMessage().replace(endpoint, '[endpoint redacted]')
    record.args = ()
    return record
logging.setLogRecordFactory(redact)
bridge = ROOT / '小智' / 'hight_weight' / 'zhudong_mcp' / 'mcp_pipe.py'
sys.argv = [str(bridge), str(Path(__file__).with_name('xiaozhi-iotda-measured.py').resolve())]
runpy.run_path(str(bridge), run_name='__main__')
