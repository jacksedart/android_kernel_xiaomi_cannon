# SPDX-License-Identifier: GPL-2.0
from pathlib import Path
import subprocess,json,shutil,hashlib,tempfile
B=Path(__file__).resolve().parents[3]; T=tempfile.TemporaryDirectory(prefix='ion-budget-');H=Path(T.name)
CXX=shutil.which('g++');assert CXX,'g++ required'

def extract(s,name):
 start=s.index('static int '+name+'(');return s[start:s.index('\n}\n',start)+3]
K='drivers/staging/android/ion/mtk/ion_mm_heap.c'
old=extract(subprocess.run(['git','-C',str(B),'show','c74f4de8b21263b862ddb8e061cfff3f86a36e85:'+K],capture_output=True,text=True,check=True).stdout,'ion_mm_heap_shrink')
new=extract((B/K).read_text(),'ion_mm_heap_shrink')
ref=extract((B/'drivers/staging/android/ion/ion_system_heap.c').read_text(),'ion_system_heap_shrink')
ref=ref.replace('ion_system_heap_shrink','reference_shrink').replace('uncached_pools','pools').replace('NUM_ORDERS','num_orders')
pre=r'''
#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <iostream>
#include <random>
#include <vector>
using gfp_t=unsigned;
struct ion_heap { int marker; };
struct ion_page_pool { int low, high, order; };
struct ion_system_heap { ion_heap heap; ion_page_pool *pools[3], *cached_pools[3]; };
constexpr int num_orders=3;
#define container_of(ptr,type,member) ((type *)((char *)(ptr)-offsetof(type,member)))
static int bad_requests;
static int ion_page_pool_shrink(ion_page_pool *p,gfp_t mask,int requested) {
    if(requested<0){++bad_requests;return 0;}
    int eligible=p->low+((mask&1)?p->high:0), chunk=1<<p->order;
    if(!requested)return eligible*chunk;
    int n=std::min(eligible,(requested+chunk-1)/chunk);
    int from_low=std::min(p->low,n);p->low-=from_low;p->high-=n-from_low;
    return n*chunk;
}
'''
post=r'''
using PoolArray=std::array<ion_page_pool,6>;
struct Result { int freed; PoolArray pools; };
using Fn=int(*)(ion_heap*,gfp_t,int);
Result run(Fn f,PoolArray p,unsigned mask,int budget){
    ion_system_heap h{};
    for(int i=0;i<3;i++){h.pools[i]=&p[2*i];h.cached_pools[i]=&p[2*i+1];}
    int n=f(&h.heap,mask,budget);return {n,p};
}
bool same(const Result&a,const Result&b){
    if(a.freed!=b.freed)return false;
    for(int i=0;i<6;i++)if(a.pools[i].low!=b.pools[i].low||a.pools[i].high!=b.pools[i].high)return false;
    return true;
}
int main(){
    std::mt19937 gen(6853);int errors=0,old_budget_violations=0,cases=0;
    PoolArray full{};for(int i=0;i<6;i++)full[i]={128,0,(i/2==0?4:(i/2==1?1:0))};
    auto example_old=run(before_shrink,full,1,64),example_new=run(after_shrink,full,1,64);
    for(int test=0;test<30000;test++){
        PoolArray p{};
        for(int i=0;i<6;i++)p[i]={int(gen()%128),int(gen()%128),(i/2==0?4:(i/2==1?1:0))};
        if(test%11==0)for(auto&x:p)x.low=x.high=0;
        unsigned mask=gen()%2;int budget=(test%7==0?0:int(gen()%5000+1));
        int eligible=0;for(const auto&x:p)eligible+=(x.low+((mask&1)?x.high:0))*(1<<x.order);
        auto a=run(before_shrink,p,mask,budget),b=run(after_shrink,p,mask,budget),r=run(reference_shrink,p,mask,budget);
        if(!same(b,r))++errors;
        if(budget==0){
            Result expected{eligible,p};if(!same(b,expected))++errors;
        }else{
            if(a.freed>budget+15)++old_budget_violations;
            if(b.freed>budget+15||b.freed>eligible||b.freed<std::min(budget,eligible))++errors;
            int remain=0;for(int i=0;i<6;i++){
                const auto&x=b.pools[i];remain+=(x.low+((mask&1)?x.high:0))*(1<<x.order);
                if(x.low<0||x.high<0||(!(mask&1)&&x.high!=p[i].high))++errors;
            }
            if(eligible-remain!=b.freed)++errors;
        }
        ++cases;
    }
    errors+=bad_requests;
    std::cout<<"{\"cases\":"<<cases<<",\"candidate_errors\":"<<errors
      <<",\"original_budget_violations\":"<<old_budget_violations
      <<",\"example_requested_pages\":64,\"example_original_freed\":"<<example_old.freed
      <<",\"example_candidate_freed\":"<<example_new.freed<<"}";
    return errors?1:0;
}
'''
kfile=H/'ion-budget.cpp';kfile.write_text(pre+old.replace('ion_mm_heap_shrink','before_shrink')+new.replace('ion_mm_heap_shrink','after_shrink')+ref+post)
results={};commands=[]

def compile_and_run(srcs,name):
 exe=H/(name+'.exe')
 cmd=[CXX,'-std=c++17','-O2','-Wall','-Wextra','-Werror','-static','-I'+str(H/'include'),*[str(x) for x in srcs],'-o',str(exe)]
 r=subprocess.run(cmd,capture_output=True,text=True,timeout=90);commands.append({'name':name,'compile_exit':r.returncode,'diagnostics':r.stderr})
 if r.returncode:raise RuntimeError(r.stderr)
 r=subprocess.run([str(exe)],capture_output=True,text=True,timeout=30)
 commands[-1]['run_exit']=r.returncode
 if r.returncode:raise RuntimeError(r.stdout+r.stderr)
 return json.loads(r.stdout)
results['ion_budget']=compile_and_run([kfile],'ion-budget')

assert results['ion_budget']['candidate_errors']==0
assert results['ion_budget']['original_budget_violations']>0
results['scope']='Extracted production functions; modeled page-pool API, not real kernel/device concurrency.'
print(json.dumps(results,indent=2))
