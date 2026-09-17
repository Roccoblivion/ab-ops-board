#!/usr/bin/env python3
# v2.1 (9/17/2026) - "New request received -> first acknowledgment sent" for rest@ + cons@.
# v2.1: threads are keyed on the job number in the subject (Neal WO no., TM BuildPro order no.) because
#       our staff append the Albi job number to the subject when they reply, and Neal adds [EXT] tags;
#       full-subject matching missed real acknowledgments and counted mid-thread replies as new requests.
# John's definition: the timer starts when the client's email instruction lands in our box
# and stops when our first email acknowledgment goes back to the client.
#
# INPUT:  inbound.json = [{box,subject,sender,received}]          (VIP-domain inbound, 30d)
#         sent.json    = [{box,subject,sender,sent,summary?}]     (box Sent Items, 30d)
# OUTPUT: email-response.json  (board card schema; v2 only ADDS fields, nothing removed)
#
# What v2 adds over v1:
#   - every item carries the actual received / acknowledged timestamps (ISO + ET label)
#   - raw wall-clock minutes (rawMin) next to business-hours minutes (min)
#   - a "week" block: requests received in the last 7 days, kept/missed, named misses
#   - one request copied to BOTH rest@ and cons@ is counted once; an acknowledgment from
#     either box stops the clock (v1 counted per box, which could show a false miss)
#   - acknowledgment-template detection: if our first reply opens with the standard line
#     ("...received your request..."), the thread counts as a new request even when the
#     client's subject has no keyword (closes the Taylor Morrison plain-address gap)
import json, re, sys, statistics
from datetime import datetime, timedelta, timezone
try:
    from zoneinfo import ZoneInfo; ET=ZoneInfo("America/New_York")
except Exception:
    ET=timezone(timedelta(hours=-4))
OPEN_H,CLOSE_H=8,17

def parse(s):
    s=s.replace("Z","+00:00"); dt=datetime.fromisoformat(s)
    if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ET)
def biz_minutes(a_iso,b_iso):
    a=parse(a_iso); b=parse(b_iso)
    if b<=a: return 0
    total=0.0; cur=a
    while cur.date()<=b.date():
        if cur.weekday()<5:
            o=cur.replace(hour=OPEN_H,minute=0,second=0,microsecond=0)
            c=cur.replace(hour=CLOSE_H,minute=0,second=0,microsecond=0)
            s=max(o,a) if cur.date()==a.date() else o
            e=min(c,b) if cur.date()==b.date() else c
            s=max(s,o); e=min(e,c)
            if e>s: total+=(e-s).total_seconds()/60.0
        cur=(cur+timedelta(days=1)).replace(hour=0,minute=0,second=0,microsecond=0)
    return round(total)
def raw_minutes(a_iso,b_iso):
    d=(parse(b_iso)-parse(a_iso)).total_seconds()/60.0
    return max(0,round(d))
def in_hours(iso):
    d=parse(iso)
    return d.weekday()<5 and OPEN_H<=d.hour<CLOSE_H
def label(iso):
    d=parse(iso)
    h=d.hour%12 or 12
    return '%s %d/%d %d:%02d%s' % (d.strftime('%a'), d.month, d.day, h, d.minute, 'am' if d.hour<12 else 'pm')

PREFIX=re.compile(r'^\s*(?:(?:re|fw|fwd|aw|tr)\s*:|\[\s*ext(?:ernal)?\s*\])\s*', re.I)
def strip_prefixes(subj):
    s=subj or ""
    while True:
        n=PREFIX.sub('',s)
        if n==s: break
        s=n
    return s
def norm(subj):
    return re.sub(r'\s+',' ',strip_prefixes(subj)).strip().lower()
def is_reply(subj):
    # a reply/continuation: after dropping [EXT] tags the subject starts with RE: or AW:
    s=subj or ""
    while True:
        n=re.sub(r'^\s*\[\s*ext(?:ernal)?\s*\]\s*','',s,flags=re.I)
        if n==s: break
        s=n
    return bool(re.match(r'^\s*(re|aw)\s*:',s,flags=re.I))
JOBNO=re.compile(r'(?<!\d)\d{6,}(?!\d)')
def thread_key(subj):
    n=norm(subj)
    m=JOBNO.search(n)
    return ('n:'+m.group(0)) if m else ('s:'+n)

DOMAINS={'taylormorrison.com':'Taylor Morrison','nealcommunities.com':'Neal',
         'pulte.com':'Pulte','pultegroup.com':'Pulte',
         # attribution only - these count once their domains are added to the daily pull
         'colliercompanies.com':'Collier Companies','islandvillage.org':'Island Village',
         'murrayhomesinc.com':'Murray Homes','davisdevelopment.com':'Davis Development'}
def builder_of(sender):
    s=(sender or '').lower()
    for d,name in DOMAINS.items():
        if d in s: return name
    return None
NOISE=re.compile(r'automatic reply|undeliverable|out of office|read:|accepted:|declined:|delivery has failed|delivery status', re.I)
NOISE_SENDER=re.compile(r'postmaster@|mailer-daemon|quickbooks@|notification\.intuit|klaviyo|houzz|constructconnect|ccsend|no-?reply', re.I)
# new-request subject patterns; precision-favoring
NEWJOB=re.compile(r'\bwo\b|\bwar\b|warranty task|\(wo\)|buildpro|remediation request|create a plan|plan of repair|truss clean|mold (mediation|remediation)|work order|\bepo\b', re.I)
# standard first line of our acknowledgment templates (kept narrow on purpose)
ACK_MARK=re.compile(r'received your (request|instruction|instructions|work order|email)|confirming receipt', re.I)

def is_opener_subject(subj):
    return bool(NEWJOB.search(subj or ''))

def _ok(m,field):
    try:
        parse(m[field]); return True
    except Exception:
        return False

def compute(inbound, sent, now_iso):
    inbound=[m for m in inbound if isinstance(m,dict) and _ok(m,'received')]
    sent=[m for m in sent if isinstance(m,dict) and _ok(m,'sent')]
    # replies indexed by thread key across BOTH boxes -> sorted [(sent, box, summary)]
    sent_idx={}
    for m in sent:
        sent_idx.setdefault(thread_key(m.get('subject')),[]).append((m['sent'], m.get('box'), m.get('summary') or ''))
    for k in sent_idx: sent_idx[k].sort(key=lambda t:parse(t[0]))
    def replies_for(k):
        if k.startswith('n:'): return sent_idx.get(k,[])
        # subject key: we often append the Albi job number, so accept replies whose subject STARTS with the opener subject
        out=[]
        for sk,v in sent_idx.items():
            if sk.startswith('s:') and sk[2:].startswith(k[2:]) and len(k)>8: out+=v
        return sorted(out,key=lambda t:parse(t[0]))
    # earliest inbound per thread across both boxes
    first={}
    for m in sorted(inbound, key=lambda x:parse(x['received'])):
        b=builder_of(m.get('sender'))
        if not b: continue
        subj=m.get('subject') or ''
        if NOISE.search(subj) or NOISE_SENDER.search(m.get('sender') or ''): continue
        k=thread_key(subj)
        if len(k)<=2: continue
        if k not in first:
            first[k]={'subject':subj,'acct':b,'received':m['received'],'boxes':[m.get('box')],'reply_first':is_reply(subj)}
        elif m.get('box') not in first[k]['boxes']:
            first[k]['boxes'].append(m.get('box'))
    items=[]; openitems=[]
    for k,o in first.items():
        if o['reply_first']: continue   # thread started before the window or outside these senders - not a new request
        reply=None
        for st,box,summ in replies_for(k):
            if parse(st)>parse(o['received']):
                reply=(st,box,summ); break
        keyword=is_opener_subject(o['subject'])
        template=bool(reply and ACK_MARK.search(reply[2]))
        if not (keyword or template): continue      # not a recognisable new request
        base={'job':o['subject'][:70],'acct':o['acct'],'received':o['received'],
              'receivedLabel':label(o['received']),'afterHours':not in_hours(o['received']),
              'box':'+'.join(sorted(x.split('@')[0] for x in o['boxes'] if x))}
        if reply:
            mins=biz_minutes(o['received'],reply[0]); raw=raw_minutes(o['received'],reply[0])
            base.update({'acked':reply[0],'ackedLabel':label(reply[0]),'min':mins,'rawMin':raw,
                         'kept':mins<=60,'keptRaw':raw<=60,'via':'template' if template else 'keyword'})
            items.append(base)
        else:
            base.update({'waitMin':biz_minutes(o['received'],now_iso),'rawWaitMin':raw_minutes(o['received'],now_iso)})
            openitems.append(base)
    return items, openitems

def agg(items):
    vals=[i['min'] for i in items]
    if not vals: return {'count':0,'medianMin':None,'within60':0,'within60Pct':None,'bestMin':None,'worstMin':None,'within60Raw':0,'medianRawMin':None}
    raws=[i.get('rawMin',i['min']) for i in items]
    return {'count':len(vals),'medianMin':round(statistics.median(vals)),
            'within60':sum(1 for v in vals if v<=60),
            'within60Pct':round(100*sum(1 for v in vals if v<=60)/len(vals)),
            'bestMin':min(vals),'worstMin':max(vals),
            'within60Raw':sum(1 for v in raws if v<=60),'medianRawMin':round(statistics.median(raws))}

def build(items, openitems, now_iso, lbl, auto=True):
    order=['Neal','Taylor Morrison','Pulte']
    accts=order+sorted({i['acct'] for i in items}-set(order))
    builders=[]
    for b in accts:
        v=[i['min'] for i in items if i['acct']==b]
        if v: builders.append({'name':b,'kept':sum(1 for x in v if x<=60),'total':len(v),'medianMin':round(statistics.median(v))})
    cut=parse(now_iso)-timedelta(days=7)
    wk=[i for i in items if parse(i['received'])>=cut]
    week=agg(wk)
    week.update({'from':label(cut.isoformat()),'to':label(now_iso),
                 'misses':[{'job':i['job'],'acct':i['acct'],'receivedLabel':i['receivedLabel'],'ackedLabel':i['ackedLabel'],'min':i['min'],'rawMin':i['rawMin'],'afterHours':i['afterHours']}
                           for i in sorted(wk,key=lambda x:-x['min']) if not i['kept']],
                 'open':[o for o in openitems if parse(o['received'])>=cut]})
    return {'asOf':now_iso,'asOfLabel':lbl,'auto':auto,'schema':2,'window':'rolling 30 days',
            'boxes':['rest@goaboveandbeyond.us','cons@goaboveandbeyond.us'],
            'metric':'New request received to first acknowledgment sent','scriptVersion':'2.1',
            'overall':agg(items),'week':week,'builders':builders,
            'items':sorted(items,key=lambda x:x['min']),
            'openItems':sorted(openitems,key=lambda x:-x['waitMin']),
            'note':'Clock starts when the client email lands in rest@ or cons@ and stops at our first email acknowledgment. Business-hours minutes (Mon-Fri 8-5 ET) decide kept/missed; raw minutes are shown too. A phone call does not stop the clock - only an email reply does. Auto-computed daily - spot-check before acting on a single number.'}

if __name__=='__main__':
    inbound=json.load(open('inbound.json')); sent=json.load(open('sent.json'))
    now_iso=sys.argv[1] if len(sys.argv)>1 else datetime.now(timezone.utc).isoformat()
    items,openitems=compute(inbound,sent,now_iso)
    data=build(items,openitems,now_iso,datetime.now(ET).strftime('%-m/%-d %-I:%M%p ET').lower())
    json.dump(data,open('email-response.json','w'),indent=1)
    print('GUARD count=%d'%data['overall']['count'])
    print(json.dumps(data['overall']))
    print('WEEK',json.dumps({k:data['week'][k] for k in ('count','within60','medianMin')}))
    print([(b['name'],b['kept'],b['total'],b['medianMin']) for b in data['builders']])
