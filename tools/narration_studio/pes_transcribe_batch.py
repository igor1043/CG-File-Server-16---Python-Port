"""Resume Portuguese Whisper transcription for the deduplicated PES audio library."""
from pathlib import Path
import argparse
import json
import sqlite3
import time

import numpy as np

from pes_extract_library import DEFAULT_ROOT, open_index, publish
from transcribe import whisper_model


SAMPLE_RATE = 16_000
SEPARATOR_SAMPLES = SAMPLE_RATE // 10
CHUNK_SECONDS = 29


def run(root=DEFAULT_ROOT, batch_size=16, limit=0, order='asc', progress_file=None, shard_index=0, shard_count=1):
    from faster_whisper import BatchedInferencePipeline
    from faster_whisper.audio import decode_audio

    root = Path(root)
    if shard_count < 1 or not 0 <= shard_index < shard_count:
        raise ValueError('shard-index precisa estar entre 0 e shard-count-1.')
    shard_sql = '' if shard_count == 1 else " AND ((instr('0123456789abcdef', lower(substr(sha,1,1)))-1) % ? = ?)"
    shard_params = () if shard_count == 1 else (shard_count, shard_index)
    db = open_index(root)
    db.row_factory = sqlite3.Row
    pending = db.execute(
        "SELECT count(*) FROM assets WHERE status='decoded' AND transcript IS NULL" + shard_sql, shard_params
    ).fetchone()[0]
    overall_total = db.execute(
        "SELECT count(*) FROM assets WHERE status IN ('decoded','transcription_failed')" + shard_sql, shard_params
    ).fetchone()[0]
    previous_done = db.execute('SELECT count(*) FROM assets WHERE transcript IS NOT NULL' + shard_sql, shard_params).fetchone()[0]
    previous_failed = db.execute("SELECT count(*) FROM assets WHERE status='transcription_failed'" + shard_sql, shard_params).fetchone()[0]
    if limit:
        pending = min(pending, limit)

    model = whisper_model('small')
    pipeline = BatchedInferencePipeline(model=model)
    order_sql = 'ASC' if order == 'asc' else 'DESC'
    done = failed = processed = 0
    started = time.time()
    progress_path = Path(progress_file) if progress_file else root / 'transcription_progress.json'

    def write_progress(state):
        payload = {
            'state': state,
            'done': min(previous_done + done, overall_total),
            'total': overall_total,
            'remaining': max(0, overall_total - previous_done - done - previous_failed - failed),
            'failed': previous_failed + failed,
            'failed_this_run': failed,
            'elapsed_seconds': round(time.time() - started),
            'batch_size': batch_size,
            'device': 'cuda' if getattr(model, 'device', None) == 'cuda' else str(getattr(model, 'device', 'auto')),
        }
        temporary = progress_path.with_suffix('.tmp')
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf8')
        temporary.replace(progress_path)
        return payload

    def save(row, text, duration, error=''):
        nonlocal done, failed
        if error:
            db.execute("UPDATE assets SET status='transcription_failed',error=? WHERE sha=?", (error, row['sha']))
            failed += 1
        else:
            db.execute('UPDATE assets SET transcript=?,duration=?,error="" WHERE sha=?', (text, duration, row['sha']))
            sidecar = Path(row['path']).with_suffix('.txt')
            temporary = sidecar.with_suffix('.tmp')
            temporary.write_text(text, encoding='utf8')
            temporary.replace(sidecar)
            done += 1

    def infer(items):
        """Infer a batch, splitting only if the backend rejects a batch."""
        nonlocal done, failed
        waves = []
        intervals = []
        cursor = 0
        for row, samples, duration in items:
            begin = cursor
            end = begin + len(samples)
            intervals.append((begin / SAMPLE_RATE, end / SAMPLE_RATE, row, duration))
            waves.append(samples)
            waves.append(np.zeros(SEPARATOR_SAMPLES, dtype=np.float32))
            cursor = end + SEPARATOR_SAMPLES

        merged = np.concatenate(waves)
        timestamps = []
        for begin, end, _, _ in intervals:
            offset = begin
            while offset < end:
                timestamps.append({'start': offset, 'end': min(end, offset + CHUNK_SECONDS)})
                offset += CHUNK_SECONDS
        try:
            segments, _ = pipeline.transcribe(
                merged,
                language='pt',
                beam_size=3,
                condition_on_previous_text=False,
                vad_filter=False,
                clip_timestamps=timestamps,
                batch_size=batch_size,
            )
            words = [[] for _ in intervals]
            confidence = [[] for _ in intervals]
            segment_items = list(segments)
            index = 0
            for segment in segment_items:
                if segment.no_speech_prob >= .6 or segment.avg_logprob < -1.0:
                    continue
                while index + 1 < len(intervals) and segment.start >= intervals[index][1]:
                    index += 1
                begin, end, _, _ = intervals[index]
                if begin - .005 <= segment.start < end:
                    words[index].append(segment.text.strip())
                    confidence[index].append(segment.avg_logprob)
            for i, (_, _, row, duration) in enumerate(intervals):
                text = ' '.join(part for part in words[i] if part).strip() or '[sem fala detectada]'
                save(row, text, duration)
            db.commit()
        except Exception as exc:
            if len(items) > 1:
                midpoint = len(items) // 2
                infer(items[:midpoint])
                infer(items[midpoint:])
            else:
                row, _, duration = items[0]
                save(row, '', duration, str(exc)[:1000])
                db.commit()

    write_progress('running')
    print(f'PES ASR: {pending:,} pendentes; lotes de {batch_size}.', flush=True)
    try:
        while not limit or processed < limit:
            take = min(batch_size, limit - processed) if limit else batch_size
            rows = db.execute(
                f"SELECT sha,path,duration,peak FROM assets WHERE status='decoded' AND transcript IS NULL"
                f"{shard_sql} ORDER BY duration {order_sql} LIMIT ?", (*shard_params, take)
            ).fetchall()
            if not rows:
                break
            items = []
            for row in rows:
                if (row['duration'] or 0) < .18 or (row['peak'] or 0) < .002:
                    save(row, '[sem fala detectada]', row['duration'] or 0)
                    continue
                try:
                    samples = decode_audio(row['path'], sampling_rate=SAMPLE_RATE)
                    duration = len(samples) / SAMPLE_RATE
                    if not len(samples) or duration < .18 or float(np.max(np.abs(samples))) < .002:
                        save(row, '[sem fala detectada]', duration)
                    else:
                        items.append((row, samples, duration))
                except Exception as exc:
                    save(row, '', row['duration'] or 0, str(exc)[:1000])
            if items:
                infer(items)
            db.commit()
            processed += len(rows)
            if done % 100 < batch_size or not items:
                payload = write_progress('running')
                print(f"Transcritos: {payload['done']:,}/{payload['total']:,}; restantes {payload['remaining']:,}; falhas novas {failed:,}.", flush=True)
        db.commit()
        remaining = db.execute(
            "SELECT count(*) FROM assets WHERE status='decoded' AND transcript IS NULL"
        ).fetchone()[0]
        complete = remaining == 0
        if complete:
            publish(root, db)
        payload = write_progress('complete' if complete else 'partial')
        print(json.dumps(payload, ensure_ascii=True), flush=True)
    except KeyboardInterrupt:
        db.commit()
        write_progress('interrupted')
        raise
    finally:
        db.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=DEFAULT_ROOT)
    parser.add_argument('--batch-size', type=int, default=16)
    parser.add_argument('--limit', type=int, default=0, help='Transcribe at most this many pending unique assets.')
    parser.add_argument('--order', choices=('asc', 'desc'), default='asc')
    parser.add_argument('--progress-file', type=Path, help='Write progress to a separate JSON file for parallel workers.')
    parser.add_argument('--shard-index', type=int, default=0)
    parser.add_argument('--shard-count', type=int, default=1, help='Split assets into deterministic non-overlapping workers.')
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 64:
        parser.error('--batch-size precisa ficar entre 1 e 64.')
    if args.shard_count < 1 or not 0 <= args.shard_index < args.shard_count:
        parser.error('--shard-index precisa estar entre 0 e --shard-count-1.')
    run(args.root, args.batch_size, args.limit, args.order, args.progress_file, args.shard_index, args.shard_count)
