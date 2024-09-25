import importlib
import os
import sys

import logfire

service = sys.argv[1] if len(sys.argv) == 2 else os.getenv('SERVICE')
services = 'webui', 'tiling', 'worker', 'spider'
# min duration is 10ms, spider isn't helped by auto tracing
logfire.install_auto_tracing(modules=[f'src.{s}' for s in services if s != 'spider'], min_duration=0.01)
if service is None:
    print('service argument variable not provided', file=sys.stderr)
    print('Available services:', ', '.join(services), file=sys.stderr)
elif service in services:
    module = importlib.import_module(f'.{service}', package='src')
    module.run()
else:
    print(f'Unknown service: {service}', file=sys.stderr)
    print('Available services:', ', '.join(services), file=sys.stderr)
