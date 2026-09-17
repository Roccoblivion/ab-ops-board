#!/usr/bin/env python3
# Computes "new-job first email response" (Metric 1) for rest@ + cons@ shared boxes.
# INPUT:  inbound.json = [{box,subject,sender,received}]  (builder-domain inbound, 30d)
#         sent.json    = [{box,subject,sender,sent}]      (box Sent Items, 30d)
# OUTPUT: email-response.json  (same schema the board card reads)
import json, re, sys, statistics, base64
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

def norm(subj):
    s=subj or ""
    while True:
        n=re.sub(r'^\s*(re|fw|fwd|aw|tr)\s*:\s*','',s,flags=re.I)
        if n==s: break
        s=n
    return re.sub(r'\s+',' ',s).strip().lower()

DOMAINS={'taylormorrison.com':'Taylor Morrison','nealcommunities.com':'Neal',
         'pulte.com':'Pulte','pultegroup.com':'Pulte'}
def builder_of(sender):
    s=(sender or '').lower()
    for d,name in DOMAINS.items():
        if d in s: return name
    return None
NOISE=re.compile(r'automatic reply|undeliverable|out of office|read:|accepted:|declined:|delivery has failed|delivery status', re.I)
NOISE_SENDER=re.compile(r'postmaster@|mailer-daemon|quickbooks@|notification\.intuit|klaviyo|houzz|constructconnect|ccsend|no-?reply', re.I)
# new-job opener patterns (per doc); precision-favoring
NEWJOB=re.compile(r'\bwo\b|\bwar\b|warranty task|\(wo\)|buildpro|remediation request|create a plan|plan of repair|truss clean|mold (mediation|remediation)|work order|\bepo\b', re.I)

def is_opener_subject(subj):
    return bool(NEWJOB.search(subj or ''))

def compute(inbound, sent, now_iso):
    # index sent replies by (box, normsubject) -> sorted sent times
    sent_idx={}
    for m in sent:
        k=(m['box'], norm(m['subject']))
        sent_idx.setdefault(k,[]).append(m['sent'])
    for k in sent_idx: sent_idx[k].sort()
    seen=set()  # (box, normsubject) already used as opener
    items=[]; openitems=[]
    for m in sorted(inbound, key=lambda x:x['received']):
        b=builder_of(m['sender'])
        if not b: continue
        subj=m['subject'] or ''
        if NOISE.search(subj) or NOISE_SENDER.search(m['sender'] or ''): continue
        if not is_opener_subject(subj): continue
        key=(m['box'], norm(subj))
        if key in seen: continue   # only first occurrence = the opener
        seen.add(key)
        # first reply from the box after opener
        reply=None
        for st in sent_idx.get(key,[]):
            if parse(st)>parse(m['received']):
                reply=st; break
        if reply:
            mins=biz_minutes(m['received'],reply)
            items.append({'job':subj[:70],'acct':b,'min':mins,'kept':mins<=60,'box':m['box']})
        else:
            wait=biz_minutes(m['received'],now_iso)
            openitems.append({'job':subj[:70],'acct':b,'waitMin':wait,'box':m['box']})
    return items, openitems

def agg(vals):
    if not vals: return {'count':0,'medianMin':None,'within60':0,'within60Pct':None,'bestMin':None,'worstMin':None}
    return {'count':len(vals),'medianMin':round(statistics.median(vals)),
            'within60':sum(1 for v in vals if v<=60),
            'within60Pct':round(100*sum(1 for v in vals if v<=60)/len(vals)),
            'bestMin':min(vals),'worstMin':max(vals)}

def build(items, openitems, now_iso, label, auto=True):
    allv=[i['min'] for i in items]
    builders=[]
    for b in ['Neal','Taylor Morrison','Pulte']:
        v=[i['min'] for i in items if i['acct']==b]
        if v: builders.append({'name':b,'kept':sum(1 for x in v if x<=60),'total':len(v),'medianMin':round(statistics.median(v))})
    return {'asOf':now_iso,'asOfLabel':label,'auto':auto,'window':'rolling 30 days',
            'boxes':['rest@goaboveandbeyond.us','cons@goaboveandbeyond.us'],
            'metric':'New-job first email response (Metric 1)','overall':agg(allv),
            'builders':builders,'items':sorted(items,key=lambda x:x['min']),
            'openItems':sorted(openitems,key=lambda x:-x['waitMin']),
            'note':'New-job first email response, business-hours clock (Mon-Fri 8-5 ET). Email time is a floor - some misses were handled same day by phone. Auto-computed daily - spot-check before acting on a single number.'}

if __name__=='__main__':
    inbound=json.load(open('inbound.json')); sent=json.load(open('sent.json'))
    now_iso=sys.argv[1] if len(sys.argv)>1 else datetime.now(timezone.utc).isoformat()
    items,openitems=compute(inbound,sent,now_iso)
    data=build(items,openitems,now_iso,datetime.now(ET).strftime('%-m/%-d %-I:%M%p ET').lower())
    json.dump(data,open('email-response.json','w'),indent=1)
    print('GUARD count=%d'%data['overall']['count'])
    print(json.dumps(data['overall']))
    print([(b['name'],b['kept'],b['total'],b['medianMin']) for b in data['builders']])
