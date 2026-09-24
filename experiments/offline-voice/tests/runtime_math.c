#include "../runtime/ctc_runtime.c"
#include <assert.h>
int main(void) {
    init_math();
    assert(nearest(.5f)==0 && nearest(1.5f)==2 && nearest(-1.5f)==-2);
    for(int i=-20000;i<=20000;i++) {
        float x=i*.001f;
        assert(fabsf(fast_gelu(x)-gelu(x))<.00002f);
        assert(fabsf(fast_tanh(x)-tanhf(x))<.00002f);
        if(x<=0) assert(fabsf(fast_exp(x)-expf(x))<.00004f);
    }
    assert(isfinite(fast_gelu(nextafterf(8,0))));
    assert(isfinite(fast_exp(nextafterf(0,-1))));
    float x[5]={-1,-.5f,0,.5f,1};int8_t q[16];
    quantize(x,q,5,16,1);
    assert(q[0]==-127 && q[4]==127);
    for(int i=5;i<16;i++) assert(q[i]==0);
    return 0;
}
