import psutil,json
for p in psutil.process_iter(['pid','name','cmdline','create_time']):
    args=p.info['cmdline'] or []
    if any('pes_extract_library.py' in x or 'build_initial_pes_profile' in x for x in args):
        try:print(json.dumps(dict(pid=p.pid,parent=p.parent().pid if p.parent() else 0,created=p.info['create_time'],cpu=p.cpu_times().user,args=args),ensure_ascii=True),flush=True)
        except psutil.Error:pass
