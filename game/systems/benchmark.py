import csv
import ctypes
import json
import os
import platform
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


def memory_mb():
    if os.name != 'nt':
        return None
    from ctypes import wintypes

    class Counters(ctypes.Structure):
        _fields_ = [('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD),
                    ('PeakWorkingSetSize',ctypes.c_size_t),('WorkingSetSize',ctypes.c_size_t),
                    ('QuotaPeakPagedPoolUsage',ctypes.c_size_t),('QuotaPagedPoolUsage',ctypes.c_size_t),
                    ('QuotaPeakNonPagedPoolUsage',ctypes.c_size_t),('QuotaNonPagedPoolUsage',ctypes.c_size_t),
                    ('PagefileUsage',ctypes.c_size_t),('PeakPagefileUsage',ctypes.c_size_t)]
    kernel = ctypes.WinDLL('kernel32',use_last_error=True)
    psapi = ctypes.WinDLL('psapi',use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD]
    stats = Counters()
    stats.cb = ctypes.sizeof(stats)
    if psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(),ctypes.byref(stats),stats.cb):
        return stats.WorkingSetSize/(1024*1024)
    return None


def scene_counts(root):
    # Evita a varredura de vertices do SceneGraphAnalyzer a cada atualizacao do HUD.
    geoms = triangles = 0
    for path in root.findAllMatches('**/+GeomNode'):
        node = path.node()
        geoms += node.getNumGeoms()
        for i in range(node.getNumGeoms()):
            geom = node.getGeom(i)
            for j in range(geom.getNumPrimitives()):
                primitive = geom.getPrimitive(j)
                triangles += primitive.getNumFaces()
    return dict(scene_geoms=geoms,scene_triangles=triangles)


def save_benchmark(samples,settings,counts,shadow,mode,output_dir=Path('benchmarks')):
    output_dir.mkdir(parents=True,exist_ok=True)
    values = np.asarray(samples,dtype=float)
    result = dict(version='0.5.0',utc=datetime.now(timezone.utc).isoformat(),
                  seed=settings.seed,mode=mode,python=platform.python_version(),
                  platform=platform.platform(),width=settings.width,height=settings.height,
                  shadows=shadow,frames=len(values),seconds=float(values.sum()),
                  fps=float(1/values.mean()) if len(values) else 0,
                  frame_ms_p50=float(np.percentile(values,50)*1000) if len(values) else 0,
                  frame_ms_p95=float(np.percentile(values,95)*1000) if len(values) else 0,
                  frame_ms_p99=float(np.percentile(values,99)*1000) if len(values) else 0,
                  frame_ms_max=float(values.max()*1000) if len(values) else 0,
                  frames_over_33ms=int(np.count_nonzero(values > .033333)),
                  ram_mb=memory_mb(),**counts)
    path = output_dir/'history-v0.5.csv'
    exists = path.exists() and path.stat().st_size > 0
    with path.open('a',newline='',encoding='utf-8') as file:
        writer = csv.DictWriter(file,fieldnames=list(result))
        if not exists:
            writer.writeheader()
        writer.writerow(result)
    (output_dir/'latest.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result
