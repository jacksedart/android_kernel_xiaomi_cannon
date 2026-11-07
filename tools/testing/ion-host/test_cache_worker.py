# SPDX-License-Identifier: GPL-2.0
from pathlib import Path
import subprocess,tempfile,shutil,json
ROOT=Path(__file__).resolve().parents[3];P='drivers/staging/android/ion/mtk/ion_comm.c'
BASE='c74f4de8b21263b862ddb8e061cfff3f86a36e85'
old=subprocess.run(['git','-C',str(ROOT),'show',BASE+':'+P],capture_output=True,text=True,check=True).stdout
new=(ROOT/P).read_text()
def block(s):
 start=s.index('\t\tbuffer->heap = ion_cam_heap;');end=s.index('\n\t\tbuffer = NULL;',start)+len('\n\t\tbuffer = NULL;');return s[start:end]
source=r'''
#include <stdlib.h>
#include <stdio.h>
#include <errno.h>
#define IONMSG(...) ((void)0)
struct ion_heap{int marker;};
struct ion_buffer{struct ion_heap*heap;unsigned flags,size;int ready;};
static int requested_result,bad_free,free_calls,errors;
static unsigned observed_flags,observed_size;
static int ion_mm_heap_cache_allocate(struct ion_heap*h,struct ion_buffer*b,unsigned size,int align,int flags){
 (void)h;(void)align;(void)flags;observed_flags=b->flags;observed_size=size;b->ready=!requested_result;return requested_result;
}
static void ion_mm_heap_cache_free(struct ion_buffer*b){free_calls++;if(!b->ready)bad_free++;}
static void kfree(void*p){free(p);}
'''
for name,text in [('before',old),('after',new)]:
 source+='static void '+name+'(struct ion_heap*ion_cam_heap,unsigned req_cache_size,int cache_buffer){\nint ret=0;struct ion_buffer*buffer=calloc(1,sizeof(*buffer));\n'+block(text)+'\n(void)ret;\n}\n'
source+=r'''
int main(void){
 int cases=0,old_bad=0;struct ion_heap h={0};int results[]={0,-ENOMEM,-EINVAL,-EFAULT};
 for(unsigned i=0;i<4;i++)for(int cached=0;cached<2;cached++){
  requested_result=results[i];bad_free=free_calls=0;before(&h,16384,cached);old_bad+=bad_free;
  bad_free=free_calls=0;after(&h,16384,cached);
  if(bad_free||free_calls!=(results[i]==0)||observed_size!=16384||observed_flags!=(cached?3U:0U))errors++;
  cases++;
 }
 printf("{\"cases\":%d,\"original_invalid_free_attempts\":%d,\"candidate_errors\":%d}",cases,old_bad,errors);return errors?1:0;
}
'''
with tempfile.TemporaryDirectory(prefix='ion-worker-') as tmp:
 t=Path(tmp);c=t/'worker.c';c.write_text(source);cc=shutil.which('gcc');assert cc
 subprocess.run([cc,'-std=gnu11','-O2','-Wall','-Wextra','-Werror','-static',str(c),'-o',str(t/'test.exe')],check=True,capture_output=True)
 r=subprocess.run([str(t/'test.exe')],capture_output=True,text=True,check=True);data=json.loads(r.stdout);assert data['original_invalid_free_attempts']==6;print(json.dumps(data,indent=2))
