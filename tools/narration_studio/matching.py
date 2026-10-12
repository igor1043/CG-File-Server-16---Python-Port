"""Local semantic proposals; keep method/score and avoid player-name rows."""
from pathlib import Path
import json
from core import connect,WORK
from generic_policy import candidate_allowed,intro_role
MODEL='sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
def model():
    from sentence_transformers import SentenceTransformer
    # Reuse the installed local model without remote metadata requests.
    try:return SentenceTransformer(MODEL,device='cpu',local_files_only=True)
    except OSError:return SentenceTransformer(MODEL,device='cpu')
def seed_semantic(narrator,threshold=0.48):
    db=connect()
    originals=db.execute("""SELECT c.* FROM clips c JOIN banks b ON b.key=c.bank
        WHERE b.active=1 AND transcript!='' AND transcript!='[sem fala detectada]'
        AND category!='callname' GROUP BY wav""").fetchall()
    sources=db.execute("SELECT * FROM sources WHERE narrator=? AND transcript!='' AND transcript!='[sem fala detectada]' AND confidence>-.8",(narrator,)).fetchall()
    if not originals or not sources:raise ValueError('Transcreva os áudios originais e a biblioteca primeiro')
    encoder=model();left=encoder.encode([r['transcript'] for r in originals],normalize_embeddings=True,show_progress_bar=False)
    right=encoder.encode([r['transcript'] for r in sources],normalize_embeddings=True,show_progress_bar=False)
    scores=left@right.T;report=[]
    for i,original in enumerate(originals):
        # Openings are handled by their reviewed role pools in base_matching.
        if intro_role(original['event']):continue
        source=None
        for j in scores[i].argsort()[::-1][:20]:
            score=float(scores[i,j])
            if score<threshold:break
            candidate=sources[int(j)]
            if candidate_allowed(dict(original),dict(candidate)):
                source=candidate;break
        if source is None:continue
        # Physical aliases cannot have different replacements. Preserve manual
        # selections; these semantic links are explicitly test proposals.
        for alias in db.execute('SELECT key FROM clips WHERE bank=? AND offset=?',(original['bank'],original['offset'])).fetchall():
            db.execute('INSERT OR IGNORE INTO mappings VALUES (?,?,?,?,?)',(narrator,alias['key'],source['key'],'semantic_test',score))
        report.append(dict(clip=original['key'],event=original['event'],original=original['transcript'],source=source['path'],replacement=source['transcript'],score=score,review=True))
    db.commit();db.close();out=WORK/'transcriptions'/(narrator+'_associations.json');out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print('semantic proposals',narrator,len(report),flush=True);return report
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('narrator');p.add_argument('--threshold',type=float,default=.48);args=p.parse_args();seed_semantic(args.narrator,args.threshold)
