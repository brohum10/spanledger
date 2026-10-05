"""Offline interval accounting for nested application spans (integer microseconds)."""
import argparse
import json
from pathlib import Path


def merge(intervals):
    """Union half-open intervals, including touching boundaries."""
    result = []
    for start, end in sorted(intervals):
        if start == end:
            continue
        if result and start <= result[-1][1]:
            result[-1][1] = max(result[-1][1], end)
        else:
            result.append([start, end])
    return result


def duration(intervals):
    return sum(b - a for a, b in merge(intervals))


def analyze(spans):
    if not isinstance(spans, list) or not spans:
        raise ValueError('spans must be a nonempty array')
    by_id = {}
    required = {'id', 'service', 'name', 'start_us', 'end_us'}
    for span in spans:
        if not isinstance(span, dict) or not required <= set(span) <= required | {'parent'}:
            raise ValueError('each span requires id, service, name, start_us, end_us; parent is optional')
        if any(not isinstance(span[k], str) or not span[k].strip() for k in ('id', 'service', 'name')):
            raise ValueError('id, service and name must be nonblank strings')
        if span['id'] in by_id:
            raise ValueError('duplicate span ID: ' + span['id'])
        if any(type(span[k]) is not int for k in ('start_us', 'end_us')):
            raise ValueError('timestamps must be integer microseconds')
        if not 0 <= span['start_us'] <= span['end_us']:
            raise ValueError('timestamps must satisfy 0 <= start_us <= end_us')
        parent = span.get('parent')
        if parent is not None and (not isinstance(parent, str) or not parent.strip()):
            raise ValueError('parent must be a nonblank span ID or null')
        by_id[span['id']] = span
    children = {key: [] for key in by_id}
    for span in spans:
        parent = span.get('parent')
        if parent is not None:
            if parent not in by_id:
                raise ValueError('missing parent: ' + parent)
            p = by_id[parent]
            if not p['start_us'] <= span['start_us'] <= span['end_us'] <= p['end_us']:
                raise ValueError('child falls outside parent: ' + span['id'])
            children[parent].append(span)
    # Iterative parent walk avoids recursion-depth failure on legitimate deep traces.
    done = set()
    for key in by_id:
        path = set()
        current = key
        while current is not None and current not in done:
            if current in path:
                raise ValueError('parent cycle detected')
            path.add(current)
            current = by_id[current].get('parent')
        done.update(path)
    rows = []
    for key, span in sorted(by_id.items()):
        inclusive = span['end_us'] - span['start_us']
        covered = duration([(c['start_us'], c['end_us']) for c in children[key]])
        rows.append({'id': key, 'service': span['service'], 'name': span['name'],
                     'inclusive_us': inclusive, 'child_union_us': covered,
                     'self_us': inclusive - covered,
                     'child_overlap_us': sum(c['end_us'] - c['start_us'] for c in children[key]) - covered})
    first = min(s['start_us'] for s in spans)
    last = max(s['end_us'] for s in spans)
    union = merge([(s['start_us'], s['end_us']) for s in spans])
    gaps = []
    cursor = first
    for start, end in union:
        if start > cursor:
            gaps.append([cursor, start])
        cursor = end
    if cursor < last:
        gaps.append([cursor, last])
    services = []
    for service in sorted({s['service'] for s in spans}):
        selected = [s for s in spans if s['service'] == service]
        services.append({'service': service, 'span_count': len(selected),
                         'active_union_us': duration([(s['start_us'], s['end_us']) for s in selected]),
                         'sum_self_us': sum(r['self_us'] for r in rows if r['service'] == service)})
    return {'schema_version': 1, 'span_count': len(spans), 'window_us': last - first,
            'active_union_us': sum(b - a for a, b in union),
            'uncovered_us': sum(b - a for a, b in gaps), 'gaps': gaps,
            'spans': rows, 'services': services}


def unique_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON field: ' + key)
        result[key] = value
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('trace', type=Path, help='JSON array of spans')
    args = parser.parse_args(argv)
    try:
        report = analyze(json.loads(args.trace.read_text(encoding='utf-8'), object_pairs_hook=unique_fields))
    except (OSError, ValueError) as error:
        parser.exit(2, f'spanledger: {error}\n')
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
