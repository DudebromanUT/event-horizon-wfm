"""Event Horizon: pocket workforce management that runs offline.

Pure Python 3.10, no dependencies. Start with:

    from horizon import required_agents
    required_agents(100, 300)                  # 100 calls/30 min, 5:00 AHT, 80/20
    required_agents(100, 300, patience=120)    # callers give up after ~2:00
"""

from .erlang import Metrics, erlang_a, erlang_c, metrics, required_agents, simulate, staffing_table, workload

__version__ = '0.1.0'
