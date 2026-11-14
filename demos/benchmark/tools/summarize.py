"""summarize.py <dir> <tagA> <tagB>: scores per run, right-every-run / flaky / never-right counts, and the questions that moved between two variants."""
import json,sys,glob,collections,os
def load(tag):
    runs=[]
    for f in sorted(glob.glob(os.path.join(DIR,f"j_{tag}_r*.json"))): runs.append({x["question"]:x["verdict"]=="correct" for x in json.load(open(f))})
    return runs
def stats(tag):
    r=load(tag); qs=list(r[0]); per=[sum(x.values()) for x in r]
    cls=collections.Counter("stable" if sum(x[q] for x in r)==len(r) else "never" if sum(x[q] for x in r)==0 else "flaky" for q in qs)
    return r,qs,per,cls
DIR,a,b=sys.argv[1:4]
ra,qs,pa,ca=stats(a); rb,_,pb,cb=stats(b)
print(f"{a}: runs {pa} mean {sum(pa)/len(pa):.1f} | right every run {ca['stable']}, flaky {ca['flaky']}, never {ca['never']}")
print(f"{b}: runs {pb} mean {sum(pb)/len(pb):.1f} | right every run {cb['stable']}, flaky {cb['flaky']}, never {cb['never']}")
ga=lambda r,q: sum(x[q] for x in r)
up=[(q,ga(ra,q),ga(rb,q)) for q in qs if ga(rb,q)>ga(ra,q)]; down=[(q,ga(ra,q),ga(rb,q)) for q in qs if ga(rb,q)<ga(ra,q)]
print("improved (base->new, of %d runs):"%len(ra))
for q,x,y in up: print(f"  {x}->{y}  {q[:80]}")
print("worse:")
for q,x,y in down: print(f"  {x}->{y}  {q[:80]}")
print("still never right with the change:")
for q in qs:
    if ga(rb,q)==0: print("  ",q[:90])
