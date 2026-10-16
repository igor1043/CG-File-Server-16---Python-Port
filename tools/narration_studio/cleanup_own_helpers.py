"""Only terminate disposable QA helpers created by this task."""
import psutil
for p in psutil.process_iter(['pid','name']):
    try:
        args=p.cmdline();line=' '.join(args)
        owned_probe='transcribe_probe_pes.py' in line
        owned_smoke=(p.name().casefold()=='narrationstudio.exe' and '--smoke' in args and 'narration_studio_hotfix' in p.exe())
        if owned_probe or owned_smoke:
            print('stopping QA helper',p.pid,flush=True);p.terminate()
    except psutil.Error:pass
