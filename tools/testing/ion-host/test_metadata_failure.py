# SPDX-License-Identifier: GPL-2.0
from pathlib import Path
import subprocess,shutil,json,tempfile,ctypes
B=Path(__file__).resolve().parents[3];T=tempfile.TemporaryDirectory(prefix='ion-host-');H=Path(T.name);K='drivers/staging/android/ion/mtk/ion_mm_heap.c'
def extract(s):
 start=s.index('static int ion_mm_heap_allocate(');return s[start:s.index('\n}\n',start)+3]
before=extract(subprocess.run(['git','-C',str(B),'show','c74f4de8b21263b862ddb8e061cfff3f86a36e85:'+K],capture_output=True,text=True,check=True).stdout).replace('ion_mm_heap_allocate','before_allocate',1)
after=extract((B/K).read_text()).replace('ion_mm_heap_allocate','after_allocate',1)
pre=r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>
#include <stddef.h>
#include <errno.h>
#define PAGE_SIZE 4096UL
#define PAGE_ALIGN(n) (((n)+PAGE_SIZE-1)&~(PAGE_SIZE-1))
#define GFP_KERNEL 0
#define CONFIG_MTK_IOMMU_V2 1
#define CONFIG_MTK_IOMMU_PGTABLE_EXT 34
#define DOMAIN_NUM 2
#define ION_MM_DBG_NAME_LEN 32
#define IONMSG(...) ((void)0)
#define IS_ERR_OR_NULL(p) (!(p))
#define container_of(ptr,type,member) ((type *)((char *)(ptr)-offsetof(type,member)))
struct list_head { struct list_head *next,*prev; };
#define INIT_LIST_HEAD(h) do {(h)->next=(h);(h)->prev=(h);}while(0)
static int list_empty(struct list_head *h){return h->next==h;}
static void list_add_tail(struct list_head*n,struct list_head*h){n->next=h;n->prev=h->prev;h->prev->next=n;h->prev=n;}
static void list_del(struct list_head*n){n->prev->next=n->next;n->next->prev=n->prev;}
#define list_for_each_entry_safe(pos,n,head,member) \
 for(struct list_head *_p=(head)->next,*_next; _p!=(head) && \
 (_next=_p->next,(pos)=container_of(_p,struct page_info,member), \
 (n)=(_next==(head)?NULL:container_of(_next,struct page_info,member)),1);_p=_next)
struct page{int order,id;};
struct page_info {struct page*page;unsigned int order;struct list_head list;};
struct scatterlist{struct page*page;unsigned int length,dma_length;};
struct sg_table{struct scatterlist*sgl;int nents;};
struct ion_heap{int marker;};
struct ion_system_heap{struct ion_heap heap;};
struct ion_mm_buffer_info{
 void*VA;unsigned int MVA[DOMAIN_NUM],FIXED_MVA[DOMAIN_NUM],iova_start[DOMAIN_NUM],iova_end[DOMAIN_NUM];
 int module_id,fix_module_id,mva_cnt,pid,lock;int port[DOMAIN_NUM];struct sg_table*table_orig;
 struct{int value1,value2,value3,value4;char dbg_name[ION_MM_DBG_NAME_LEN];}dbg_info;
};
struct ion_buffer{struct sg_table*sg_table;struct sg_table*sg_table_orig;void*priv_virt;unsigned long size;int pid;};
static unsigned int orders[]={4,1,0};
static unsigned long totalram_pages=100000;
static unsigned long long alloc_large_fail_ts;
static unsigned int caller_pid,caller_tid;
struct {int pid,tgid;} task={123,123};
#define current (&task)
static int stage,kalloc_calls,page_calls,live_pages,returned_pages,unexpected_free;
static struct page*allocated[100];
static void*kzalloc(size_t n,int flags){(void)flags;kalloc_calls++;if((stage==1&&kalloc_calls==1)||(stage==3&&kalloc_calls==2))return NULL;return calloc(1,n);}
static void kfree(void*p){free(p);}
static unsigned long long sched_clock(void){static unsigned long long t=2000000000ULL;return ++t;}
static bool ion_buffer_cached(struct ion_buffer*b){(void)b;return false;}
static int ion_mm_pool_total(struct ion_system_heap*h,unsigned long order,bool cached){(void)h;(void)order;(void)cached;return 100;}
static int get_order(unsigned long n){int o=0;while((PAGE_SIZE<<o)<n)o++;return o;}
static void mutex_init(int*p){*p=0;}
static int sg_alloc_table(struct sg_table*t,int n,int flags){(void)flags;if(stage==2)return -ENOMEM;t->sgl=calloc(n,sizeof(*t->sgl));t->nents=n;return t->sgl?0:-ENOMEM;}
static void sg_free_table(struct sg_table*t){free(t->sgl);t->sgl=NULL;}
static void sg_set_page(struct scatterlist*s,struct page*p,unsigned int len,int off){(void)off;s->page=p;s->length=len;}
#define sg_dma_len(s) ((s)->dma_length)
#define sg_next(s) ((s)+1)
#define sg_page(s) ((s)->page)
#define for_each_sg(sgl,sg,n,i) for((i)=0,(sg)=(sgl);(i)<(n);(i)++,(sg)++)
static struct page_info*alloc_largest_available(struct ion_system_heap*h,struct ion_buffer*b,unsigned long size,unsigned int max){
 (void)h;(void)b;page_calls++;if(stage>=10&&page_calls==stage-9)return NULL;
 unsigned order=0;for(int i=0;i<3;i++)if(orders[i]<=max&&(PAGE_SIZE<<orders[i])<=size){order=orders[i];break;}
 struct page_info*p=calloc(1,sizeof(*p));p->page=calloc(1,sizeof(*p->page));p->order=order;p->page->order=order;
 p->page->id=page_calls;allocated[page_calls]=p->page;live_pages+=1<<order;INIT_LIST_HEAD(&p->list);return p;
}
static void free_buffer_page(struct ion_system_heap*h,struct ion_buffer*b,struct page*p,unsigned order){
 (void)h;(void)b;if(!p||allocated[p->id]!=p||p->order!=(int)order){unexpected_free++;return;}
 live_pages-=1<<order;returned_pages+=1<<order;allocated[p->id]=NULL;free(p);
}
'''
post=r'''
typedef int(*Fn)(struct ion_heap*,struct ion_buffer*,unsigned long,unsigned long,unsigned long);
struct result{int ret,unreturned,double_free;};
static struct result run(Fn f,int failure_stage){
 stage=failure_stage;kalloc_calls=page_calls=live_pages=returned_pages=unexpected_free=0;memset(allocated,0,sizeof(allocated));
 struct ion_system_heap heap={0};struct ion_buffer b={0};unsigned long bytes=67*PAGE_SIZE;
 int ret=f(&heap.heap,&b,bytes,0,0);
 if(!ret){
  struct scatterlist*sg;int i;for_each_sg(b.sg_table->sgl,sg,b.sg_table->nents,i)free_buffer_page(&heap,&b,sg_page(sg),get_order(sg->length));
  sg_free_table(b.sg_table);free(b.sg_table);free(b.priv_virt);
 }
 struct result out={ret,live_pages,unexpected_free};
 for(int i=0;i<100;i++)if(allocated[i])free(allocated[i]);
 return out;
}
int main(void){
 int stages[]={0,1,2,3,10,12,15};int errors=0,old_failures=0,old_metadata_pages=0;
 for(unsigned i=0;i<sizeof(stages)/sizeof(stages[0]);i++){
  struct result a=run(before_allocate,stages[i]),b=run(after_allocate,stages[i]);
  if(a.unreturned||a.double_free)old_failures++;
  if(stages[i]==3)old_metadata_pages=a.unreturned;
  if(b.unreturned||b.double_free||a.ret!=b.ret||(stages[i]&&b.ret!=-ENOMEM)||(!stages[i]&&b.ret))errors++;
 }
 printf("{\"fault_scenarios\":7,\"original_ownership_failures\":%d,\"original_metadata_failure_unreturned_pages\":%d,\"candidate_errors\":%d}",old_failures,old_metadata_pages,errors);
 return errors?1:0;
}
'''
src=H/'ion-allocation-failures.c';src.write_text(pre+before+after+post)
cc=shutil.which('gcc');assert cc
exe=H/'ion-allocation-failures.exe'
cmd=[cc,'-std=gnu11','-O2','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-Wno-unused-but-set-variable','-Wno-int-to-pointer-cast','-static',str(src),'-o',str(exe)]
r=subprocess.run(cmd,capture_output=True,text=True,timeout=60);assert r.returncode==0,r.stderr
r=subprocess.run([str(exe)],capture_output=True,text=True,timeout=15);assert r.returncode==0,r.stdout+r.stderr
result=json.loads(r.stdout);assert result['original_ownership_failures']==1;assert result['candidate_errors']==0;assert result['original_metadata_failure_unreturned_pages']==67
result['scope']='Actual allocator function bodies with modeled kernel allocation/list/SG APIs; installed CONFIG_MTK_IOMMU_V2=y and CONFIG_MTK_IOMMU_PGTABLE_EXT=34 branches are enabled. Includes success, table allocation failure, SG allocation failure, metadata allocation failure and three partial-page failures. The harness uses small allocations and zero user_va; host long/pointer widths are reported and the unchanged zero-address cast warning is suppressed. Does not validate ARM64 ABI, concurrent hardware, real kernel pool state or device stability.'
result['host_long_bytes']=ctypes.sizeof(ctypes.c_ulong)
result['host_pointer_bytes']=ctypes.sizeof(ctypes.c_void_p)
result['compiler']=subprocess.run([cc,'--version'],capture_output=True,text=True).stdout.splitlines()[0]
(H/'allocation-failure-results.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
