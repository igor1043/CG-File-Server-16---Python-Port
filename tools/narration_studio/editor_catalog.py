"""A single occurrence order for both columns, and honest conversion counts."""
from pathlib import Path
import json,os,collections
from core import connect, GAME, PROJECTS


def source_signature(path):
    stat = Path(path).stat()
    return dict(size=stat.st_size, mtime_ns=stat.st_mtime_ns)


def converted_keys(name):
    """Only count sources contained in a package and unchanged since conversion."""
    reports = []
    for root in (PROJECTS / name / 'build', GAME / 'Narrations' / name):
        report, package = root / 'build_report.json', root / 'profile.npack'
        if report.is_file() and package.is_file():
            reports.append((report.stat().st_mtime_ns, report, package))
    if not reports:
        return {}
    _, report, package = max(reports)
    package_time=package.stat().st_mtime_ns
    try:
        entries = json.loads(report.read_text(encoding='utf8'))
    except (ValueError, OSError):
        return {}
    signatures = {}
    requested=collections.defaultdict(set)
    for item in entries:
        if 'error' not in item and item.get('source'):
            path=Path(item['source']);requested[path.parent].add(path.name)
    # Windows directory enumeration already carries size and timestamp.
    # Avoid thousands of separate network/USB file-stat requests on opening.
    for directory,names in requested.items():
        try:
            with os.scandir(directory) as files:
                remaining=set(names)
                for entry in files:
                    if entry.name in names:
                        stat=entry.stat();signatures[str(Path(directory)/entry.name)]=dict(size=stat.st_size,mtime_ns=stat.st_mtime_ns)
                        remaining.discard(entry.name)
                        if not remaining:break
        except OSError:pass
    result = {}
    for item in entries:
        if 'error' in item:
            continue
        path = item.get('source', '')
        if path not in signatures:
            try:
                signatures[path] = source_signature(path)
            except OSError:
                signatures[path] = None
        signature = signatures[path]
        if signature is None:
            continue
        # Existing releases predate source_signature; their build timestamp is
        # the only available freshness evidence. New builds record both fields.
        saved = item.get('source_signature')
        valid = signature == saved if saved else signature['mtime_ns'] <= package_time
        if valid:
            result[item['clip']] = path
    return result


def paired_page(name, query='', category=None, offset=0, state='Todos', converted=None,
                original_query=None, source_query=None):
    converted = converted if converted is not None else converted_keys(name)
    db = connect()
    conversion_filter=state in ('Já convertidos','Ainda não convertidos','Com áudio, a converter')
    if conversion_filter:
        db.execute('CREATE TEMP TABLE ready_audio (clip TEXT PRIMARY KEY,path TEXT)')
        db.executemany('INSERT INTO ready_audio VALUES (?,?)',converted.items())
    separate_search=original_query is not None or source_query is not None
    search_parts=[];search_params=[]
    if separate_search:
        if original_query and original_query.strip():
            search_parts.append('(fold(c.event) LIKE fold(?) OR fold(c.transcript) LIKE fold(?) OR fold(c.key) LIKE fold(?) OR fold(c.topic) LIKE fold(?))')
            search_params.extend(['%'+original_query.strip()+'%']*4)
        if source_query and source_query.strip():
            search_parts.append('(fold(s.transcript) LIKE fold(?) OR fold(s.path) LIKE fold(?) OR fold(s.event) LIKE fold(?) OR fold(s.topic) LIKE fold(?))')
            search_params.extend(['%'+source_query.strip()+'%']*4)
    elif query:
        search_parts.append('(fold(c.event) LIKE fold(?) OR fold(c.transcript) LIKE fold(?) OR fold(c.key) LIKE fold(?) OR fold(c.topic) LIKE fold(?) OR fold(s.transcript) LIKE fold(?) OR fold(s.path) LIKE fold(?) OR fold(s.event) LIKE fold(?) OR fold(s.topic) LIKE fold(?))')
        search_params.extend(['%'+query+'%']*8)
    where=' AND '.join(search_parts) if search_parts else '1'
    params = [name,name] + search_params
    if category:
        where += ' AND c.topic=?'
        params.append(category)
    if name != 'Tiago Leifert':
        if state == 'Sem áudio próprio':
            where += ' AND s.key IS NULL'
        elif state == 'Com áudio próprio':
            where += ' AND s.key IS NOT NULL'
        elif state=='Já convertidos':where+=' AND ready.path=s.path'
        elif state=='Ainda não convertidos':where+=' AND (ready.path IS NULL OR s.path IS NULL OR ready.path!=s.path)'
        elif state=='Com áudio, a converter':where+=' AND s.key IS NOT NULL AND (ready.path IS NULL OR ready.path!=s.path)'
        elif state in ('Revisados/aprovados','Revisados manualmente'):where+=' AND coalesce(rv.reviewed,0)=1'
        elif state=='Sugestões para revisar':where+=" AND s.key IS NOT NULL AND m.method NOT IN ('manual','gender_review','boundary_cleanup')"
    elif state in ('Sem áudio próprio','Ainda não convertidos','Com áudio, a converter','Sugestões para revisar'):where+=' AND 0'
    if state in ('Revisados/aprovados','Revisados manualmente') and name=='Tiago Leifert':where+=' AND coalesce(rv.reviewed,0)=1'
    sql = '''FROM clips c LEFT JOIN mappings m ON m.clip=c.key AND m.profile=?
             LEFT JOIN sources s ON s.key=m.source
             LEFT JOIN narration_reviews rv ON rv.clip=c.key AND rv.profile=? '''+('LEFT JOIN ready_audio ready ON ready.clip=c.key ' if conversion_filter else '')+' WHERE '+where
    fast_page=not query and not (original_query or '').strip() and not (source_query or '').strip() and state=='Todos'
    if fast_page:
        clip_where='c.topic=?' if category else '1';clip_params=[category] if category else []
        total=db.execute('SELECT count(*) FROM clips c WHERE '+clip_where,clip_params).fetchone()[0]
        sql='''FROM (SELECT c.* FROM clips c WHERE '''+clip_where+''' ORDER BY c.event,c.bank,c.row,c.key LIMIT 500 OFFSET ?) c
             LEFT JOIN mappings m ON m.clip=c.key AND m.profile=? LEFT JOIN sources s ON s.key=m.source
             LEFT JOIN narration_reviews rv ON rv.clip=c.key AND rv.profile=?'''
        params=clip_params+[offset,name,name]
    else:total = db.execute('SELECT count(*) ' + sql, params).fetchone()[0]
    # Both lists receive these very same clip keys, including unmapped rows.
    rows = [dict(r) for r in db.execute('''SELECT c.*,coalesce(rv.reviewed,0) reviewed,s.key source_key,s.path source_path,
               s.transcript source_transcript,s.duration source_duration,s.event source_event,
               s.confidence source_confidence,s.topic source_topic ''' + sql +
               ' ORDER BY c.event,c.bank,c.row,c.key'+('' if fast_page else ' LIMIT 500 OFFSET ?'), params if fast_page else params + [offset])]
    usage = dict(db.execute('SELECT source,count(DISTINCT clip) FROM mappings WHERE profile=? GROUP BY source',(name,)))
    db.close()
    for row in rows:
        row['source_uses'] = usage.get(row['source_key'],0)
        if name == 'Tiago Leifert':
            row.update(source_key=row['key'], source_path=row['wav'], source_transcript=row['transcript'],
                       source_duration=row['duration'], source_event=row['event'], source_topic=row['topic'],
                       conversion='Original do jogo')
        elif not row['source_key']:
            row['conversion'] = 'Sem áudio próprio'
        elif converted.get(row['key']) == row['source_path']:
            row['conversion'] = 'Convertido'
        else:
            row['conversion'] = 'A converter'
    return rows, total


def coverage(name, converted=None):
    converted = converted if converted is not None else converted_keys(name)
    db = connect()
    groups = {}
    rows = db.execute('''SELECT c.key,c.topic,c.transcript,c.wav,c.status,s.path,coalesce(rv.reviewed,0) reviewed
        FROM clips c LEFT JOIN mappings m ON m.clip=c.key AND m.profile=?
        LEFT JOIN sources s ON s.key=m.source
        LEFT JOIN narration_reviews rv ON rv.clip=c.key AND rv.profile=?''', (name,name)).fetchall()
    physical = set()
    for row in rows:
        group = groups.setdefault(row['topic'], dict(total=0, linked=0, converted=0, transcribed=0, reviewed=0))
        group['total'] += 1
        group['transcribed'] += bool(row['transcript'])
        group['reviewed'] += bool(row['reviewed'])
        original = name == 'Tiago Leifert'
        group['linked'] += original or bool(row['path'])
        group['converted'] += original or (bool(row['path']) and converted.get(row['key']) == row['path'])
        if row['status'] == 'decoded':
            physical.add(row['wav'])
    db.close()
    totals = {key: sum(g[key] for g in groups.values()) for key in ('total', 'linked', 'converted', 'transcribed', 'reviewed')}
    totals.update(physical=len(physical), missing=totals['total'] - totals['linked'],
                  pending=totals['total'] - totals['converted'], topics=groups)
    return totals
